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
        # Batch 3 / Issue 3: any user-initiated cancel ("stop", "enough",
        # "Friday cancel", wake-word barge-in) fires through the global
        # InterruptBus. DialogState clears every pending-* field on signal
        # so the next turn starts clean.
        from core.interrupt_bus import get_interrupt_bus  # noqa: PLC0415
        self._interrupt_bus = get_interrupt_bus()
        self._interrupt_bus.subscribe(
            "all",
            lambda sig: self.dialog_state.reset_pending(sig.reason),
        )
        self.assistant_context = AssistantContext()
        self.context_store = ContextStore()
        self.session_id = self.context_store.start_session({"entrypoint": "FridayApp"})
        # memory_service is created further below; bind now without it and
        # rebind once it exists so assistant_context can surface Mem0 facts
        # in chat prompts.
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
        # Port #3: audit trail — every capability execution is logged here.
        from core.audit_trail import AuditTrail  # noqa: PLC0415
        self.audit_trail = AuditTrail(self.memory_service, session_id=self.session_id)
        self.capability_executor.audit_trail = self.audit_trail
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
        # Optional LoRA-tuned intent router (Gemma 3 270M). Opt-in via
        # ``FRIDAY_USE_GEMMA_ROUTER=1`` — defaults off so existing flows
        # keep using the deterministic + embedding router. When enabled,
        # ``self.gemma_router`` is preloaded so the first turn doesn't
        # pay cold-load latency. Use ``self.gemma_predict(text)`` to
        # query it; integration into the live turn loop is intentionally
        # left to the caller so behavior changes are explicit.
        # Bench: docs/bench_results_2026_05_16.md (macro F1 0.762, p95 163 ms).
        self.gemma_router = None
        # Tools Gemma was actually trained on. The live runtime has
        # MORE tools than this (vision Tier 2 etc. were added after the
        # LoRA training set was synthesized), so predictions for any
        # name outside this set are out-of-distribution noise. Loaded
        # below alongside the router so gemma_predict() can filter them.
        self._gemma_trained_tools: set[str] = set()
        if os.environ.get("FRIDAY_USE_GEMMA_ROUTER") == "1":
            try:
                from core.gemma_router import GemmaIntentRouter  # noqa: PLC0415
                self.gemma_router = GemmaIntentRouter(mode="chat")
                if not self.gemma_router.load():
                    logger.warning(
                        "[app] FRIDAY_USE_GEMMA_ROUTER=1 but Gemma 270M "
                        "model failed to load — falling back to deterministic router."
                    )
                    self.gemma_router = None
                else:
                    # Load the trained-on tool set so gemma_predict()
                    # can suppress hallucinated predictions for tools
                    # Gemma never saw during fine-tuning.
                    try:
                        import yaml  # noqa: PLC0415
                        reg_path = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "tests", "datasets", "tool_registry.yaml",
                        )
                        with open(reg_path, encoding="utf-8") as fh:
                            self._gemma_trained_tools = {
                                t["name"] for t in (yaml.safe_load(fh) or {}).get("tools", [])
                            }
                    except Exception as exc:
                        logger.warning(
                            "[app] Could not load tool_registry.yaml for Gemma "
                            "OOD filter (%s) — all predictions will pass through.", exc,
                        )
                    logger.info(
                        "[app] Gemma 270M intent router enabled "
                        "(loaded in %.0f ms, trained on %d tools).",
                        self.gemma_router.last_load_ms, len(self._gemma_trained_tools),
                    )
            except Exception as exc:
                logger.warning("[app] Gemma router init failed: %s", exc)
                self.gemma_router = None
        # Port #6: multi-agent hierarchy
        from core.agent_hierarchy import AgentHierarchy, AgentTaskManager, AgentNode  # noqa: PLC0415
        self.agent_hierarchy = AgentHierarchy()
        self.agent_task_manager = AgentTaskManager(self.agent_hierarchy, self.memory_service)
        # Register primary FRIDAY node
        self.agent_hierarchy.add_agent(AgentNode(
            agent_id="friday",
            name="FRIDAY",
            role="primary",
            authority_level=10,
        ))
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
        # Port #8: cloud LLM fallback chain (opt-in, respects local-first stance).
        from core.llm_providers.fallback_chain import FallbackChain  # noqa: PLC0415
        self.llm_fallback_chain = FallbackChain.from_config(self.config)
        if self.llm_fallback_chain.enabled:
            logger.info("[app] Cloud LLM fallback chain enabled.")
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
        # Now that memory_service exists, give assistant_context a handle so
        # build_chat_messages can inject user_facts into the chat prompt.
        try:
            self.assistant_context.memory_service = self.memory_service
        except Exception:
            pass

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

    def gemma_predict(self, text: str) -> "tuple[str | None, float]":
        """Run the optional LoRA-tuned intent router on *text*.

        Returns ``(tool_name, latency_ms)``. ``tool_name`` is ``None``
        when Gemma isn't loaded (flag off / model missing / load failed)
        or when it declines to pick a tool. Latency is 0.0 in those
        no-op cases. Safe to call from any thread.

        Intentionally NOT wired into the live routing path — callers
        decide when and how to use this signal (shadow-route + log,
        replace deterministic, or A/B by feature flag) so behavior
        changes stay explicit and reviewable.
        """
        if self.gemma_router is None:
            return None, 0.0
        try:
            # Only show Gemma the tools it was trained on. Sending the
            # full live tool list lets Gemma "predict" tools it has zero
            # training signal for (e.g. explain_meme), which produces
            # confidently-wrong shadow predictions. Intersecting with
            # the trained set keeps Gemma in distribution.
            trained = self._gemma_trained_tools
            tools = [
                {"name": name, "description": (route.get("spec") or {}).get("description", "")[:120]}
                for name, route in self.router._tools_by_name.items()
                if not trained or name in trained
            ]
            decision = self.gemma_router.route(text, tools)
            allowed = [t["name"] for t in tools]
            tool = self.gemma_router.normalize_tool_name(decision.tool, allowed)
            # Belt-and-suspenders: drop any prediction that still leaks
            # an out-of-distribution name (defense against future code
            # paths that bypass the prompt filter above).
            if tool and trained and tool not in trained:
                logger.info(
                    "[gemma_predict] suppressing OOD prediction %r "
                    "(not in trained tool set)", tool,
                )
                tool = None
            return tool, decision.latency_ms
        except Exception as exc:
            logger.warning("[gemma_predict] failed: %s", exc)
            return None, 0.0

    def _shadow_route_with_gemma(self, text: str) -> None:
        """Run Gemma on *text* in a background thread and publish a
        ``gemma_prediction`` event for HUD / log visibility.

        Shadow only — does NOT affect the live routing decision. The
        deterministic router runs in parallel on the main turn thread;
        this just surfaces what Gemma WOULD have predicted so users can
        compare both paths in the event stream before flipping the live
        switch. Costs ~80–200 ms of background CPU on i5-12; the turn
        itself is unblocked.
        """
        if self.gemma_router is None:
            return
        import threading  # noqa: PLC0415 — keep startup imports lean

        def _run():
            tool, latency_ms = self.gemma_predict(text)
            logger.info(
                "[gemma_shadow] utterance=%r -> tool=%s (%.0f ms)",
                text[:80], tool or "—", latency_ms,
            )
            try:
                self.event_bus.publish("gemma_prediction", {
                    "utterance":  text,
                    "tool_name":  tool or "",
                    "latency_ms": latency_ms,
                })
            except Exception:
                pass

        try:
            threading.Thread(target=_run, daemon=True, name="gemma-shadow").start()
        except Exception as exc:
            logger.warning("[gemma_shadow] thread start failed: %s", exc)

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

        # Shadow-run the optional LoRA-tuned Gemma router for visibility.
        # No-op when FRIDAY_USE_GEMMA_ROUTER is unset (gemma_router is None).
        self._shadow_route_with_gemma(text)

        if source in ("voice", "gui"):
            if source == "voice":
                # Mute the mic button immediately so the GUI shows "idle/processing"
                # while the turn runs. The post-turn finally block will re-emit the
                # correct state (True for persistent/wake_word, False for on_demand).
                self.event_bus.publish("gui_toggle_mic", False)
                # Keep mic open so the user can barge in by saying "Friday [command]"
                # while the task is running. The reactor shows "processing" via
                # set_processing_state; stop_listening() is intentionally not called.
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
        self._current_cancel_event = cancel_event
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
