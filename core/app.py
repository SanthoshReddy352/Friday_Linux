import copy
import os

from core.assistant_context import AssistantContext
from core.capability_broker import CapabilityBroker
from core.capability_registry import CapabilityExecutor, CapabilityRegistry
from core.config import ConfigManager
from core.context_store import ContextStore
from core.conversation_agent import ConversationAgent
from core.delegation import DelegationManager
from core.dialog_state import DialogState
from core.event_bus import EventBus
from core.memory_broker import MemoryBroker
from core.persona_manager import PersonaManager
from core.speech_coordinator import SpeechCoordinator
from core.system_capabilities import SystemCapabilities
from core.tool_execution import OrderedToolExecutor
from core.turn_feedback import RuntimeMetrics, TurnFeedbackRuntime
from core.turn_manager import TurnManager
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
        self.capability_registry = CapabilityRegistry()
        self.capability_executor = CapabilityExecutor(self.capability_registry)
        self.runtime_metrics = RuntimeMetrics()
        self.turn_feedback = TurnFeedbackRuntime(self.event_bus, config=self.config, metrics=self.runtime_metrics)
        self.persona_manager = PersonaManager(self.context_store)
        self.context_store.set_active_persona(self.session_id, self.persona_manager.DEFAULT_PERSONA_ID)
        self.memory_broker = MemoryBroker(self.context_store, self.persona_manager)
        self.router = CommandRouter(self.event_bus)
        self.router.capability_registry = self.capability_registry
        self.router.dialog_state = self.dialog_state
        self.router.assistant_context = self.assistant_context
        self.router.context_store = self.context_store
        self.router.session_id = self.session_id
        self.workflow_orchestrator = WorkflowOrchestrator(self)
        self.router.workflow_orchestrator = self.workflow_orchestrator
        self.delegation_manager = DelegationManager(self)
        self.capability_broker = CapabilityBroker(self)
        self.ordered_tool_executor = OrderedToolExecutor(self)
        self.conversation_agent = ConversationAgent(self)
        self.turn_manager = TurnManager(self, self.conversation_agent)
        self.speech_coordinator = SpeechCoordinator(self)
        self.capabilities = SystemCapabilities(self.config)
        self.plugin_manager = PluginManager(self)
        self.gui_callback = None
        self.is_speaking = False
        # TTS reference — set by VoiceIOPlugin after it constructs TextToSpeech
        self.tts = None
        self.stt = None
        self.media_control_mode = False
        self._active_turn_record = None
        self._last_turn_speech_managed = False

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
        
        # Hard exit to ensure all lingering non-daemon threads from plugins are terminated.
        # This is necessary because some skills might have background workers that
        # don't respond to standard signals, which would otherwise keep the process alive
        # and prevent the snap detector from relaunching.
        os._exit(0)

    def process_input(self, text, source="user"):
        """Process user input through the router."""
        if source != "voice" and self.is_speaking:
            tts = getattr(self, "tts", None)
            if tts:
                tts.stop()

        if hasattr(self.router, "_voice_already_spoken"):
            self.router._voice_already_spoken = False

        self.emit_message("user", text, source=source)
        
        # Auto-Pause Mic for voice commands to prevent noise during task execution
        if source == "voice":
            self.event_bus.publish("gui_toggle_mic", False)
            if self.stt and hasattr(self.stt, "set_processing_state"):
                self.stt.set_processing_state(True)

        try:
            route_text = text
            if self.assistant_context and hasattr(self.assistant_context, "clean_user_text"):
                cleaned = self.assistant_context.clean_user_text(text, source=source)
                if cleaned:
                    route_text = cleaned

            # Process through the main conversation control plane.
            self._last_turn_speech_managed = False
            response = self.turn_manager.handle_turn(route_text, source=source)
            
            # Post-process state changes
            decision = getattr(self.router, "last_routing_decision", None)
            if decision:
                # Enable media mode if we just started a browser media action
                if decision.tool_name in ("play_youtube", "play_youtube_music", "browser_media_control"):
                    if not self.media_control_mode:
                        logger.info("[app] Entering Restricted Media Control Mode.")
                        self.media_control_mode = True
                        self.event_bus.publish("media_control_mode_changed", {"active": True})
                
                # Disable media mode if we got a wake-up command
                if decision.tool_name == "enable_voice" and decision.args.get("wake_up"):
                    if self.media_control_mode:
                        logger.info("[app] Exiting Restricted Media Control Mode.")
                        self.media_control_mode = False
                        self.event_bus.publish("media_control_mode_changed", {"active": False})
                        response = "I'm awake! How can I help you?"

            if response:
                self.emit_assistant_message(
                    response,
                    source="friday",
                    speak=not getattr(self, "_last_turn_speech_managed", False),
                )
            return response
        finally:
            # Auto-Resume Mic after processing is complete
            if source == "voice":
                if self.stt and hasattr(self.stt, "set_processing_state"):
                    self.stt.set_processing_state(False)
                self.event_bus.publish("gui_toggle_mic", self.should_resume_voice_after_turn())

    def get_listening_mode(self):
        mode = ""
        if self.config and hasattr(self.config, "get"):
            mode = str(self.config.get("conversation.listening_mode", "persistent") or "").strip().lower().replace("-", "_")
        if mode not in {"persistent", "wake_word", "on_demand", "manual"}:
            mode = "persistent"
        return mode

    def set_listening_mode(self, mode):
        mode = str(mode or "").strip().lower().replace("-", "_")
        aliases = {
            "ondemand": "on_demand",
            "on demand": "on_demand",
            "always_on": "persistent",
            "always on": "persistent",
            "wakeword": "wake_word",
            "wake word": "wake_word",
            "wake": "wake_word",
            "off": "manual",
        }
        mode = aliases.get(mode, mode)
        if mode not in {"persistent", "wake_word", "on_demand", "manual"}:
            return self.get_listening_mode()

        if self.config and hasattr(self.config, "set"):
            self.config.set("conversation.listening_mode", mode)
            if hasattr(self.config, "save"):
                self.config.save()
        else:
            config_payload = getattr(self.config, "config", None)
            if isinstance(config_payload, dict):
                next_config = copy.deepcopy(config_payload)
                next_config.setdefault("conversation", {})["listening_mode"] = mode
                self.config.config = next_config

        self.event_bus.publish("listening_mode_changed", {"mode": mode})
        if mode in {"persistent", "wake_word"}:
            self.event_bus.publish("gui_toggle_mic", True)
        else:
            self.event_bus.publish("gui_toggle_mic", False)
        return mode

    def should_auto_start_voice(self):
        return self.get_listening_mode() in {"persistent", "wake_word"}

    def should_resume_voice_after_turn(self):
        return self.get_listening_mode() in {"persistent", "wake_word"}

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
        already_spoken = getattr(self.router, "_voice_already_spoken", False)
        if speak and not already_spoken:
            self.event_bus.publish("voice_response", spoken_text if spoken_text is not None else text)
        if hasattr(self.router, "_voice_already_spoken"):
            self.router._voice_already_spoken = False
