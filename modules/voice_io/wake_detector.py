import os

import numpy as np

from core.logger import logger


class WakeWordDetector:
    """Thin OpenWakeWord-compatible wake detector wrapper."""

    def __init__(self, model_path, threshold=0.5):
        self.model_path = model_path
        self.threshold = float(threshold)
        self.model = None
        self.available = False
        self.unavailable_reason = ""

    def initialize(self):
        if self.available:
            return True

        if not self.model_path:
            self.unavailable_reason = "wake model missing"
            return False

        if not os.path.exists(self.model_path):
            self.unavailable_reason = "wake model missing"
            return False

        try:
            from openwakeword.model import Model

            self.model = Model(wakeword_models=[self.model_path])
            self.available = True
            self.unavailable_reason = ""
            logger.info("Wake word model loaded: %s", self.model_path)
            return True
        except Exception as exc:
            self.unavailable_reason = f"wake detector unavailable: {exc}"
            logger.warning("[WakeWord] %s", self.unavailable_reason)
            return False

    def process_frame(self, audio_frame):
        if not self.initialize():
            return False

        audio = np.asarray(audio_frame, dtype=np.float32)
        if audio.ndim == 2 and audio.shape[1] > 1:
            audio = np.mean(audio, axis=1)
        else:
            audio = audio.reshape(-1)

        pcm16 = np.clip(audio, -1.0, 1.0)
        pcm16 = (pcm16 * 32767).astype(np.int16)

        try:
            predictions = self.model.predict(pcm16)
        except Exception as exc:
            self.available = False
            self.unavailable_reason = f"wake detector unavailable: {exc}"
            logger.warning("[WakeWord] %s", self.unavailable_reason)
            return False

        if isinstance(predictions, dict):
            return any(float(score) >= self.threshold for score in predictions.values())
        return False
