import threading
import queue
import numpy as np
import os
import re
import time
import difflib
from core.logger import logger
from .audio_devices import apply_input_device_selection

# Words that trigger an immediate TTS interrupt (barge-in)
BARGE_IN_WORDS = {"stop", "wait", "cancel", "enough", "quiet", "silence", "pause"}
FILLER_ONLY_WORDS = {"please", "yeah", "yes", "okay", "ok", "go", "uh", "um", "hmm", "hm"}

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

        # VAD settings - tuned for background noise rejection
        self.silence_threshold = 0.008
        self.silence_duration = 0.6
        self.barge_in_rms_threshold = float(os.getenv("FRIDAY_BARGE_IN_RMS", "0.045"))
        self.barge_in_trigger_frames = max(1, int(os.getenv("FRIDAY_BARGE_IN_FRAMES", "4")))
        self.barge_in_grace_period_s = float(os.getenv("FRIDAY_BARGE_IN_GRACE_S", "0.7"))
        self.barge_in_post_stop_drop_s = float(os.getenv("FRIDAY_BARGE_IN_POST_STOP_DROP_S", "0.12"))
        self._barge_in_frame_count = 0

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

        if time.monotonic() < self._drop_audio_until:
            return

        rms = float(np.sqrt(np.mean(indata ** 2)))
        if self.app_core.is_speaking:
            self._maybe_interrupt_for_live_speech(rms)
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
            samplerate = 16000
            blocksize = 800

            logger.info(f"Opening persistent sd.InputStream on device {self.device_id}...")
            # We wrap the InputStream in a try/except because some devices might not be available
            with sd.InputStream(
                samplerate=samplerate, blocksize=blocksize, device=self.device_id,
                dtype='float32', channels=1, callback=self.audio_callback
            ):
                audio_buffer = []
                silence_frames = 0
                frames_per_second = samplerate / blocksize

                while self._loop_active:
                    try:
                        # We still wait on the queue, but the callback only fills it if is_listening is True
                        data = self.q.get(timeout=0.1)
                    except queue.Empty:
                        continue
                        
                    # If we somehow got data while not listening, clear it
                    if not self.is_listening:
                        audio_buffer = []
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

                        if (silence_frames > (self.silence_duration * frames_per_second)
                                and len(audio_buffer) > frames_per_second):
                            audio_data = np.concatenate(audio_buffer).flatten()
                            audio_buffer = []
                            silence_frames = 0

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

        except Exception as e:
            logger.error(f"Error in persistent listening loop: {e}")
            self._loop_active = False

    def _process_voice_text(self, text):
        text_clean = self._sanitize_text(text)

        # Basic barge-in logic
        if self.app_core.is_speaking:
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
        if not self.app_core.is_speaking:
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
            
        self._clear_audio_queue()
        self._barge_in_frame_count = 0
        self.is_listening = True
        logger.info("Microphone software gate OPENED.")
        return True

    def stop_listening(self):
        """Lightweight software gate deactivation."""
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
