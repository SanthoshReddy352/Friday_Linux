from core.config import ConfigManager
from core.dialog_state import DialogState
from core.event_bus import EventBus
from core.router import CommandRouter
from core.plugin_manager import PluginManager
from core.logger import logger


class FridayApp:
    def __init__(self):
        self.config = ConfigManager()
        self.event_bus = EventBus()
        self.dialog_state = DialogState()
        self.router = CommandRouter(self.event_bus)
        self.router.dialog_state = self.dialog_state
        self.plugin_manager = PluginManager(self)
        self.gui_callback = None
        self.is_speaking = False
        # TTS reference — set by VoiceIOPlugin after it constructs TextToSpeech
        self.tts = None

    def initialize(self):
        logger.info("Initializing FRIDAY...")
        self.config.load()
        self.plugin_manager.load_plugins()
        logger.info("FRIDAY initialized successfully.")

    def process_input(self, text, source="user"):
        """Process user input through the router."""
        self.emit_message("user", text, source=source)
        response = self.router.process_text(text)
        if response:
            self.emit_assistant_message(response, source="friday")
        return response

    def set_gui_callback(self, callback):
        """Allows GUI to register a callback to receive conversation payloads."""
        self.gui_callback = callback

    def emit_message(self, role, text, source=None):
        payload = {
            "role": role,
            "text": text,
            "source": source or role,
        }
        if self.gui_callback:
            self.gui_callback(payload)
        self.event_bus.publish("conversation_message", payload)
        return payload

    def emit_assistant_message(self, text, source="friday", speak=True, spoken_text=None):
        self.emit_message("assistant", text, source=source)
        if speak:
            self.event_bus.publish("voice_response", spoken_text if spoken_text is not None else text)
