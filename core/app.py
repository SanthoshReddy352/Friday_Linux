from core.assistant_context import AssistantContext
from core.config import ConfigManager
from core.context_store import ContextStore
from core.dialog_state import DialogState
from core.event_bus import EventBus
from core.system_capabilities import SystemCapabilities
from core.workflow_orchestrator import WorkflowOrchestrator
from core.router import CommandRouter
from core.plugin_manager import PluginManager
from core.logger import logger
from modules.system_control.app_launcher import configure_app_registry


class FridayApp:
    def __init__(self):
        self.config = ConfigManager()
        self.event_bus = EventBus()
        self.dialog_state = DialogState()
        self.assistant_context = AssistantContext()
        self.context_store = ContextStore()
        self.session_id = self.context_store.start_session({"entrypoint": "FridayApp"})
        self.assistant_context.bind_context_store(self.context_store, self.session_id)
        self.router = CommandRouter(self.event_bus)
        self.router.dialog_state = self.dialog_state
        self.router.assistant_context = self.assistant_context
        self.router.context_store = self.context_store
        self.router.session_id = self.session_id
        self.workflow_orchestrator = WorkflowOrchestrator(self)
        self.router.workflow_orchestrator = self.workflow_orchestrator
        self.capabilities = SystemCapabilities(self.config)
        self.plugin_manager = PluginManager(self)
        self.gui_callback = None
        self.is_speaking = False
        # TTS reference — set by VoiceIOPlugin after it constructs TextToSpeech
        self.tts = None
        self.stt = None
        self.media_control_mode = False

    def initialize(self):
        logger.info("Initializing FRIDAY...")
        self.config.load()
        self.capabilities.probe()
        configure_app_registry(self.capabilities)
        if hasattr(self.router, "refresh_runtime_settings"):
            self.router.refresh_runtime_settings()
        if hasattr(self.router, "model_manager"):
            self.router.model_manager.preload_requested_models()
        self.plugin_manager.load_plugins()
        logger.info("FRIDAY initialized successfully.")

    def shutdown(self):
        """Perform cleanup for a graceful exit."""
        logger.info("FRIDAY: Performing graceful shutdown...")
        
        # Stop STT Stream
        if self.stt and hasattr(self.stt, "shutdown"):
            self.stt.shutdown()
            
        # Stop TTS
        if self.tts:
            self.tts.stop()
            
        logger.info("FRIDAY: Cleanup complete.")

    def process_input(self, text, source="user"):
        """Process user input through the router."""
        if source != "voice" and self.is_speaking:
            tts = getattr(self, "tts", None)
            if tts:
                tts.stop()

        self.emit_message("user", text, source=source)
        
        # Auto-Pause Mic for voice commands to prevent noise during task execution
        if source == "voice":
            self.event_bus.publish("gui_toggle_mic", False)

        route_text = text
        if self.assistant_context and hasattr(self.assistant_context, "clean_user_text"):
            cleaned = self.assistant_context.clean_user_text(text, source=source)
            if cleaned:
                route_text = cleaned

        # Process through router
        response = self.router.process_text(route_text)
        
        # Post-process state changes
        decision = getattr(self.router, "last_routing_decision", None)
        if decision:
            # Enable media mode if we just started a browser media action
            if decision.tool_name in ("play_youtube", "play_youtube_music", "browser_media_control"):
                if not self.media_control_mode:
                    logger.info("[app] Entering Restricted Media Control Mode.")
                    self.media_control_mode = True
            
            # Disable media mode if we got a wake-up command
            if decision.tool_name == "enable_voice" and decision.args.get("wake_up"):
                if self.media_control_mode:
                    logger.info("[app] Exiting Restricted Media Control Mode.")
                    self.media_control_mode = False
                    response = "I'm awake! How can I help you?"

        if response:
            self.emit_assistant_message(response, source="friday")
        
        # Auto-Resume Mic after processing is complete
        if source == "voice":
            self.event_bus.publish("gui_toggle_mic", True)
            
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
        logger.info(f"[{role.upper()}]: {text}")
        self.assistant_context.record_message(role, text, source=payload["source"])
        if getattr(self, "context_store", None) and getattr(self, "session_id", None):
            self.context_store.append_turn(self.session_id, role, text, source=payload["source"])
        if self.gui_callback:
            self.gui_callback(payload)
        self.event_bus.publish("conversation_message", payload)
        return payload

    def emit_assistant_message(self, text, source="friday", speak=True, spoken_text=None):
        self.emit_message("assistant", text, source=source)
        # Skip TTS if the router already spoke during this request cycle
        # (e.g. LLM streaming preamble, "On it.", or tool acknowledgments)
        if speak and not getattr(self.router, "_voice_already_spoken", False):
            self.event_bus.publish("voice_response", spoken_text if spoken_text is not None else text)
