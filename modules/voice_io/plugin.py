from core.plugin_manager import FridayPlugin
from core.logger import logger
import threading
import re
from .stt import STTEngine
from .tts import TextToSpeech


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def sanitize_for_speech(text):
    if not text:
        return ""

    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = re.sub(r"```[a-zA-Z0-9_-]*", "", cleaned).replace("```", "")
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[*+-]\s+", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*\d+\.\s+", "", cleaned)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"[_*~]", "", cleaned)
    cleaned = EMOJI_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


class VoiceIOPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "VoiceIO"

        self.tts = TextToSpeech(app)
        self.stt = STTEngine(app)

        # Expose TTS on app_core so STT can call app_core.tts.stop()
        app.tts = self.tts
        app.stt = self.stt

        self.on_load()

    def on_load(self):
        # Speak all voice_response events using chunked (interruptible) TTS
        self.app.event_bus.subscribe("voice_response", self.handle_speak)

        # Voice toggle commands
        self.app.router.register_tool({
            "name": "enable_voice",
            "description": "Enable the microphone and start listening for voice commands.",
            "parameters": {}
        }, lambda t, a: self.start_listening())

        self.app.router.register_tool({
            "name": "disable_voice",
            "description": "Disable the microphone and stop listening for voice commands.",
            "parameters": {}
        }, lambda t, a: self.stop_listening())

        # GUI mic toggle
        self.app.event_bus.subscribe("gui_toggle_mic", self.toggle_mic)

        # Warm voice dependencies in the background so first-use latency is lower.
        threading.Thread(target=self._warm_voice_stack, daemon=True).start()

        logger.info("VoiceIOPlugin loaded.")

    def handle_speak(self, text):
        if not text:
            return
        clean_text = sanitize_for_speech(text)
        if not clean_text:
            return
        self.tts.speak_chunked(clean_text)

    def start_listening(self, text=None):
        return "Voice listening enabled." if self.stt.start_listening() else "I couldn't enable voice listening."

    def stop_listening(self, text=None):
        return "Voice listening disabled." if self.stt.stop_listening() else "I couldn't disable voice listening."

    def toggle_mic(self, state):
        """Called from the GUI toggle switch."""
        if state:
            self.stt.start_listening()
        else:
            self.stt.stop_listening()

    def _warm_voice_stack(self):
        self.tts.warm_up()
        self.stt.warm_up()


def setup(app):
    return VoiceIOPlugin(app)
