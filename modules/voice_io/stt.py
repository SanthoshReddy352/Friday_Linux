import threading
import queue
import numpy as np
import os
import re
import time
import difflib
from core.logger import logger

# Words that trigger an immediate TTS interrupt (barge-in)
BARGE_IN_WORDS = {"stop", "wait", "cancel", "enough", "quiet", "silence", "pause"}


class STTEngine:
    def __init__(self, app_core):
        self.app_core = app_core
        self.is_listening = False
        self.model = None
        self.q = queue.Queue(maxsize=32)
        self.listen_thread = None
        self._init_lock = threading.Lock()
        self._initialized_event = threading.Event()
        self._initializing = False
        self.model_name = os.getenv("FRIDAY_WHISPER_MODEL", "base.en")
        self._drop_audio_until = 0.0

        # VAD settings
        self.silence_threshold = 0.005
        self.silence_duration = 0.35

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Audio callback — always runs, no hard gate
    # ------------------------------------------------------------------

    def audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Audio status: {status}")
        if time_module() < self._drop_audio_until:
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
                logger.debug("[STT] Dropping audio frame because processing is behind.")

    # ------------------------------------------------------------------
    # Listen loop
    # ------------------------------------------------------------------

    def _listen_loop(self):
        try:
            import sounddevice as sd
            samplerate = 16000
            blocksize = 800

            logger.info("Started continuous listening loop with Whisper.")
            with sd.InputStream(
                samplerate=samplerate, blocksize=blocksize, device=None,
                dtype='float32', channels=1, callback=self.audio_callback
            ):
                audio_buffer = []
                silence_frames = 0
                frames_per_second = samplerate / blocksize

                while self.is_listening:
                    try:
                        data = self.q.get(timeout=0.1)
                    except queue.Empty:
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
            logger.error(f"Error in continuous listening loop: {e}")
            self.is_listening = False

    # ------------------------------------------------------------------
    # Text processing — handles barge-in and normal commands
    # ------------------------------------------------------------------

    def _process_voice_text(self, text):
        text_clean = self._sanitize_text(text)

        # --- Barge-in detection (works even while TTS is playing) ---
        if self.app_core.is_speaking:
            words = set(text_clean.split())
            is_barge_in = bool(words & BARGE_IN_WORDS)
            # Also treat any wake-word prefix as barge-in
            is_wake = "friday" in text_clean
            is_new_request = self._is_new_user_request(text_clean)

            if is_barge_in or is_wake or is_new_request:
                logger.info(f"[STT] Barge-in detected: '{text_clean}'")
                tts = getattr(self.app_core, 'tts', None)
                if tts:
                    tts.stop()
                self._clear_audio_queue()
                self._drop_audio_until = time_module() + 0.12

                # If it was only a stop word, don't process further
                if is_barge_in and not is_wake:
                    return

                # Strip barge-in words and wake word, then process the rest
                for word in BARGE_IN_WORDS | {"friday", "hey"}:
                    text_clean = text_clean.replace(word, "")
                text_clean = self._sanitize_text(text_clean)
                if not text_clean:
                    return
            else:
                # TTS is speaking and no barge-in trigger — ignore
                logger.debug("[STT] Ignoring audio: TTS is speaking, no barge-in detected.")
                return

        # --- Normal wake-word stripping ---
        if "friday" in text_clean or "hey friday" in text_clean:
            logger.info("Wake word detected!")
            text_clean = self._sanitize_text(
                text_clean.replace("hey friday", "").replace("friday", "")
            )

        if not text_clean:
            return

        self.app_core.process_input(text_clean, source="voice")

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def start_listening(self):
        if not self.model and not self.initialize():
            logger.error("Cannot start listening: STT model not loaded.")
            return
        if self.is_listening:
            return
        self._clear_audio_queue()
        self.is_listening = True
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()
        logger.info("Microphone listening activated.")

    def stop_listening(self):
        self.is_listening = False
        self._clear_audio_queue()
        logger.info("Microphone listening deactivated.")

    def _sanitize_text(self, text):
        if not isinstance(text, str):
            return ""
        cleaned = text.lower().strip()
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _is_new_user_request(self, text_clean):
        if not text_clean or len(text_clean) < 3:
            return False

        # Single filler-like words during speech are usually noise or echo.
        if len(text_clean.split()) == 1 and text_clean in {"yeah", "okay", "ok", "hmm", "uh", "um"}:
            return False

        tts = getattr(self.app_core, "tts", None)
        if not tts:
            return True

        current_sentence = self._sanitize_text(getattr(tts, "current_sentence", "") or "")
        current_text = self._sanitize_text(getattr(tts, "current_text", "") or "")
        if not current_sentence and not current_text:
            return True

        references = [ref for ref in (current_sentence, current_text) if ref]
        if any(text_clean == ref for ref in references):
            return False
        if any(text_clean in ref for ref in references if len(text_clean) >= 5):
            return False

        similarities = [
            difflib.SequenceMatcher(None, text_clean, ref).ratio()
            for ref in references
        ]
        max_similarity = max(similarities, default=0.0)
        if max_similarity >= 0.7:
            return False

        return True

    def _clear_audio_queue(self):
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break


def time_module():
    return time.monotonic()
