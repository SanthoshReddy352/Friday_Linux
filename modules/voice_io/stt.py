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
from .audio_devices import apply_input_device_selection, list_audio_input_devices

# Words that trigger an immediate TTS interrupt (barge-in)
BARGE_IN_WORDS = {"stop", "wait", "cancel", "enough", "quiet", "silence", "pause"}
FILLER_ONLY_WORDS = {"please", "yeah", "yes", "okay", "ok", "go", "uh", "um", "hmm", "hm"}

# Whitelist for restricted media control mode
MEDIA_COMMAND_WHITELIST = {
    "play", "pause", "resume", "stop", "next", "previous", "skip", 
    "forward", "back", "backward", "revert", "rewind", "seconds", "secs", "video",
    "wake", "up", "friday"
}

class STTEngine:
    def __init__(self, app_core):
        self.app_core = app_core
        self.is_listening = False  # Software gate (False = mute/ignore)
        self._loop_active = False # Underlying hardware stream state
        self.model = None
        self.q = queue.Queue(maxsize=32)
        self.listen_thread = None
        self._init_lock = threading.Lock()
        self._initialized_event = threading.Event()
        self._initializing = False
        self.model_name = os.getenv("FRIDAY_WHISPER_MODEL", "base.en")
        self._drop_audio_until = 0.0
        self.device_id = None # Default device
        self.device_label = "System default"
        self.target_samplerate = 16000
        self.stream_samplerate = self.target_samplerate
        self.stream_channels = 1
        self.stream_blocksize = 800
        self._startup_device_selected = False
        self.max_utterance_duration = float(os.getenv("FRIDAY_MAX_UTTERANCE_S", "4.0"))
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
            logger.info(f"Initializing faster-whisper {self.model_name} model...")
            self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
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
        threading.Thread(target=self.initialize, daemon=True).start()

    def audio_callback(self, indata, frames, time_info, status):
        """Always running hardware callback."""
        if status:
            logger.warning(f"Audio status: {status}")
        
        # Software Gate: Only put data into queue if we are actively 'listening'
        if not self.is_listening:
            return

        # Periodic profile check (Adaptive VAD)
        now = time.monotonic()
        if now - self._last_profile_check > self.profile_check_interval:
            self._update_audio_profile()
            self._last_profile_check = now

        if now < self._drop_audio_until:
            return

        rms = float(np.sqrt(np.mean(indata ** 2)))
        if self.app_core.is_speaking:
            self._maybe_interrupt_for_live_speech(rms)
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
                frames_per_second = self.stream_samplerate / self.stream_blocksize

                while self._loop_active:
                    try:
                        # We still wait on the queue, but the callback only fills it if is_listening is True
                        data = self.q.get(timeout=0.1)
                    except queue.Empty:
                        continue
                        
                    # If we somehow got data while not listening, clear it
                    if not self.is_listening:
                        audio_buffer = []
                        silence_frames = 0
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
                    has_enough_audio = buffer_duration >= self.min_utterance_duration
                    hit_silence_boundary = silence_frames > (self.silence_duration * frames_per_second)
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
            return

        # Strict Mode: Speaker feedback suppression
        # If media is playing on speakers, we are much more critical of the input
        if self.system_media_active and not self.is_bluetooth_active:
            is_wake_up = "friday" in text_clean or "wake up" in text_clean
            is_media_cmd = bool(set(text_clean.split()) & MEDIA_COMMAND_WHITELIST)
            
            # If it's just a few words of junk that isn't a command or wake word, drop it
            if not (is_wake_up or is_media_cmd):
                # We also drop if it's too short (less than 2 words) as it's likely a speaker blip
                if len(text_clean.split()) < 2:
                    logger.info(f"[STT] Ignored short noise '{text_clean}' (Required 'Friday' trigger because media is active).")
                    return
                # If it's longer but doesn't mention friday, it might be the video audio
                if "friday" not in text_clean:
                    logger.info(f"[STT] Ignored '{text_clean}' (Missing 'Friday' trigger while media is active).")
                    return

        # Restricted Media Mode: Discard if not a whitelist command
        media_mode = getattr(self.app_core, "media_control_mode", False)
        if media_mode:
            words = set(text_clean.split())
            is_media_cmd = bool(words & MEDIA_COMMAND_WHITELIST)
            is_wake_up = "wake up" in text_clean
            
            if not (is_media_cmd or is_wake_up):
                logger.debug(f"[STT] Dropping non-media command in restricted mode: '{text_clean}'")
                return
            logger.info(f"[STT] Whitelist match in media mode: '{text_clean}'")

        # Basic barge-in logic
        if self.app_core.is_speaking:
            text_clean_barge = text_clean
            # In Speaker mode, we strictly require the 'Friday' keyword to avoid
            # accidental triggers from speaker reflections or room noise.
            if not self.is_bluetooth_active and "friday" not in text_clean:
                return

            words = set(text_clean.split())
            if bool(words & BARGE_IN_WORDS) or "friday" in text_clean or self._looks_like_fresh_command(text_clean):
                logger.info(f"[STT] Barge-in detected during speech: '{text_clean}'")
                if self.app_core.tts:
                    self.app_core.tts.stop()
                self._clear_audio_queue()
                self._drop_audio_until = time.monotonic() + 0.15

                for word in BARGE_IN_WORDS | {"friday", "hey"}:
                    text_clean = text_clean.replace(word, "")
                text_clean = self._clean_command_text(text_clean)
                if not text_clean or text_clean in FILLER_ONLY_WORDS:
                    return
            else:
                return

        if "friday" in text_clean or "hey friday" in text_clean:
            text_clean = self._clean_command_text(
                text_clean.replace("hey friday", "").replace("friday", "")
            )
        else:
            text_clean = self._clean_command_text(text_clean)

        if not text_clean:
            return

        self.app_core.process_input(text_clean, source="voice")

    def _maybe_interrupt_for_live_speech(self, rms):
        if not self.app_core.is_speaking or not self.use_rms_barge_in:
            self._barge_in_frame_count = 0
            return

        tts = getattr(self.app_core, "tts", None)
        now = time.monotonic()
        speaking_started_at = getattr(tts, "speaking_started_at", 0.0) if tts else 0.0
        if speaking_started_at and (now - speaking_started_at) < self.barge_in_grace_period_s:
            self._barge_in_frame_count = 0
            return

        if rms >= self.barge_in_rms_threshold:
            self._barge_in_frame_count += 1
        else:
            self._barge_in_frame_count = 0
            return

        if self._barge_in_frame_count < self.barge_in_trigger_frames:
            return

        self._barge_in_frame_count = 0
        if tts:
            logger.info("[STT] Live barge-in detected from voice activity.")
            self._clear_audio_queue()
            self._drop_audio_until = now + self.barge_in_post_stop_drop_s
            tts.stop()

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

    def start_listening(self):
        """Lightweight software gate activation."""
        if not self.model and not self.initialize():
            logger.error("Cannot start listening: STT model or hardware stream failed.")
            return False
            
        if self.is_listening:
            return True

        request_id = self._next_listen_request_id()
        if self.app_core.is_speaking:
            logger.info("Microphone gate will open after current speech finishes.")
            threading.Thread(
                target=self._complete_listen_when_ready,
                args=(request_id,),
                daemon=True,
            ).start()
            return True

        self._activate_listening(request_id)
        return True

    def stop_listening(self):
        """Lightweight software gate deactivation."""
        self._next_listen_request_id()
        self.is_listening = False
        self._barge_in_frame_count = 0
        self._clear_audio_queue()
        logger.info("Microphone software gate CLOSED.")
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

        # We must restart the actual hardware stream if the device changes
        self._loop_active = False
        if self.listen_thread and self.listen_thread.is_alive():
            self.listen_thread.join(timeout=1.0)
        time.sleep(0.5)
        self._start_hardware_stream()

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

    def _clear_audio_queue(self):
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    def _activate_listening(self, request_id=None):
        if request_id is not None and request_id != self._current_listen_request_id():
            return
        self._clear_audio_queue()
        self._barge_in_frame_count = 0
        self._drop_audio_until = max(self._drop_audio_until, time.monotonic() + self.listen_resume_delay_s)
        self.is_listening = True
        logger.info("Microphone software gate OPENED.")

    def _complete_listen_when_ready(self, request_id):
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if request_id != self._current_listen_request_id():
                return
            if not self.app_core.is_speaking:
                self._activate_listening(request_id)
                return
            time.sleep(0.05)

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
            result = subprocess.run([wpctl, "status"], capture_output=True, text=True, check=False)
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
            streams_section = False
            for line in status.splitlines():
                if "Streams:" in line:
                    streams_section = True
                    continue
                if "[active]" in line and "python" not in line and "stt" not in line:
                    is_media_active = True
                    break

            if is_bt != self.is_bluetooth_active or is_media_active != self.system_media_active:
                self.is_bluetooth_active = is_bt
                self.system_media_active = is_media_active
                self._apply_adaptive_thresholds()
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
            profile_name += " + ACTIVE MEDIA"

        logger.info(f"[STT] Adaptive VAD profile updated: {profile_name}")
        logger.debug(f"[STT] Thresholds: silence={self.silence_threshold:.4f}, barge_in={self.barge_in_rms_threshold:.4f}")

    def _transcribe_buffer(self, audio_buffer):
        audio_data = np.concatenate(audio_buffer, axis=0)
        audio_data = self._prepare_audio_for_transcription(audio_data)

        logger.debug("[Whisper] Transcribing...")
        segments, _ = self.model.transcribe(
            audio_data,
            beam_size=1,
            best_of=1,
            patience=1,
            language="en",
            condition_on_previous_text=False,
            vad_filter=False,
        )
        text = "".join(s.text for s in segments).strip()

        if text:
            logger.info(f"[Voice Identified]: {text}")
            self._process_voice_text(text)
        else:
            logger.debug("[Whisper] No speech identified.")

    def _ensure_startup_input_device(self):
        if self._startup_device_selected or self.device_id is not None or self.device_label != "System default":
            return

        try:
            devices = list_audio_input_devices()
        except Exception as exc:
            logger.warning("Could not inspect microphone devices: %s", exc)
            return

        if not devices:
            return

        preferred = next((device for device in devices if device.is_default), None)
        if preferred is None:
            preferred = next((device for device in devices if device.backend == "pipewire"), None)
        if preferred is None:
            preferred = next(
                (
                    device for device in devices
                    if any(token in device.label.lower() for token in ("built-in", "analog", "microphone", "mic"))
                ),
                None,
            )
        if preferred is None:
            preferred = devices[0]

        try:
            selection = apply_input_device_selection(preferred.target)
        except Exception as exc:
            logger.warning("Could not select startup microphone '%s': %s", preferred.label, exc)
            return

        self.device_id = selection.get("device")
        self.device_label = selection.get("label", preferred.label)
        self._startup_device_selected = True
        logger.info("Startup microphone selected: %s", self.device_label)

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
                    blocksize = max(256, int(sample_rate * 0.05))
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
