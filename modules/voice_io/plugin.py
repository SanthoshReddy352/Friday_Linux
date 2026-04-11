from core.plugin_manager import FridayPlugin
from core.logger import logger
import threading
from .stt import STTEngine
from .tts import TextToSpeech


class VoiceIOPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "VoiceIO"

        self.tts = TextToSpeech(app)
        self.stt = STTEngine(app)

        # Expose TTS on app_core so STT can call app_core.tts.stop()
        app.tts = self.tts

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
        # Strip any HTML markup that may come from the GUI display layer
        import re
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        self.tts.speak_chunked(clean_text)

    def start_listening(self, text=None):
        self.stt.start_listening()
        return "Voice listening enabled."

    def stop_listening(self, text=None):
        self.stt.stop_listening()
        return "Voice listening disabled."

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
