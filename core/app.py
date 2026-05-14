import copy
import os
import sys

from core.assistant_context import AssistantContext
from core.bootstrap import LifecycleManager
from core.capability_broker import CapabilityBroker
from core.kernel import ConsentService, PermissionService
from core.capability_registry import CapabilityExecutor, CapabilityRegistry
from core.config import ConfigManager
from core.context_store import ContextStore
from core.conversation_agent import ConversationAgent
from core.delegation import DelegationManager
from core.dialogue_manager import DialogueManager
from core.dialog_state import DialogState
from core.event_bus import EventBus
from core.memory_broker import MemoryBroker
from core.memory_service import MemoryService
from core.persona_manager import PersonaManager
from core.reasoning import ModelRouter, GraphCompiler
from core.reasoning.route_scorer import RouteScorer
from core.result_cache import ResultCache
from core.speech_coordinator import SpeechCoordinator
from core.system_capabilities import SystemCapabilities
from core.planning import (
    IntentEngine,
    PlannerEngine,
    TurnOrchestrator,
    WorkflowCoordinator,
)
from core.task_graph_executor import TaskGraphExecutor
from core.tool_execution import OrderedToolExecutor
from core.tracing import configure_trace_export
from core.resource_monitor import ResourceMonitor
from core.session_rag import SessionRAG
from core.turn_feedback import RuntimeMetrics, TurnFeedbackRuntime
from core.turn_manager import TurnManager
from core.task_runner import TaskRunner
from core.workflow_orchestrator import WorkflowOrchestrator
from core.router import CommandRouter
from core.extensions.loader import ExtensionLoader
from core.routing_state import RoutingState
from core.response_finalizer import ResponseFinalizer
from core.model_output import strip_model_artifacts
from core.logger import logger


class FridayApp:
    def __init__(self):
        self.config = ConfigManager()
        self.event_bus = EventBus()
        self.dialog_state = DialogState()
        self.assistant_context = AssistantContext()
        self.context_store = ContextStore()
        self.session_id = self.context_store.start_session({"entrypoint": "FridayApp"})
        self.assistant_context.bind_context_store(self.context_store, self.session_id)
        self.session_rag = SessionRAG()
        self.assistant_context.session_rag = self.session_rag
        self.capability_registry = CapabilityRegistry()
        self.capability_executor = CapabilityExecutor(self.capability_registry)
        self.runtime_metrics = RuntimeMetrics()
        self.turn_feedback = TurnFeedbackRuntime(self.event_bus, config=self.config, metrics=self.runtime_metrics)
        self.persona_manager = PersonaManager(self.context_store)
        self.context_store.set_active_persona(self.session_id, self.persona_manager.DEFAULT_PERSONA_ID)
        self.memory_broker = MemoryBroker(self.context_store, self.persona_manager)
        # Phase 2 (v2): unified memory facade. Hides ContextStore/MemoryBroker
        # behind one read/write surface so the storage layer can evolve
        # without touching every caller. New code targets app.memory_service;
        # legacy app.context_store access remains valid during the migration.
        # Phase 6: Mem0 components wired in after server probe (see further below)
        self.memory_service = MemoryService(self.context_store, self.memory_broker)
        # Phase 3: kernel services — stateless, injected into broker/agent
        self.consent_service = ConsentService(self.config)
        self.permission_service = PermissionService()
        # Phase 1: shared routing services — router writes, executors read
        self.routing_state = RoutingState()
        self.response_finalizer = ResponseFinalizer(self)
        self.router = CommandRouter(self.event_bus)
        self.router.capability_registry = self.capability_registry
        self.router.routing_state = self.routing_state
        self.router.response_finalizer = self.response_finalizer
        self.router.dialog_state = self.dialog_state
        self.router.assistant_context = self.assistant_context
        self.router.context_store = self.context_store
        self.router.session_id = self.session_id
        self.workflow_orchestrator = WorkflowOrchestrator(self)
        self.router.workflow_orchestrator = self.workflow_orchestrator
        self.delegation_manager = DelegationManager(self)
        self.capability_broker = CapabilityBroker(self)
        self.ordered_tool_executor = OrderedToolExecutor(self)
        # Phase 4 (v2): DAG-based parallel executor. Selected via the
        # `routing.execution_engine: "parallel"` config flag (default
        # "ordered" stays current behavior). Single-step plans always
        # forward to ordered to skip pool overhead.
        self.task_graph_executor = TaskGraphExecutor(self)
        # Phase 3 (v2): WorkflowCoordinator + PlannerEngine can be built
        # now (their deps already exist). IntentEngine and TurnOrchestrator
        # need route_scorer / intent_recognizer which are constructed a
        # few lines below — wired further down.
        self.planner_engine = PlannerEngine(self.capability_broker)
        self.workflow_coordinator = WorkflowCoordinator(
            self.workflow_orchestrator, self.context_store
        )
        self.intent_engine = None
        self.turn_orchestrator = None
        self.conversation_agent = ConversationAgent(self)
        self.turn_manager = TurnManager(self, self.conversation_agent)
        self.speech_coordinator = SpeechCoordinator(self)
        self.capabilities = SystemCapabilities(self.config)
        self.extension_loader = ExtensionLoader(self)
        # Phase 5: expose IntentRecognizer directly (avoids going through router)
        self.intent_recognizer = self.router.intent_recognizer
        # Phase 5: RouteScorer searches both router tools AND capability_registry
        # The lambda is evaluated at route-time so newly-registered extensions are visible.
        self.route_scorer = RouteScorer(lambda: self.router.tools + self._registry_routes())
        # Phase 3 (v2): now that intent_recognizer + route_scorer exist,
        # build the IntentEngine adapter and the TurnOrchestrator.
        self.intent_engine = IntentEngine(self.intent_recognizer, self.route_scorer)
        self.turn_orchestrator = TurnOrchestrator(
            self,
            intent_engine=self.intent_engine,
            planner_engine=self.planner_engine,
            workflow_coordinator=self.workflow_coordinator,
            memory_broker=self.memory_broker,
        )
        # Phase 5 (v2): expose model_manager directly so callers (research,
        # planner, future extensions) can fetch per-domain inference locks
        # without depending on CommandRouter as a back-channel.
        self.model_manager = self.router.model_manager
        # Phase 5: ModelRouter for LLM-based tool selection
        self.model_router = ModelRouter(
            self.router.model_manager,
            timeout_ms=self.router.tool_timeout_ms,
            max_tokens=self.router.tool_max_tokens,
            target_max_tokens=self.router.tool_target_max_tokens,
            top_p=self.router.tool_top_p,
            json_response=self.router.tool_json_response,
        )
        # Phase 6: GraphCompiler for LangGraph-based execution (falls back to ordered)
        self.graph_compiler = GraphCompiler(self)
        # Phase 9: DialogueManager for contextual acks and tone adaptation
        self.dialogue_manager = DialogueManager(self.config)
        # Phase 10: ResultCache for TTL-based capability result caching
        self.result_cache = ResultCache()
        # Task runner: each voice command runs in a daemon thread so the STT
        # listen-loop is never blocked and commands can be cancelled.
        self.task_runner = TaskRunner(self)
        # Phase 2: lifecycle manager owns ordered teardown
        self.lifecycle = LifecycleManager()
        self.gui_callback = None
        self.is_speaking = False
        # TTS reference — set by VoiceIOPlugin after it constructs TextToSpeech
        self.tts = None
        self.stt = None
        self.media_control_mode = False
        self._active_turn_record = None
        # Phase 1 (v2): unified per-turn ephemeral state. Set by TurnManager
        # at turn start, cleared in the finally branch.
        self.current_turn_context = None
        self._last_turn_speech_managed = False
        self._shutdown_requested = False
        self._turn_lock = __import__("threading").Lock()
        self.resource_monitor = ResourceMonitor()

        # Phase 6: Mem0 memory integration — boot extraction server and build client
        from core.mem0_client import build_mem0_client
        from core.memory_extractor import TurnGatedMemoryExtractor

        _mem0_cfg = self.config.get("memory", {}) if hasattr(self.config, "get") else {}
        self._mem0_client = None
        self._mem0_extractor = None

        if _mem0_cfg.get("enabled", False):
            if self._start_mem0_server():
                self._mem0_client = build_mem0_client(_mem0_cfg)
                if self._mem0_client:
                    self._mem0_extractor = TurnGatedMemoryExtractor(
                        self._mem0_client, self.turn_feedback
                    )

        # Rebuild MemoryService with Mem0 components (replaces the Phase 2 instance above)
        self.memory_service = MemoryService(
            self.context_store,
            self.memory_broker,
            mem0_client=self._mem0_client,
            extractor=self._mem0_extractor,
        )

    def _start_mem0_server(self) -> bool:
        """Boot llama.cpp extraction server if memory.enabled and auto_start are set."""
        import subprocess
        import time
        import urllib.request

        cfg = self.config.get("memory", {}) if hasattr(self.config, "get") else {}
        if not cfg.get("enabled", False):
            return False
        srv_cfg = cfg.get("extraction_server", {})
        if not srv_cfg.get("auto_start", False):
            return False

        model_path = srv_cfg.get("model_path", "")
        port = int(srv_cfg.get("port", 8181))
        host = srv_cfg.get("host", "127.0.0.1")

        if not os.path.exists(model_path):
            logger.warning("[mem0] Model not found: %s — skipping extraction server.", model_path)
            return False

        try:
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "llama_cpp.server",
                    "--model", model_path,
                    "--n_ctx", str(srv_cfg.get("n_ctx", 1024)),
                    "--n_batch", str(srv_cfg.get("n_batch", 128)),
                    "--port", str(port),
                    "--host", host,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(16):
                time.sleep(0.5)
                try:
                    urllib.request.urlopen(f"http://{host}:{port}/v1/models", timeout=1)
                    logger.info("[mem0] Extraction server ready at port %d (PID %d).", port, proc.pid)
                    return True
                except Exception:
                    continue
            logger.warning("[mem0] Extraction server did not start in time.")
            return False
        except Exception as exc:
            logger.warning("[mem0] Failed to start extraction server: %s", exc)
            return False

    def initialize(self):
        logger.info("Initializing FRIDAY...")
        self.config.load()
        self.capabilities.probe()
        try:
            from modules.system_control.app_launcher import configure_app_registry  # noqa: PLC0415
            configure_app_registry(self.capabilities)
        except Exception as e:
            logger.warning("App registry configuration failed: %s", e)
        if hasattr(self.router, "refresh_runtime_settings"):
            self.router.refresh_runtime_settings()
        if hasattr(self.router, "model_manager"):
            self.router.model_manager.preload_requested_models()
        self.extension_loader.load_all()
        # Phase 10: configure trace export path
        _data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        configure_trace_export(os.path.join(_data_dir, "traces.jsonl"))
        logger.info("FRIDAY initialized successfully.")

    def shutdown(self):
        """Perform cleanup for a graceful exit.

        Stop order (reverse of start):
          1. STT stream  — stops audio capture immediately
          2. TTS         — drains the speak queue
          3. All lifecycle-registered services (reverse registration order)
          4. sys.exit(0) — clean exit; all threads are daemon so Python does
                           not need to wait for them

        Previously used os._exit(0) which bypassed Python's atexit handlers
        and prevented orderly cleanup. sys.exit raises SystemExit, which
        propagates through the GUI event loop (Qt catches it) and then to the
        interpreter, giving atexit handlers a chance to run.
        """
        if self._shutdown_requested:
            return
        self._shutdown_requested = True
        logger.info("FRIDAY: Performing graceful shutdown...")

        if self.stt and hasattr(self.stt, "shutdown"):
            try:
                self.stt.shutdown()
            except Exception:
                logger.exception("[shutdown] STT shutdown error")

        if self.tts and hasattr(self.tts, "stop"):
            try:
                self.tts.stop()
            except Exception:
                logger.exception("[shutdown] TTS stop error")

        self.lifecycle.stop_all()
        logger.info("FRIDAY: Cleanup complete.")
        sys.exit(0)

    _RAG_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt", ".html", ".csv"}

    def _resolve_rag_file_path(self, text: str) -> "str | None":
        """Return a local file path if *text* looks like a supported document, else None."""
        from urllib.parse import urlparse, unquote
        t = (text or "").strip()
        candidates = []
        if t.startswith("file://"):
            try:
                candidates.append(unquote(urlparse(t).path))
            except Exception:
                pass
        if t.startswith("/"):
            candidates.append(t)
        for path in candidates:
            path = path.strip()
            if os.path.isfile(path) and os.path.splitext(path)[1].lower() in self._RAG_EXTENSIONS:
                return path
        return None

    def process_input(self, text, source="user"):
        """Process user input.

        Voice commands are dispatched to TaskRunner so the STT listen-loop
        returns immediately and is never blocked for the duration of a turn.
        Text/GUI commands run synchronously as before.
        """
        # Intercept file paths (dropped, typed, or pasted) before routing to LLM.
        file_path = self._resolve_rag_file_path(text)
        if file_path:
            import threading
            name = os.path.basename(file_path)
            self.emit_message("user", f"[Load file: {name}]", source=source)

            def _load():
                msg = self.load_session_rag_file(file_path)
                self.emit_assistant_message(msg, speak=True)

            threading.Thread(target=_load, daemon=True).start()
            return ""

        if source != "voice" and self.is_speaking:
            tts = getattr(self, "tts", None)
            if tts:
                tts.stop()

        self.routing_state.clear_voice_spoken()
        self.emit_message("user", text, source=source)

        if source in ("voice", "gui"):
            if source == "voice":
                # Pause mic right away; TaskRunner thread resumes it when done.
                self.event_bus.publish("gui_toggle_mic", False)
                if self.stt and hasattr(self.stt, "set_processing_state"):
                    self.stt.set_processing_state(True)
            self.task_runner.submit(text, source)
            return ""

        return self._execute_turn(text, source)

    def load_session_rag_file(self, path: str) -> str:
        """Load a file into the session RAG context. Returns a status message."""
        from core.logger import logger as _log
        try:
            msg = self.session_rag.load_file(path)
            _log.info("[session_rag] %s", msg)
            return msg
        except Exception as exc:
            _log.warning("[session_rag] Failed to load %s: %s", path, exc)
            return f"Could not load file: {exc}"

    def _execute_turn(self, text, source="user", cancel_event=None):
        """Synchronous turn processing — called directly (text/GUI) or via TaskRunner (voice)."""
        route_text = text
        if self.assistant_context and hasattr(self.assistant_context, "clean_user_text"):
            cleaned = self.assistant_context.clean_user_text(text, source=source)
            if cleaned:
                route_text = cleaned

        try:
            self._last_turn_speech_managed = False
            response = self.turn_manager.handle_turn(route_text, source=source)

            decision = self.routing_state.last_decision
            if decision:
                if decision.tool_name in ("play_youtube", "play_youtube_music", "browser_media_control"):
                    if not self.media_control_mode:
                        logger.info("[app] Entering Restricted Media Control Mode.")
                        self.media_control_mode = True
                        self.event_bus.publish("media_control_mode_changed", {"active": True})

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
                # Phase 8: queue Mem0 extraction for this completed turn.
                # Fires for all turn types (VLM, document, chat) — the extractor
                # waits for active_turns == 0 before calling mem0.add().
                _extractor = getattr(self, "_mem0_extractor", None)
                if _extractor:
                    try:
                        _extractor.queue_turn(route_text, response)
                    except Exception as e:
                        logger.warning("Mem0 extraction queue failed: %s", e)
            return response
        finally:
            if source == "voice":
                if self.stt and hasattr(self.stt, "set_processing_state"):
                    self.stt.set_processing_state(False)
                self.event_bus.publish("gui_toggle_mic", self.should_resume_voice_after_turn())

    def cancel_current_task(self, announce: bool = True) -> bool:
        """Cancel any running voice task. Returns True if something was running."""
        return self.task_runner.cancel_current(announce=announce)

    def _registry_routes(self) -> list:
        """Expose capability_registry entries as route dicts for RouteScorer."""
        from core.reasoning.route_scorer import RouteScorer  # noqa: PLC0415
        routes = []
        try:
            caps = self.capability_registry.list_capabilities()
        except Exception:
            return routes
        for cap in caps:
            spec = {
                "name": cap.name,
                "description": getattr(cap, "description", "") or "",
                "parameters": {},
            }
            routes.append(RouteScorer.build_route_entry(spec, None))
        return routes

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
        if role == "assistant":
            text = strip_model_artifacts(text)
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
        if speak and not self.routing_state.voice_already_spoken:
            self.event_bus.publish("voice_response", spoken_text if spoken_text is not None else text)
        self.routing_state.clear_voice_spoken()
