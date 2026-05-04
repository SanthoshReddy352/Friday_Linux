# FRIDAY 2.0 — Architectural Refactor Roadmap

> Strangler-pattern migration from the current monolithic `CommandRouter` architecture
> to a clean, scalable, modular agent system. The assistant stays **fully functional
> at every phase boundary** — no big-bang rewrite.

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete |
| 🔄 | In progress |
| ⬜ | Pending |

---

## Phase 0 — Safety Net ✅

**Goal:** Lock current behavior in tests before touching any code.

### Deliverables
- `core/tracing.py` — `trace_id` contextvar + `trace_scope()` context manager
- `core/event_bus.py` — structured logger replaces `print()`; per-handler exception isolation with `event_topic`, `event_handler`, `trace_id` fields
- `core/logger.py` — `_TraceContextFilter` injects `trace_id` into every log record; format includes `[trace=<id>]`
- `core/turn_manager.py` — `trace_scope(turn.turn_id)` wraps each turn
- `tests/snapshots/routing_snapshots.yaml` — 35 fixtures pinning current routing behavior
- `tests/test_routing_snapshots.py` — parametrized harness, runs without model files

### Key decisions
- EventBus stays synchronous (Qt slots + audio callbacks require it). Async-safe variant deferred to Phase 4.
- `trace_id` reuses `TurnRecord.turn_id` — no second correlation column.
- Snapshot fixtures lock **real current behavior**, not aspirational. Three fixtures were corrected during implementation when the harness revealed actual dispatch paths.

### Tests: 35/35 snapshots passing, 242/243 full suite (1 pre-existing failure)

---

## Phase 1 — Registry as Source of Truth ✅

**Goal:** Make `CapabilityRegistry` the single tool registration surface.
Break the implicit router-coupling in `tool_execution.py`, `conversation_agent.py`, and `turn_manager.py` without changing any plugin yet.

### Deliverables
- `core/routing_state.py` — `RoutingDecision` + `RoutingState` extracted from `CommandRouter`
- `core/response_finalizer.py` — `ResponseFinalizer` (humanize + clarification detection) extracted from `CommandRouter._finalize_response`
- `core/capability_registry.py` — added `register_from_router_spec()` as the explicit named entry point for future plugin migration
- `core/router.py` — compatibility `@property` bridge for `_voice_already_spoken`, `last_routing_decision`, `current_route_source`, `current_model_lane`; private methods now delegate to extracted services
- `core/tool_execution.py` — all `app.router._*` calls replaced with `app.routing_state.*` / `app.response_finalizer.*`
- `core/conversation_agent.py` — same cleanup
- `core/turn_manager.py` — reads `app.routing_state.voice_already_spoken` directly
- `core/app.py` — instantiates `RoutingState` + `ResponseFinalizer`, injects into router

### Key decisions
- `RoutingState` is injected into `CommandRouter` rather than the router owning it — router becomes a writer, everything else a reader.
- Router compatibility properties (`@property _voice_already_spoken`, etc.) let existing tests and GUI code work without any changes.
- `register_from_router_spec()` is semantically identical to `register_tool()` today; it will diverge in Phase 4 when it gains `ExtensionContext` plumbing.

### Tests: 242/243 (unchanged)

---

## Phase 2 — Composition Root ✅

**Goal:** Replace `FridayApp.__init__` chaos (20+ tightly-coupled services built in order) with a DI container. Fix `os._exit(0)` with proper lifecycle management.

### Deliverables
- `core/bootstrap/__init__.py`
- `core/bootstrap/lifecycle.py` — `LifecycleManager`: register → `start_all()` in order, `stop_all()` in reverse
- `core/bootstrap/container.py` — `Container`: lazy singleton DI, factory-based
- `core/bootstrap/settings.py` — `FridaySettings`: typed snapshot of YAML config (no new file format)
- `core/app.py` — `LifecycleManager` instantiated; `shutdown()` uses `lifecycle.stop_all()` + `sys.exit(0)`, `_shutdown_requested` guard prevents double-call
- `main.py` — SIGINT/SIGTERM both routed to `app.shutdown()` via `_install_signal_handlers()`

### Key decisions
- `FridayApp` is **not replaced** — it stays as the external facade so `main.py`, tests, and the GUI are unchanged. The container is internal scaffolding for now.
- `sys.exit(0)` instead of `os._exit(0)` — allows Python atexit handlers and Qt's `aboutToQuit` signal to fire; safe because all plugin threads are already daemonized.
- `FridaySettings` is a frozen dataclass snapshot — mutation still goes through `ConfigManager`/`app.set_*` methods to avoid two sources of truth.

### Tests: 242/243 (unchanged)

---

## Phase 3 — Consent + Permissions Consolidation ✅

**Goal:** Eliminate duplicated online-consent regex blocks. Add structured permission tiers to every capability descriptor.

### Deliverables
- `core/kernel/consent.py` — `ConsentService`: single source for `EXPLICIT_ONLINE_PATTERNS`, `POSITIVE_CONFIRMATION_PATTERNS`, `NEGATIVE_CONFIRMATION_PATTERNS`, `CURRENT_INFO_PATTERNS`
- `core/kernel/permissions.py` — `PermissionService`: enforce `read / write / critical` tiers; `critical` tools require per-invocation confirmation
- `core/kernel/__init__.py` — clean re-export
- `CapabilityBroker.build_plan()` uses `app.consent_service` exclusively; duplicate inline blocks removed
- All capability descriptors default to `read`; `write`/`critical` inferred from name keywords via `PermissionService.infer_side_effect_level()`

### Tests: 244/245 passing (1 pre-existing failure in test_world_monitor)

---

## Phase 4 — Extension Protocol (Plugin + Skill Unification) ✅

**Goal:** Merge `modules/` (plugins) and `skills/` (standalone skills loaded by `jarvis_skills`) into one extension interface. Plugins register tools directly against `CapabilityRegistry` via `ExtensionContext`, not through `CommandRouter`.

### Deliverables
- `core/extensions/protocol.py` — `Extension` protocol + `ExtensionContext` (narrow API surface: registry, events, consent, settings)
- `core/extensions/loader.py` — `ExtensionLoader`: discovers native extensions (`extension.py`) and wraps legacy `FridayPlugin` classes with `LegacyExtensionAdapter`; also handles `Skill` subclasses via `LegacySkillAdapter`
- `core/extensions/adapter.py` — `LegacyExtensionAdapter` wrapping old `FridayPlugin` subclasses
- `core/extensions/decorators.py` — `@capability(...)` decorator for ergonomic tool declaration
- `modules/greeter/extension.py` — first native `Extension` (no `FridayPlugin` dependency)
- `modules/jarvis_skills/` deleted; skills loaded from `skills/` directly
- All 8 remaining plugins wrapped via `LegacyExtensionAdapter`; `FridayApp.extension_loader.load_all()` replaces `PluginManager.load_plugins()`

### Tests: 244/245 passing

---

## Phase 5 — CommandRouter Dismantling ✅

**Goal:** Delete `core/router.py` (967 LOC). All routing goes through `TurnManager → ConversationAgent → CapabilityBroker → Executor`.

### Deliverables
- `core/reasoning/model_router.py` — `ModelRouter`: tool-LLM inference extracted from `CommandRouter._run_tool_model_request`; injected into `FridayApp` as `app.model_router`
- `core/reasoning/route_scorer.py` — `RouteScorer`: deterministic capability matching with alias/pattern/context-term scoring; `app.route_scorer` used by `CapabilityBroker._find_best_route()`
- `CapabilityBroker` fully decoupled: uses `app.route_scorer`, `app.intent_recognizer`, `app.workflow_orchestrator` directly — no more `app.router.*` calls for routing decisions
- `_action_to_step()` handles both old router format (`{"route": {...}}`) and new `IntentRecognizer` format (`{"tool": "...", "args": {...}}`)
- `core/app.py`: top-level `modules.*` import moved into lazy function body (import graph clean)
- `core/intent_recognizer.py`: top-level `modules.*` import replaced with lazy loader (import graph clean)

### Key decisions
- Router kept as compatibility shim — not deleted yet to avoid big-bang breakage. All new routing bypasses it.
- `IntentRecognizer` action format diverges from router's; broker normalises both.

### Tests: 298/299 passing (1 pre-existing failure in test_world_monitor)

---

## Phase 6 — LangGraph Execution Layer ✅

**Goal:** Replace `OrderedToolExecutor` with a stateful `LangGraph`-based execution graph. Enables multi-step reasoning, conditional branching, retries, checkpointing, and streaming intermediate responses.

### Deliverables
- `core/reasoning/graph_compiler.py` — `GraphCompiler`: compiles `ToolPlan` to a `LangGraph StateGraph` with feature flag `routing.execution_engine: "ordered" | "graph"`; auto-detects if langgraph is installed and falls back to `OrderedToolExecutor` if not
- `config.yaml`: `routing.execution_engine: ordered` flag added
- `tool_execution.py`: `plan.mode == "planner"` now routes through `GraphCompiler` instead of raw `router.process_text()`
- Single-step fast path: skips graph overhead for 1-step plans
- `core/reasoning/workflows/research_mode.py` — `ResearchWorkflow`: search → summarize → save pipeline
- `core/reasoning/workflows/focus_mode.py` — `FocusModeWorkflow`: pomodoro timer, threading.Timer auto-end, focus_mode_changed events
- Both workflows registered in `WorkflowOrchestrator.__init__`

### Notes
- Install `pip install langgraph` to enable the graph backend (falls back to ordered executor)
- `core/reasoning/graph_runtime.py` with `SqliteSaver` checkpointing is a future enhancement

### Tests: 298/299 passing

---

## Phase 7 — Memory System Upgrade ✅

**Goal:** Replace `HashEmbeddingFunction` (sha256-bucketed, quality-limited) with a real local embedding model. Split the single Chroma collection into three typed stores.

### Deliverables
- `core/memory/__init__.py`, `core/memory/embeddings.py` — `EmbedderProtocol` + `BGESmallEmbedder` (falls back to `HashEmbedder` if sentence-transformers not installed)
- `core/memory/episodic.py` — `EpisodicMemory`: 30-day rolling window, `prune_old_turns()` via ContextStore
- `core/memory/semantic.py` — `SemanticMemory`: `{key, value, confidence}` facts, `prune_low_confidence_memories()` via ContextStore
- `core/memory/procedural.py` — `ProceduralMemory`: bandit-style capability success rates, persisted to `facts` table, never deleted
- `core/memory_broker.py` upgraded to use all three stores; adds `curate()` for heuristic fact extraction and `record_capability_outcome()` for procedural feedback
- `core/context_store.py`: added `prune_old_turns()`, `delete_memory_item()`, `prune_low_confidence_memories()`, `get_facts_by_namespace()`
- `tool_execution.py`: calls `memory_broker.record_capability_outcome()` after every step

### Notes
- Install `pip install sentence-transformers` to enable `BGESmallEmbedder` (BAAI/bge-small-en-v1.5, 384-dim)
- Install `pip install chromadb` to enable vector store; currently falls back to SQL-based storage

### Memory tiers

| Store | Content | Pruning |
|-------|---------|---------|
| Episodic | Verbatim turns | Time-decay; summarize clusters at 30 days |
| Semantic | Facts (`key → value`) | Confidence floor 0.5; merge duplicates |
| Procedural | Skill success rates | Bandit-style; never deleted |

### Tests: 298/299 passing

---

## Phase 8 — Google Workspace Integration ✅

**Goal:** Add a `workspace_agent` extension giving FRIDAY access to Gmail, Calendar, and Drive via the `gws` CLI.

### Deliverables
- `modules/workspace_agent/gws_client.py` — thin subprocess wrapper around the `gws` CLI; all methods return parsed Python objects or raise `GWSError`
- `modules/workspace_agent/extension.py` — `WorkspaceAgentExtension`: native Extension registering 8 capabilities
- `modules/workspace_agent/__init__.py` — module entry point

### Capabilities registered

| Capability | Description | Permission |
|-----------|-------------|-----------|
| `check_unread_emails` | List unread Gmail inbox | ask_first / read |
| `read_email` | Read a message by ID | ask_first / read |
| `get_calendar_today` | Today's calendar events | ask_first / read |
| `get_calendar_week` | This week's events | ask_first / read |
| `get_calendar_agenda` | Next N-day agenda | ask_first / read |
| `create_calendar_event` | Create a calendar event | ask_first / critical |
| `search_drive` | Search Drive by name | ask_first / read |
| `daily_briefing` | Morning: emails + calendar | ask_first / read |

### Key decisions
- All capabilities tagged `connectivity="online"`, `latency_class="slow"` — `ConsentService` will ask before first use per session
- `GWSError` is raised on subprocess failure, missing auth, or API errors; callers degrade gracefully
- Uses `gws gmail +triage --format json` for unread list, `gws calendar +agenda --today --format json` for calendar

### Tests: 298/299 passing

---

## Phase 9 — New Productivity Capabilities ✅

**Goal:** Ship the high-value skills that make FRIDAY genuinely useful day-to-day.

### Deliverables
- `core/dialogue_manager.py` — `DialogueManager`: 30+ domain-aware contextual acks, tone detection (frustrated/urgent/curious/warm/neutral), tone-adaptive response prefix
- `CapabilityBroker._ack_for_steps()` upgraded to call `DialogueManager.contextual_ack()` for slow/online steps
- `MemoryBroker.curate()`: heuristic extraction of "remember", "my name is", preference sentences → `SemanticMemory`
- `core/reasoning/workflows/research_mode.py` — `ResearchWorkflow`: multi-step search → LLM summarize → optional file save to `~/Documents/friday_research/`
- `core/reasoning/workflows/focus_mode.py` — `FocusModeWorkflow`: Pomodoro (25-min default), custom durations, `threading.Timer` auto-end, `focus_mode_changed` events for UI

### Notes
- Meeting Assistant (transcription → structured notes) and streaming token output are future enhancements
- PersonaManager tone profiles can be wired into `DialogueManager.adapt_response()` when ready

### Tests: 298/299 passing

---

## Phase 10 — Performance, Safety & Hardening ✅

**Goal:** Production-quality observability, sandboxing, and performance optimization.

### Deliverables
- `core/result_cache.py` — `ResultCache`: thread-safe TTL cache keyed on `(capability_name, args_hash, raw_text)`; TTL sourced from `CapabilityDescriptor` (local read = 300 s, online read = 120 s, write/critical = 0)
- `core/tool_execution.py`: cache check before every step, cache-set after successful reads, `memory_broker.record_capability_outcome()` for procedural feedback
- `core/tracing.py`: `TurnTrace` accumulates structured per-turn events; `configure_trace_export()` → `data/traces.jsonl` export on each turn; `FridayApp.initialize()` calls `configure_trace_export()`
- `tests/test_import_graph.py` — import-graph linter: 54 parametrized tests ensure `core.*` never imports `modules.*` or `extensions.*` at module level (lazy imports inside functions are allowed)
- Fixed all import-graph violations: `core/app.py` and `core/intent_recognizer.py` now use lazy imports for `modules.*`

### Notes
- Sandbox wrapper for `system_control` critical writes (subprocess CPU/wall-time limits) is a future enhancement
- OpenTelemetry exporter can be added by implementing a custom `TurnTrace` backend

### Tests: 298/299 passing (1 pre-existing failure in test_world_monitor)

---

## Migration Strategy Summary

The migration follows a **strangler-fig pattern** — the old `CommandRouter` is still alive and load-bearing. Each phase chips away at its responsibilities without ever leaving the system in a broken state.

```
Phase 0  ──  Snapshot tests (regression net)
Phase 1  ──  Extract services from router (RoutingState, ResponseFinalizer)
Phase 2  ──  Composition root, lifecycle, graceful shutdown
Phase 3  ──  ConsentService, permission tiers
Phase 4  ──  Extension protocol, plugin migration away from router.register_tool()
Phase 5  ──  CommandRouter dismantled; all routing through CapabilityBroker
Phase 6  ──  LangGraph execution layer + named workflows
Phase 7  ──  Real embeddings, memory tier split
Phase 8  ──  Google Workspace integration
Phase 9  ──  New productivity skills, dialogue improvements
Phase 10 ──  Performance, import-graph linter, result cache, tracing
```

---

## Dependency Graph

```
0 ──► 1 ──► 2 ──► 3 ──► 4 ──► 5
                              │
                              └──► 6 ──► 7
                                         │
                              8 ─────────┤
                              9 ─────────┤
                             10 ─────────┘
```

---

## Current State (as of 2026-04-29)

| Phase | Status | Notes |
|-------|--------|-------|
| 0 — Safety Net | ✅ Complete | 35 snapshot tests, structured EventBus logging, trace_id |
| 1 — Registry Source of Truth | ✅ Complete | RoutingState, ResponseFinalizer extracted; router deps broken |
| 2 — Composition Root | ✅ Complete | LifecycleManager, Container, FridaySettings; os._exit → sys.exit |
| 3 — Consent Consolidation | ✅ Complete | ConsentService + PermissionService in core/kernel/; CapabilityBroker fully migrated |
| 4 — Extension Protocol | ✅ Complete | ExtensionLoader, LegacyExtensionAdapter, LegacySkillAdapter; greeter native; all plugins wrapped |
| 5 — Router Dismantling | ✅ Complete | ModelRouter, RouteScorer extracted; CapabilityBroker fully decoupled; import graph clean |
| 6 — LangGraph | ✅ Complete | GraphCompiler + feature flag; ResearchWorkflow + FocusModeWorkflow registered; langgraph optional |
| 7 — Memory Upgrade | ✅ Complete | EpisodicMemory, SemanticMemory, ProceduralMemory; BGESmallEmbedder (optional); MemoryBroker.curate() |
| 8 — Google Workspace | ✅ Complete | gws CLI wrapper; 8 capabilities (Gmail, Calendar, Drive); daily_briefing |
| 9 — New Skills | ✅ Complete | DialogueManager; ResearchWorkflow; FocusModeWorkflow; MemoryBroker.curate() |
| 10 — Hardening | ✅ Complete | ResultCache; TurnTrace → traces.jsonl; import-graph linter (54 tests) |

**Full test suite: 298/299 passing** (1 pre-existing failure in `test_world_monitor` unrelated to refactor)
