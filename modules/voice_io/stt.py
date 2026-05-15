import threading
import queue
import numpy as np
import os
import re
import time
import difflib
import subprocess
import shutil
from core.logger import logger
from .audio_devices import (
    apply_input_device_selection,
    choose_startup_input_device,
    list_audio_input_devices,
)
from .safety import VoiceSafetyLayer
from .wake_detector import WakeWordDetector

# Words that stop TTS speech only (barge-in)
BARGE_IN_WORDS = {"stop", "wait", "enough", "quiet", "silence", "pause"}
# Words that cancel the running TaskRunner turn (separate from TTS barge-in)
TASK_CANCEL_WORDS = {"cancel", "abort", "terminate", "stop", "nevermind"}
FILLER_ONLY_WORDS = {"please", "yeah", "yes", "okay", "ok", "go", "uh", "um", "hmm", "hm"}
LOW_SIGNAL_TRANSCRIPTS = {"you", "yo", "uh", "um", "hmm", "hm", "mm", "mmm", "ah", "oh"}
MEDIA_NOISE_PHRASES = {
    "thank you for watching",
    "thanks for watching",
    "like and subscribe",
    "dont forget to subscribe",
    "don t forget to subscribe",
    "subscribe to our channel",
    "welcome back to",
    "in this video",
}

# Whitelist for restricted media control mode
MEDIA_COMMAND_WHITELIST = {
    "play", "pause", "resume", "stop", "next", "previous", "skip", 
    "forward", "back", "backward", "revert", "rewind", "seconds", "secs", "video",
    "wake", "up", "friday"
}
WAKE_WORD_VARIANTS = ("hey friday", "friday", "florida", "freddy", "fry day", "fryday")

class STTEngine:
    def __init__(self, app_core):
        self.app_core = app_core
        self.is_listening = False  # Software gate (False = mute/ignore)
        self._loop_active = False # Underlying hardware stream state
        self.wake_armed = False
        self._processing_voice = False
        self.last_rejected_reason = ""
        self._explicit_activation_until = 0.0
        self._explicit_activation_pending = False
        self.model = None
        self.q = queue.Queue(maxsize=32)
        self.listen_thread = None
        self._init_lock = threading.Lock()
        self._initialized_event = threading.Event()
        self._initializing = False
        self.model_name = self._config_str("voice.stt_model", "base.en", "FRIDAY_WHISPER_MODEL")
        self.compute_type = self._config_str("voice.stt_compute_type", "int8", "FRIDAY_WHISPER_COMPUTE_TYPE")
        self.language = self._config_str("voice.stt_language", "en", "FRIDAY_WHISPER_LANGUAGE").lower()
        self.download_root = self._config_str("voice.stt_download_root", "", "FRIDAY_WHISPER_DOWNLOAD_ROOT") or None
        self.cpu_threads = self._config_int("voice.stt_cpu_threads", max(1, min(8, os.cpu_count() or 1)), "FRIDAY_WHISPER_CPU_THREADS")
        self._drop_audio_until = 0.0
        self.device_id = None # Default device
        self.device_label = "System default"
        self.target_samplerate = 16000
        self.stream_samplerate = self.target_samplerate
        self.stream_channels = 1
        self.stream_blocksize = 800
        self._startup_device_selected = False
        self.max_utterance_duration = float(
            os.getenv("FRIDAY_MAX_UTTERANCE_S")
            or self._config_float("voice.stt_max_utterance_s", 20.0)
        )
        self.min_utterance_duration = float(os.getenv("FRIDAY_MIN_UTTERANCE_S", "0.35"))
        self.listen_resume_delay_s = float(os.getenv("FRIDAY_LISTEN_RESUME_DELAY_S", "0.35"))
        self._listen_request_id = 0
        self._listen_request_lock = threading.Lock()

        # VAD settings - tuned for background noise rejection
        self.silence_threshold = 0.008
        self.silence_duration = 0.6
        self.barge_in_rms_threshold = float(os.getenv("FRIDAY_BARGE_IN_RMS", "0.045"))
        self.barge_in_trigger_frames = max(1, int(os.getenv("FRIDAY_BARGE_IN_FRAMES", "4")))
        self.barge_in_grace_period_s = float(os.getenv("FRIDAY_BARGE_IN_GRACE_S", "0.7"))
        self.barge_in_post_stop_drop_s = float(os.getenv("FRIDAY_BARGE_IN_POST_STOP_DROP_S", "0.12"))
        self._barge_in_frame_count = 0
        self.use_rms_barge_in = True

        # Profile state
        self.is_bluetooth_active = False
        self.system_media_active = False
        self._last_profile_check = 0.0
        self.profile_check_interval = 5.0
        self.wake_session_timeout_s = self._config_float("conversation.wake_session_timeout_s", 12.0)
        self.assistant_echo_window_s = self._config_float("conversation.assistant_echo_window_s", 1.8)
        self._wake_session_until = 0.0
        self.min_wake_free_words = int(os.getenv("FRIDAY_MIN_WAKE_FREE_WORDS", "3"))
        self.media_max_uninvoked_words = self._config_int("voice.media_max_uninvoked_words", 4)
        self.wake_model_path = self._resolve_project_path(
            self._config_str("voice.wake_model_path", "models/hey_friday.onnx")
        )
        self.wake_threshold = self._config_float("voice.wake_threshold", 0.5)
        self.wake_transcript_fallback_enabled = self._config_bool("voice.wake_transcript_fallback", True)
        self.wake_transcript_fallback = False
        self.wake_detector = WakeWordDetector(self.wake_model_path, threshold=self.wake_threshold)
        self.safety = VoiceSafetyLayer(self.media_max_uninvoked_words)

    def initialize(self):
        if self.model is not None:
            return True

        with self._init_lock:
            if self.model is not None:
                return True
            if self._initializing:
                should_wait = True
            else:
                self._initializing = True
                self._initialized_event.clear()
                should_wait = False

        if should_wait:
            self._initialized_event.wait(timeout=30)
            return self.model is not None

        try:
            from faster_whisper import WhisperModel
            logger.info(
                "Initializing faster-whisper %s model (compute=%s, language=%s)...",
                self.model_name,
                self.compute_type,
                self.language,
            )
            self.model = WhisperModel(
                self.model_name,
                device="cpu",
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
                download_root=self.download_root,
            )
            logger.info("faster-whisper loaded successfully.")
            
            # Start the persistent hardware stream thread immediately after model load
            self._start_hardware_stream()
            
            return True
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            return False
        finally:
            with self._init_lock:
                self._initializing = False
                self._initialized_event.set()

    def warm_up(self):
        self._start_hardware_stream()
        if self._current_mode() != "wake_word":
            threading.Thread(target=self.initialize, daemon=True).start()

    def audio_callback(self, indata, frames, time_info, status):
        """Always running hardware callback."""
        if status:
            logger.warning(f"Audio status: {status}")

        # Periodic profile check (Adaptive VAD)
        now = time.monotonic()
        if self._loop_active and now - self._last_profile_check > self.profile_check_interval:
            self._update_audio_profile()
            self._last_profile_check = now

        if self.wake_armed and not self.is_listening:
            if self.wake_detector.process_frame(indata):
                self._handle_wake_detected()
            elif self.wake_detector.unavailable_reason:
                self._reject_transcript(self.wake_detector.unavailable_reason, log_level="debug")
            return
        
        # Software Gate: Only put data into queue if we are actively transcribing.
        if not self.is_listening:
            return

        if now < self._drop_audio_until:
            return

        rms = float(np.sqrt(np.mean(indata ** 2)))
        if self._speech_output_busy():
            if self._tts_is_actively_speaking() and self._maybe_interrupt_for_live_speech(rms):
                return
            if not self._tts_is_actively_speaking():
                return
            # Do NOT return early here. We allow audio to pass into the queue 
            # while speaking so word-based barge-in ("Friday stop") can work.
            # But we use a higher threshold to avoid transcribing everything.
            if rms < self.silence_threshold * 2.0:
                return
            
        try:
            self.q.put_nowait(indata.copy())
        except queue.Full:
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass
            try:
                self.q.put_nowait(indata.copy())
            except queue.Full:
                logger.debug("[STT] Queue full even after pruning.")

    def _start_hardware_stream(self):
        """Starts the persistent thread that keeps the sounddevice InputStream open."""
        if self._loop_active:
            return
        self._loop_active = True
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()
        logger.info("Persistent audio stream thread started.")

    def _listen_loop(self):
        """Thread that keeps the microphone hardware active to avoid Bluetooth reconnection blips."""
        try:
            import sounddevice as sd
            self._ensure_startup_input_device()
            stream_settings = self._resolve_stream_settings(sd)
            self.stream_samplerate = stream_settings["samplerate"]
            self.stream_channels = stream_settings["channels"]
            self.stream_blocksize = stream_settings["blocksize"]

            logger.info(
                "Opening persistent sd.InputStream on device %s (%s, %s channel%s, blocksize=%s)...",
                stream_settings["device"],
                self.stream_samplerate,
                self.stream_channels,
                "" if self.stream_channels == 1 else "s",
                self.stream_blocksize,
            )
            # We wrap the InputStream in a try/except because some devices might not be available
            with sd.InputStream(
                samplerate=self.stream_samplerate,
                blocksize=self.stream_blocksize,
                device=stream_settings["device"],
                dtype='float32',
                channels=self.stream_channels,
                callback=self.audio_callback
            ):
                audio_buffer = []
                silence_frames = 0
                empty_polls = 0
                frames_per_second = self.stream_samplerate / self.stream_blocksize

                while self._loop_active:
                    try:
                        # We still wait on the queue, but the callback only fills it if is_listening is True
                        data = self.q.get(timeout=0.1)
                        empty_polls = 0
                    except queue.Empty:
                        # During TTS speech, audio_callback drops sub-threshold
                        # frames so silence_frames never increments via the
                        # normal path. Treat ~250ms of empty polls as
                        # end-of-utterance so "Friday stop" finalizes fast.
                        if audio_buffer and self._tts_is_actively_speaking():
                            empty_polls += 1
                            if empty_polls >= 3:
                                self._transcribe_buffer(audio_buffer)
                                audio_buffer = []
                                silence_frames = 0
                                empty_polls = 0
                        continue

                    # If we somehow got data while not listening, clear it
                    if not self.is_listening:
                        audio_buffer = []
                        silence_frames = 0
                        empty_polls = 0
                        continue

                    rms = float(np.sqrt(np.mean(data ** 2)))

                    if rms > self.silence_threshold:
                        if not audio_buffer:
                            logger.debug("[VAD] Voice detected, recording...")
                        audio_buffer.append(data)
                        silence_frames = 0
                    else:
                        if audio_buffer:
                            silence_frames += 1
                            audio_buffer.append(data)

                    buffer_duration = len(audio_buffer) / frames_per_second if frames_per_second else 0.0
                    # While TTS is speaking, react faster so "Friday stop"
                    # cuts speech with minimal latency.
                    if self._tts_is_actively_speaking():
                        min_dur = 0.2
                        silence_dur = 0.3
                    else:
                        min_dur = self.min_utterance_duration
                        silence_dur = self.silence_duration
                    has_enough_audio = buffer_duration >= min_dur
                    hit_silence_boundary = silence_frames > (silence_dur * frames_per_second)
                    hit_max_duration = buffer_duration >= self.max_utterance_duration

                    if has_enough_audio and (hit_silence_boundary or hit_max_duration):
                        self._transcribe_buffer(audio_buffer)
                        audio_buffer = []
                        silence_frames = 0

        except Exception as e:
            logger.error(f"Error in persistent listening loop: {e}")
            self._loop_active = False

    def _process_voice_text(self, text):
        text_clean = self._sanitize_text(text)
        if not text_clean:
            self._reject_transcript("empty transcript", log_level="debug")
            return

        # ── DICTATION OVERRIDE ──────────────────────────────────────────────
        # When a dictation session is active, send transcripts straight to its
        # buffer and skip wake-word / media gating. Only "end memo" / "cancel
        # memo" control phrases are routed to the normal pipeline.
        dictation = getattr(self.app_core, "dictation_service", None)
        # Strict identity check so MagicMock-wrapped tests don't accidentally
        # take this branch — only a real DictationService.is_active() returns
        # a literal True.
        dictation_active = (
            dictation is not None
            and hasattr(dictation, "is_active")
            and dictation.is_active() is True
        )
        if dictation_active:
            control = dictation.detect_control_phrase(text_clean)
            if control:
                residue = dictation.strip_control_phrase(text_clean)
                if residue:
                    dictation.append(residue)
                # Fall through to normal pipeline so the end/cancel tool runs.
                text_clean = (
                    "friday end memo" if control == "end" else "friday cancel memo"
                )
                wake_found = True
                has_voice_session = True
                invoked = True
                text_clean = self._clean_command_text(text_clean)
            else:
                logger.info("[dictation] captured: %s", text_clean[:80])
                dictation.append(text_clean)
                self._extend_wake_session()
                return
        else:
            wake_found = self._contains_wake_word(text_clean)
            has_voice_session = self._has_active_wake_session()
            invoked = wake_found or has_voice_session or self._has_explicit_activation()
            text_clean = self._clean_command_text(text_clean)
        if not text_clean:
            self._reject_transcript("empty command after cleanup", log_level="debug")
            return

        # ── TRACK 1: Task cancellation ──────────────────────────────────────
        # "cancel / abort / terminate" cancels the TaskRunner turn, not just TTS.
        if self._is_task_cancel_command(text_clean):
            task_runner = getattr(self.app_core, "task_runner", None)
            if task_runner and task_runner.is_busy():
                logger.info("[STT] Task cancel command: '%s'", text_clean)
                tts = getattr(self.app_core, "tts", None)
                if tts:
                    tts.stop()
                self._clear_audio_queue()
                self.app_core.cancel_current_task(announce=True)
                return
            # No task running → treat as normal barge-in / command

        if self._current_mode() == "wake_word" and not invoked:
            self._reject_transcript("waiting for wake word", text_clean, log_level="debug")
            return

        if self._is_low_signal_transcript(text_clean) and not wake_found:
            self._reject_transcript("low-signal transcript", text_clean, log_level="debug")
            return

        if self._looks_like_recent_assistant_echo(text_clean) and not wake_found and not self.app_core.is_speaking:
            self._reject_transcript("assistant echo", text_clean)
            return

        if self.system_media_active and not wake_found and self._looks_like_media_noise(text_clean):
            self._reject_transcript("likely media audio", text_clean)
            return

        media_mode = getattr(self.app_core, "media_control_mode", False)
        if not isinstance(media_mode, bool):
            media_mode = False

        words = set(text_clean.split())
        is_media_cmd = bool(words & MEDIA_COMMAND_WHITELIST)
        is_wake_up = "wake up" in text_clean

        safety_invoked = invoked
        if media_mode:
            # In restricted media mode, do not let an earlier wake session keep
            # arbitrary YouTube/background speech trusted for several seconds.
            safety_invoked = wake_found or self._has_explicit_activation()

        decision = self.safety.evaluate_media_transcript(
            text_clean,
            media_active=self.system_media_active,
            media_control_mode=media_mode,
            invoked=safety_invoked,
            is_media_command=is_media_cmd,
            is_wake_up=is_wake_up,
            is_bluetooth_active=self.is_bluetooth_active,
        )
        if not decision.accepted:
            self._reject_transcript(decision.reason, text_clean)
            return

        # ── TRACK 2: TTS barge-in (stop speech, maybe continue as command) ──
        if self._tts_is_actively_speaking():
            is_friday = "friday" in text_clean or any(
                w in text_clean for w in WAKE_WORD_VARIANTS[1:]
            )
            # Speaker (non-BT): require wake word or obvious command to avoid echo triggers
            if not self.is_bluetooth_active and not is_friday and not self._looks_like_fresh_command(text_clean):
                self._reject_transcript("speaker echo during speech", text_clean, log_level="debug")
                return

            barge_words = set(text_clean.split())
            if bool(barge_words & (BARGE_IN_WORDS | TASK_CANCEL_WORDS)) or is_friday or self._looks_like_fresh_command(text_clean):
                logger.info("[STT] Barge-in detected during speech: '%s'", text_clean)
                if self.app_core.tts:
                    self.app_core.tts.stop()
                self._clear_audio_queue()
                self._drop_audio_until = time.monotonic() + 0.15

                # Strip barge-in words; if nothing remains it was a pure TTS-stop
                for word in BARGE_IN_WORDS | TASK_CANCEL_WORDS | {"friday", "hey"}:
                    text_clean = text_clean.replace(word, "")
                text_clean = self._clean_command_text(text_clean)
                if not text_clean or text_clean in FILLER_ONLY_WORDS:
                    self._reject_transcript("barge-in TTS-stop only", text_clean, log_level="debug")
                    return
            else:
                self._reject_transcript("ignored during speech", text_clean, log_level="debug")
                return

        if wake_found:
            text_clean = self._strip_wake_words(text_clean)
            text_clean = self._clean_command_text(text_clean)
            self._extend_wake_session()
            if not text_clean:
                self.last_rejected_reason = ""
                self._emit_runtime_state()
                self._handle_wake_detected()
                return
        else:
            if not has_voice_session and not self._has_explicit_activation() and not self.is_bluetooth_active:
                word_count = len(text_clean.split())
                if word_count < self.min_wake_free_words:
                    self._reject_transcript("short transcript missing wake word", text_clean, log_level="debug")
                    return
            text_clean = self._clean_command_text(text_clean)

        if not text_clean:
            self._reject_transcript("empty command after wake cleanup", log_level="debug")
            self._clear_explicit_activation()
            return

        self._extend_wake_session()
        self.last_rejected_reason = ""
        self._emit_runtime_state()
        self._clear_explicit_activation()

        # ── Wake-word barge-in: instantly kill any running task ──────────────
        # If the user invoked Friday while the assistant is mid-task (LLM
        # streaming, TTS queued or playing), kill everything non-blocking so
        # the new command starts immediately without a 2-second join stall.
        if wake_found:
            runner = getattr(self.app_core, "task_runner", None)
            if runner and runner.is_busy():
                logger.info("[STT] Wake-word barge-in — cancelling running task for: '%s'", text_clean)
                runner.cancel_nowait()

        # ── TRACK 3a: Instant media-control fast path ────────────────────────
        # When a short utterance is purely a media command (pause/resume/next/
        # previous/forward/backward/mute), bypass the LLM router and call the
        # browser worker directly. This is the same idea as voice barge-in:
        # detect intent locally and react in milliseconds.
        if self._try_fast_media_command(text_clean):
            return

        # ── TRACK 3b: Normal command through TaskRunner pipeline ─────────────
        self.app_core.process_input(text_clean, source="voice")

    def _maybe_interrupt_for_live_speech(self, rms):
        if not self._tts_is_actively_speaking() or not self.use_rms_barge_in:
            self._barge_in_frame_count = 0
            return False

        tts = getattr(self.app_core, "tts", None)
        now = time.monotonic()
        speaking_started_at = getattr(tts, "speaking_started_at", 0.0) if tts else 0.0
        if speaking_started_at and (now - speaking_started_at) < self.barge_in_grace_period_s:
            self._barge_in_frame_count = 0
            return True

        if rms >= self.barge_in_rms_threshold:
            self._barge_in_frame_count += 1
        else:
            self._barge_in_frame_count = 0
            return False

        if self._barge_in_frame_count < self.barge_in_trigger_frames:
            return False

        self._barge_in_frame_count = 0
        if tts:
            logger.info("[STT] Live barge-in detected from voice activity.")
            self._clear_audio_queue()
            self._drop_audio_until = now + self.barge_in_post_stop_drop_s
            tts.stop()
            return True
        return False

    def _looks_like_fresh_command(self, text):
        if not text:
            return False

        current_text = getattr(getattr(self.app_core, "tts", None), "current_text", "") or ""
        similarity = difflib.SequenceMatcher(None, text, self._sanitize_text(current_text)).ratio()
        if similarity >= 0.82:
            return False

        command_starters = (
            "what", "how", "why", "when", "where", "who",
            "open", "search", "find", "read", "summarize",
            "create", "write", "append", "save", "tell",
            "show", "launch", "start", "stop",
        )
        return any(text.startswith(starter) for starter in command_starters)

    def _is_task_cancel_command(self, text):
        """Return True only when the transcript is a *pure* cancellation with no follow-up.

        "cancel" / "friday stop" → True.
        "friday stop open calculator" → False (has follow-up content).
        """
        words = text.split()
        if not set(words) & TASK_CANCEL_WORDS:
            return False
        # Strip wake/cancel/filler words and see if anything substantive remains.
        _STRIP = TASK_CANCEL_WORDS | {"friday", "hey", "that", "it", "please"}
        remaining = [w for w in words if w not in _STRIP]
        return len(remaining) == 0 and len(words) <= 6

    def _try_fast_media_command(self, text):
        """Send a short pure media-control phrase straight to the browser worker.

        Returns True if the command was handled (caller should not fall through
        to the LLM router). The fast path only fires when:
          • there is an active browser media session (media_control_mode), and
          • the cleaned utterance is short (<=4 words) and is a known
            media-control verb with no extra content.
        """
        media_mode = bool(getattr(self.app_core, "media_control_mode", False))
        if not media_mode:
            return False

        normalized = (text or "").strip().lower()
        if not normalized:
            return False
        words = normalized.split()
        if len(words) > 4:
            return False

        # Map short verbs to canonical actions. Order matters: "stop" should
        # match before "pause" because the user often says "stop the music".
        action = None
        if "pause" in words or "stop" in words:
            action = "pause"
        elif "resume" in words or "continue" in words or "unpause" in words:
            action = "resume"
        elif words == ["play"] or words[:2] == ["play", "it"] or normalized in {"keep playing", "play it"}:
            action = "resume"
        elif "next" in words or "skip" in words:
            action = "next"
        elif "previous" in words or "back" in words or "rewind" in words or "backward" in words:
            action = "previous"
        elif "forward" in words:
            action = "forward"
        elif "mute" in words or "unmute" in words:
            action = "mute"
        else:
            return False

        # Reject if the utterance carries non-control nouns ("play closer on
        # youtube music" must NOT fast-path — it should go through the
        # play_youtube_music tool).
        leftover = [
            w for w in words
            if w not in {
                "pause", "stop", "resume", "continue", "unpause", "play", "it",
                "next", "skip", "previous", "back", "rewind", "backward",
                "forward", "mute", "unmute", "the", "music", "video", "song",
                "please", "now",
            }
        ]
        if leftover:
            return False

        service = getattr(self.app_core, "browser_media_service", None)
        if service is None or not hasattr(service, "fast_media_command"):
            return False

        logger.info("[STT] Fast media command: %s", action)
        threading.Thread(
            target=service.fast_media_command,
            args=(action,),
            daemon=True,
            name="friday-fastmedia",
        ).start()
        return True

    def _dispatch_media_command(self, text):
        """Publish a media_command event for short media-control phrases."""
        normalized = text.strip()
        if any(w in normalized for w in ("pause", "stop it")):
            action = "pause"
        elif any(w in normalized for w in ("play", "resume")):
            action = "play"
        elif any(w in normalized for w in ("next", "skip")):
            action = "next"
        elif any(w in normalized for w in ("previous", "back", "rewind", "backward", "revert")):
            action = "previous"
        elif any(w in normalized for w in ("forward",)):
            action = "forward"
        else:
            # Unrecognised — fall through to the full pipeline
            self.app_core.process_input(normalized, source="voice")
            return

        event_bus = getattr(self.app_core, "event_bus", None)
        if event_bus:
            event_bus.publish("media_command", {"action": action, "text": text})
        else:
            # Fallback: normal pipeline
            self.app_core.process_input(normalized, source="voice")

    def _looks_like_short_media_command(self, text):
        normalized = self._sanitize_text(text).strip()
        if not normalized:
            return False
        if len(normalized.split()) > 4:
            return False
        direct = {
            "play", "pause", "resume", "stop", "next", "skip", "previous",
            "forward", "back", "backward", "revert", "rewind",
            "next video", "previous video", "play it", "pause it", "resume it",
            "right next", "ready play", "wake up",
        }
        if normalized in direct:
            return True
        return bool(re.fullmatch(r"(?:skip|forward|back|backward|revert|rewind)(?: \d+)?(?: seconds?| secs?)?", normalized))

    def _tts_is_actively_speaking(self):
        app_speaking = getattr(self.app_core, "is_speaking", False)
        if app_speaking is True:
            return True

        tts = getattr(self.app_core, "tts", None)
        if not tts:
            return False

        tts_speaking = getattr(tts, "is_speaking", False)
        return tts_speaking is True

    def _speech_output_busy(self):
        if self._tts_is_actively_speaking():
            return True

        tts = getattr(self.app_core, "tts", None)
        if not tts:
            return False

        pending = getattr(tts, "has_pending_speech", False)
        if isinstance(pending, bool):
            return pending
        return False

    def _should_drop_transcript_before_logging(self, text):
        text_clean = self._sanitize_text(text)
        if not text_clean:
            return True
        if self._contains_wake_word(text_clean):
            return False
        return self._is_low_signal_transcript(text_clean)

    def _looks_like_media_noise(self, text):
        normalized = self._sanitize_text(text)
        return any(phrase in normalized for phrase in MEDIA_NOISE_PHRASES)

    def start_listening(self):
        """Activate the voice gate according to the current listening mode."""
        mode = self._current_mode()
        if mode == "wake_word":
            return self.arm_wake_word()
        return self.activate_for_invocation(source="command" if mode in {"manual", "on_demand"} else "policy")

    def activate_for_invocation(self, source="button"):
        """Explicitly open transcription for a short user-invoked session."""
        mode = self._current_mode()
        self.wake_armed = False
        self.wake_transcript_fallback = False
        if mode in {"wake_word", "on_demand", "manual"}:
            self._explicit_activation_until = time.monotonic() + self.wake_session_timeout_s
        if source in {"button", "command", "wake_word"}:
            self._explicit_activation_pending = True
        return self._start_transcription_gate()

    def arm_wake_word(self):
        """Keep hardware warm and listen only for the low-cost wake detector."""
        self._start_hardware_stream()
        self.is_listening = False
        self.wake_armed = True
        self.wake_transcript_fallback = False
        if not self.wake_detector.initialize():
            reason = self.wake_detector.unavailable_reason or "wake detector unavailable"
            if self.wake_transcript_fallback_enabled:
                logger.warning("[WakeWord] %s; using transcript wake fallback.", reason)
                return self._start_transcript_wake_gate(reason)
            self.wake_armed = False
            self._reject_transcript(reason)
        self._emit_runtime_state()
        return True

    def _start_transcript_wake_gate(self, reason=""):
        self.last_rejected_reason = ""
        self.wake_armed = True
        self.wake_transcript_fallback = True
        self._explicit_activation_pending = False
        self._explicit_activation_until = 0.0

        request_id = self._next_listen_request_id()
        if not self.model:
            logger.info("Wake transcript fallback will arm after the STT model is ready.")
            threading.Thread(
                target=self._complete_transcript_wake_gate_after_initialize,
                args=(request_id,),
                daemon=True,
            ).start()
        else:
            self._activate_transcript_wake_gate(request_id)

        self._emit_runtime_state()
        return True

    def _complete_transcript_wake_gate_after_initialize(self, request_id):
        if not self.initialize():
            logger.error("Cannot arm transcript wake fallback: STT model or hardware stream failed.")
            self.wake_armed = False
            self.wake_transcript_fallback = False
            self._reject_transcript("wake transcript fallback unavailable")
            return
        self._activate_transcript_wake_gate(request_id)

    def _activate_transcript_wake_gate(self, request_id):
        if request_id != self._current_listen_request_id():
            return
        self._clear_audio_queue()
        self._barge_in_frame_count = 0
        self._drop_audio_until = max(self._drop_audio_until, time.monotonic() + self.listen_resume_delay_s)
        self.is_listening = True
        self.wake_armed = True
        self.wake_transcript_fallback = True
        logger.info("Wake transcript fallback ARMED. Say 'Friday' before the command.")
        self._emit_runtime_state()

    def _start_transcription_gate(self):
        """Lightweight software gate activation."""
        if self.is_listening:
            self._emit_runtime_state()
            return True

        request_id = self._next_listen_request_id()
        if not self.model:
            logger.info("STT model is still loading. Microphone will open when it is ready.")
            threading.Thread(
                target=self._complete_listen_after_initialize,
                args=(request_id,),
                daemon=True,
            ).start()
            return True

        if self._speech_output_busy():
            if self._tts_is_actively_speaking():
                logger.info("Microphone barge-in gate armed during speech.")
            else:
                logger.info("Microphone barge-in gate armed for queued speech.")
            self._activate_listening(request_id, resume_delay=0.0)
            threading.Thread(
                target=self._complete_listen_when_ready,
                args=(request_id,),
                daemon=True,
            ).start()
            return True

        self._activate_listening(request_id)
        return True

    def _complete_listen_after_initialize(self, request_id):
        if not self.initialize():
            logger.error("Cannot start listening: STT model or hardware stream failed.")
            return
        self._complete_listen_when_ready(request_id)

    def stop_listening(self):
        """Lightweight software gate deactivation."""
        self._next_listen_request_id()
        self.is_listening = False
        self.wake_armed = False
        self.wake_transcript_fallback = False
        self._explicit_activation_until = 0.0
        self._explicit_activation_pending = False
        self._barge_in_frame_count = 0
        self._clear_audio_queue()
        logger.info("Microphone software gate CLOSED.")
        self._emit_runtime_state()
        return True

    def set_device(self, device_id):
        """Switch device by restarting the underlying hardware loop."""
        selection = apply_input_device_selection(device_id)
        next_device = selection.get("device")
        next_label = selection.get("label", "System default")

        if self.device_id == next_device and self.device_label == next_label:
            return

        logger.info("Switching mic hardware to device: %s", next_label)
        self.device_id = next_device
        self.device_label = next_label
        self._startup_device_selected = True
        self._persist_input_device(device_id)

        # We must restart the actual hardware stream if the device changes
        self._loop_active = False
        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=1.0)
        time.sleep(0.5)
        self._start_hardware_stream()
        self._emit_runtime_state()

    def shutdown(self):
        """Cleanly close the hardware stream and stop the process."""
        logger.info("STT: Shutting down persistent audio stream...")
        self._loop_active = False
        self.is_listening = False
        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=1.0)
        logger.info("STT: Hardware stream closed.")

    def _sanitize_text(self, text):
        if not isinstance(text, str): return ""
        cleaned = text.lower().strip()
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _clean_command_text(self, text):
        assistant_context = getattr(self.app_core, "assistant_context", None)
        if assistant_context and hasattr(assistant_context, "clean_voice_transcript"):
            cleaned = assistant_context.clean_voice_transcript(text)
            if isinstance(cleaned, str) and cleaned:
                return cleaned
        return self._sanitize_text(text)

    def _contains_wake_word(self, text):
        text = self._sanitize_text(text)
        if not text:
            return False
        return any(variant in text for variant in WAKE_WORD_VARIANTS)

    def _strip_wake_words(self, text):
        cleaned = self._sanitize_text(text)
        for variant in WAKE_WORD_VARIANTS:
            cleaned = cleaned.replace(variant, " ")
        return re.sub(r"\s+", " ", cleaned).strip()

    def _extend_wake_session(self):
        self._wake_session_until = max(self._wake_session_until, time.monotonic() + self.wake_session_timeout_s)

    def _has_active_wake_session(self):
        return time.monotonic() < self._wake_session_until

    def _is_low_signal_transcript(self, text):
        normalized = self._sanitize_text(text)
        if not normalized:
            return True
        tokens = normalized.split()
        if len(tokens) == 1 and tokens[0] in LOW_SIGNAL_TRANSCRIPTS:
            return True
        if len(tokens) <= 2 and len(set(tokens)) == 1 and tokens[0] in LOW_SIGNAL_TRANSCRIPTS:
            return True
        return False

    def _looks_like_recent_assistant_echo(self, text):
        if not text:
            return False
        candidates = []
        tts = getattr(self.app_core, "tts", None)
        now = time.monotonic()
        is_currently_speaking = bool(getattr(tts, "is_speaking", False) or getattr(self.app_core, "is_speaking", False))
        speaking_stopped_at = float(getattr(tts, "speaking_stopped_at", 0.0) or 0.0) if tts else 0.0
        if not is_currently_speaking:
            if not speaking_stopped_at:
                return False
            if (now - speaking_stopped_at) > self.assistant_echo_window_s:
                return False
        if tts:
            candidates.extend(
                candidate for candidate in (
                    getattr(tts, "current_text", ""),
                    getattr(tts, "current_sentence", ""),
                )
                if candidate
            )
        assistant_context = getattr(self.app_core, "assistant_context", None)
        if assistant_context and hasattr(assistant_context, "latest_assistant_text"):
            latest = assistant_context.latest_assistant_text()
            if latest:
                candidates.append(latest)

        normalized = self._sanitize_text(text)
        if len(normalized.split()) < 3:
            return False

        for candidate in candidates:
            candidate_norm = self._sanitize_text(candidate)
            if not candidate_norm:
                continue
            similarity = difflib.SequenceMatcher(None, normalized, candidate_norm).ratio()
            if similarity >= 0.84:
                return True
            if normalized == candidate_norm:
                return True
            if normalized in candidate_norm and len(normalized) >= 18:
                return True
            candidate_tokens = set(candidate_norm.split())
            normalized_tokens = set(normalized.split())
            overlap = len(candidate_tokens & normalized_tokens)
            if len(normalized_tokens) >= 6 and overlap / max(1, len(normalized_tokens)) >= 0.85:
                return True
        return False

    def _clear_audio_queue(self):
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    def _activate_listening(self, request_id=None, resume_delay=None):
        if request_id is not None and request_id != self._current_listen_request_id():
            return
        self._clear_audio_queue()
        self._barge_in_frame_count = 0
        delay = self.listen_resume_delay_s if resume_delay is None else max(0.0, float(resume_delay))
        self._drop_audio_until = max(self._drop_audio_until, time.monotonic() + delay)
        self.is_listening = True
        self.wake_armed = False
        self.wake_transcript_fallback = False
        logger.info("Microphone software gate OPENED.")
        self._emit_runtime_state()

    def _complete_listen_when_ready(self, request_id):
        while True:
            if request_id != self._current_listen_request_id():
                return
            if not self._speech_output_busy():
                self._activate_listening(request_id)
                return
            time.sleep(0.05)

    def _handle_wake_detected(self):
        logger.info("[WakeWord] Wake word detected.")
        self.last_rejected_reason = ""
        self._extend_wake_session()
        self._explicit_activation_until = time.monotonic() + self.wake_session_timeout_s
        event_bus = getattr(self.app_core, "event_bus", None)
        if event_bus and hasattr(event_bus, "publish"):
            event_bus.publish("voice_activation_requested", {"source": "wake_word"})
        else:
            self.activate_for_invocation(source="wake_word")

    def set_processing_state(self, processing):
        self._processing_voice = bool(processing)
        self._emit_runtime_state()

    def get_runtime_state(self):
        mode = self._current_mode()
        ui_state = "muted"
        if self._tts_is_actively_speaking():
            ui_state = "speaking"
        elif self._processing_voice:
            ui_state = "processing"
        elif self.is_listening:
            ui_state = "listening"
        elif self.wake_armed:
            ui_state = "armed"

        return {
            "mode": mode,
            "ui_state": ui_state,
            "hardware_warm": bool(self._loop_active),
            "actively_transcribing": bool(self.is_listening),
            "wake_armed": bool(self.wake_armed),
            "wake_transcript_fallback": bool(self.wake_transcript_fallback),
            "wake_strategy": "Transcript fallback" if self.wake_transcript_fallback else "Wake model",
            "device_label": self.device_label,
            "media_active": bool(self.system_media_active or getattr(self.app_core, "media_control_mode", False)),
            "last_rejected_reason": self.last_rejected_reason,
        }

    def _emit_runtime_state(self):
        event_bus = getattr(self.app_core, "event_bus", None)
        if event_bus and hasattr(event_bus, "publish"):
            event_bus.publish("voice_runtime_state_changed", self.get_runtime_state())

    def _reject_transcript(self, reason, text="", log_level="info"):
        reason = reason or "transcript rejected"
        if reason == self.last_rejected_reason:
            return
        self.last_rejected_reason = reason
        message = f"[STT] Rejected transcript ({reason})"
        if text:
            message = f"{message}: '{text}'"
        getattr(logger, log_level, logger.info)(message)
        self._emit_runtime_state()

    def _current_mode(self):
        getter = getattr(self.app_core, "get_listening_mode", None)
        if callable(getter):
            try:
                mode = getter()
            except Exception:
                mode = "persistent"
        else:
            config = getattr(self.app_core, "config", None)
            if config and hasattr(config, "get"):
                mode = config.get("conversation.listening_mode", "persistent")
            else:
                mode = "persistent"
        mode = str(mode or "persistent").strip().lower().replace("-", "_")
        aliases = {"wakeword": "wake_word", "on demand": "on_demand", "ondemand": "on_demand"}
        mode = aliases.get(mode, mode)
        if mode in {"persistent", "wake_word", "on_demand", "manual"}:
            return mode
        return "persistent"

    def _has_explicit_activation(self):
        return self._explicit_activation_pending or time.monotonic() < self._explicit_activation_until

    def _clear_explicit_activation(self):
        self._explicit_activation_pending = False
        self._explicit_activation_until = 0.0

    def _persist_input_device(self, device_id):
        config = getattr(self.app_core, "config", None)
        if not config or not hasattr(config, "set"):
            return
        try:
            config.set("voice.input_device", device_id)
            if hasattr(config, "save"):
                config.save()
        except Exception as exc:
            logger.warning("Could not persist microphone selection: %s", exc)

    def _resolve_project_path(self, path):
        path = str(path or "").strip()
        if not path or os.path.isabs(path):
            return path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(project_root, path)

    def _next_listen_request_id(self):
        with self._listen_request_lock:
            self._listen_request_id += 1
            return self._listen_request_id

    def _current_listen_request_id(self):
        with self._listen_request_lock:
            return self._listen_request_id

    def _update_audio_profile(self):
        """Detects if we are on Bluetooth and if system audio is active."""
        wpctl = shutil.which("wpctl")
        if not wpctl:
            return

        try:
            result = subprocess.run([wpctl, "status"], capture_output=True, text=True, check=False, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                return

            status = result.stdout
            
            # Detect Bluetooth Sink
            # Look for lines under Sinks or Filters that are marked as default (*) and have bluetooth signatures
            sinks_section = False
            is_bt = False
            for line in status.splitlines():
                if "Sinks:" in line:
                    sinks_section = True
                    continue
                if sinks_section and line.strip() == "":
                    sinks_section = False
                    continue
                
                if sinks_section and "*" in line:
                    if any(token in line.lower() for token in ("bluez", "ion", "headset", "earplay", "bt")):
                        is_bt = True
                        break

            # Detect System Audio Activity
            # Look for [active] streams that are NOT our own process
            is_media_active = False
            for raw_line in status.splitlines():
                lowered = raw_line.lower()
                if "[active]" not in lowered:
                    continue
                if any(
                    token in lowered
                    for token in ("python", "stt", "friday", "aplay", "piper", "speech", "espeak")
                ):
                    continue
                is_media_active = True
                break

            if is_bt != self.is_bluetooth_active or is_media_active != self.system_media_active:
                self.is_bluetooth_active = is_bt
                self.system_media_active = is_media_active
                self._apply_adaptive_thresholds()
                self._emit_runtime_state()
        except Exception as e:
            logger.warning(f"[STT] Failed to update audio profile: {e}")

    def _apply_adaptive_thresholds(self):
        """Sets VAD thresholds based on connection and background noise."""
        if self.is_bluetooth_active:
            # Sensitive profile for isolated headsets
            self.silence_threshold = 0.008
            self.use_rms_barge_in = True
            self.barge_in_rms_threshold = 0.045
            self.listen_resume_delay_s = 0.15
            profile_name = "HEADSET (Bluetooth)"
        else:
            # Conservative profile for built-in speakers
            # Disable volume-based barge-in to prevent self-triggering
            self.silence_threshold = 0.008
            self.barge_in_rms_threshold = 0.25 # Be very conservative
            self.use_rms_barge_in = False
            self.barge_in_grace_period_s = 1.2
            self.listen_resume_delay_s = 0.8
            profile_name = "SPEAKER (Built-in)"

        if self.system_media_active:
            # Even stricter if music is playing
            self.silence_threshold += 0.005
            self.barge_in_rms_threshold += 0.02
            self.use_rms_barge_in = False
            profile_name += " + ACTIVE MEDIA"

        logger.info(f"[STT] Adaptive VAD profile updated: {profile_name}")
        logger.debug(f"[STT] Thresholds: silence={self.silence_threshold:.4f}, barge_in={self.barge_in_rms_threshold:.4f}")

    def _config_float(self, key, default):
        config = getattr(self.app_core, "config", None)
        if config and hasattr(config, "get"):
            try:
                return float(config.get(key, default))
            except Exception:
                return float(default)
        return float(default)

    def _config_int(self, key, default, env_name=None):
        if env_name:
            env_value = os.getenv(env_name)
            if env_value:
                try:
                    return int(env_value)
                except Exception:
                    return int(default)

        config = getattr(self.app_core, "config", None)
        if config and hasattr(config, "get"):
            try:
                return int(config.get(key, default))
            except Exception:
                return int(default)
        return int(default)

    def _config_str(self, key, default, env_name=None):
        if env_name:
            env_value = os.getenv(env_name)
            if env_value:
                return env_value.strip()

        config = getattr(self.app_core, "config", None)
        if config and hasattr(config, "get"):
            try:
                value = config.get(key, default)
            except Exception:
                value = default
        else:
            value = default

        if not isinstance(value, (str, int, float, bool)):
            return str(default)
        if value is None:
            return str(default)
        return str(value).strip() or str(default)

    def _config_bool(self, key, default=False, env_name=None):
        if env_name:
            env_value = os.getenv(env_name)
            if env_value:
                return env_value.strip().lower() in {"1", "true", "yes", "on"}

        config = getattr(self.app_core, "config", None)
        if config and hasattr(config, "get"):
            try:
                value = config.get(key, default)
            except Exception:
                value = default
        else:
            value = default
        if isinstance(value, bool):
            return value
        if not isinstance(value, (str, int, float)):
            return bool(default)
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _transcribe_buffer(self, audio_buffer):
        audio_data = np.concatenate(audio_buffer, axis=0)
        audio_data = self._prepare_audio_for_transcription(audio_data)

        logger.debug("[Whisper] Transcribing...")
        transcribe_kwargs = {
            "beam_size": 1,
            "best_of": 1,
            "patience": 1,
            "condition_on_previous_text": False,
            "vad_filter": False,
        }
        if self.language and self.language not in {"auto", "detect"}:
            transcribe_kwargs["language"] = self.language
        segments, _ = self.model.transcribe(audio_data, **transcribe_kwargs)
        text = "".join(s.text for s in segments).strip()

        if text:
            if self._should_drop_transcript_before_logging(text):
                self._reject_transcript("low-signal transcript", text, log_level="debug")
                return
            logger.info(f"[Voice Identified]: {text}")
            self._process_voice_text(text)
        else:
            logger.debug("[Whisper] No speech identified.")

    def _ensure_startup_input_device(self):
        if self._startup_device_selected or self.device_id is not None or self.device_label != "System default":
            return

        configured_device = self._configured_input_device()
        if configured_device is not None:
            try:
                selection = apply_input_device_selection(configured_device)
                self.device_id = selection.get("device")
                self.device_label = selection.get("label", "System default")
                self._startup_device_selected = True
                logger.info("Configured microphone selected: %s", self.device_label)
                self._emit_runtime_state()
                return
            except Exception as exc:
                logger.warning("Could not select configured microphone: %s", exc)

        try:
            devices = list_audio_input_devices()
        except Exception as exc:
            logger.warning("Could not inspect microphone devices: %s", exc)
            return

        if not devices:
            return

        preferred = choose_startup_input_device(devices) or devices[0]

        try:
            selection = apply_input_device_selection(preferred.target)
        except Exception as exc:
            logger.warning("Could not select startup microphone '%s': %s", preferred.label, exc)
            return

        self.device_id = selection.get("device")
        self.device_label = selection.get("label", preferred.label)
        self._startup_device_selected = True
        logger.info("Startup microphone selected: %s", self.device_label)
        self._emit_runtime_state()

    def _configured_input_device(self):
        config = getattr(self.app_core, "config", None)
        if config and hasattr(config, "get"):
            value = config.get("voice.input_device", None)
            if isinstance(value, (str, int, dict)) or value is None:
                return value
        return None

    def _resolve_stream_settings(self, sd):
        default_input = None
        try:
            default_input = sd.default.device[0]
        except Exception:
            pass

        candidates = []

        def add_candidate(device, label=""):
            key = (device, label)
            if key not in candidates:
                candidates.append(key)

        add_candidate(self.device_id, self.device_label)
        if self.device_id is None:
            add_candidate(None, "System default")
            if default_input is not None:
                add_candidate(default_input, f"Default input {default_input}")

        try:
            all_devices = list(sd.query_devices())
        except Exception:
            all_devices = []

        preferred_ids = []
        fallback_ids = []
        for index, device in enumerate(all_devices):
            if device.get("max_input_channels", 0) <= 0:
                continue
            name = device.get("name", f"Input {index}")
            lowered = name.lower()
            if lowered in {"default", "pipewire", "sysdefault"} or "monitor" in lowered:
                fallback_ids.append((index, name))
                continue
            if any(token in lowered for token in ("built-in", "analog", "mic", "microphone", "hda intel", "alc")):
                preferred_ids.append((index, name))
            else:
                fallback_ids.append((index, name))

        for index, label in preferred_ids + fallback_ids:
            add_candidate(index, label)

        attempted = []
        for device, label in candidates:
            info = self._query_input_device_info(sd, device, default_input)
            if not info:
                continue
            max_channels = max(1, int(info.get("max_input_channels", 1) or 1))
            sample_rates = self._candidate_sample_rates(info)
            channel_options = [1]
            if max_channels > 1:
                channel_options.append(min(2, max_channels))

            for sample_rate in sample_rates:
                for channels in channel_options:
                    blocksize = max(256, int(sample_rate * (0.15 if os.name == "nt" else 0.05)))
                    try:
                        sd.check_input_settings(
                            device=device,
                            samplerate=sample_rate,
                            channels=channels,
                            dtype="float32",
                        )
                        return {
                            "device": device,
                            "label": label or info.get("name", "System default"),
                            "samplerate": int(sample_rate),
                            "channels": channels,
                            "blocksize": blocksize,
                        }
                    except Exception as exc:
                        attempted.append(f"{label or device}:{sample_rate}Hz/{channels}ch ({exc})")
                        continue

        details = "; ".join(attempted[:6]) if attempted else "no compatible input candidates"
        raise RuntimeError(f"No compatible microphone input format found: {details}")

    def _query_input_device_info(self, sd, device, default_input):
        query_target = default_input if device is None and default_input is not None else device
        try:
            if query_target is None:
                return None
            return sd.query_devices(query_target, "input")
        except Exception:
            return None

    def _candidate_sample_rates(self, info):
        rates = [self.target_samplerate]
        default_rate = info.get("default_samplerate")
        try:
            if default_rate:
                rounded = int(default_rate)
                if rounded not in rates:
                    rates.append(rounded)
        except Exception:
            pass
        for fallback in (48000, 44100):
            if fallback not in rates:
                rates.append(fallback)
        return rates

    def _prepare_audio_for_transcription(self, audio_data):
        if isinstance(audio_data, np.ndarray) and audio_data.ndim == 2 and audio_data.shape[1] > 1:
            audio_data = np.mean(audio_data, axis=1)
        else:
            audio_data = np.asarray(audio_data, dtype=np.float32).reshape(-1)

        if self.stream_samplerate != self.target_samplerate:
            audio_data = self._resample_audio(audio_data, self.stream_samplerate, self.target_samplerate)

        return np.asarray(audio_data, dtype=np.float32)

    def _resample_audio(self, audio_data, source_rate, target_rate):
        if source_rate == target_rate or len(audio_data) == 0:
            return audio_data

        duration = len(audio_data) / float(source_rate)
        target_length = max(1, int(round(duration * target_rate)))
        source_positions = np.linspace(0.0, len(audio_data) - 1, num=len(audio_data), dtype=np.float32)
        target_positions = np.linspace(0.0, len(audio_data) - 1, num=target_length, dtype=np.float32)
        return np.interp(target_positions, source_positions, audio_data).astype(np.float32)
