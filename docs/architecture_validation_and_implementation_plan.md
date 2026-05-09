# FRIDAY Architecture — Allegation Validation and Implementation Plan

## Methodology

Each allegation from the architecture problem documents was validated against the **current codebase** using the graphify knowledge graph (2,797 nodes, 4,915 edges) and direct source-file inspection.

Verdict codes:
- **CONFIRMED** — allegation is accurate; the gap is real
- **PARTIALLY CONFIRMED** — the gap exists but the docs overstate the severity
- **FALSE** — the feature is already implemented; allegation is outdated
- **SUPERSEDED** — addressed by a different mechanism than the docs assumed

---

## Allegation 1 — Missing Working Artifact Memory

**Verdict: CONFIRMED**

The docs allege that generated outputs are stored only as raw text turns and cannot be referenced in follow-up interactions.

**What the code shows:**

- `ContextStore.append_turn()` (`core/context_store.py:L109`) stores role + text only — no artifact object.
- `CapabilityExecutionResult` (`core/capability_registry.py:L39`) exists and captures `ok`, `name`, `output: Any`, `error`, `descriptor`. This is a step in the right direction but it is ephemeral — it lives only inside the executor call and is never attached to a session or turn.
- No `WorkingArtifact` dataclass, no `active_artifact` field, no session-level pronoun → artifact resolution exists anywhere in `core/` or `modules/`.

**Real-world impact confirmed:** "save that", "read it back", "export this" will fail or require the user to re-specify content.

**Implementation Plan:**

### Step 1 — Add `WorkingArtifact` dataclass to `core/capability_registry.py`

```python
@dataclass
class WorkingArtifact:
    artifact_id: str
    artifact_type: str          # "text" | "list" | "code" | "table" | "summary" | "search_results"
    content: Any
    display_text: str
    source_capability: str
    created_at: str
    turn_id: str
```

### Step 2 — Add `active_artifact` to `ContextStore` session state

Extend `ContextStore.save_session_state()` / `get_session_state()` (already at `core/context_store.py:L362`) to persist the artifact in the existing `session_state` JSON blob. No schema migration required — the blob is already schemaless.

### Step 3 — Populate artifact after every capability execution

In `TaskGraphExecutor._execute_node()` (`core/task_graph_executor.py`), after a successful tool result, construct a `WorkingArtifact` and call `memory_service.set_active_artifact(artifact)`.

### Step 4 — Resolve pronouns in `IntentRecognizer`

In `IntentRecognizer.plan()` (`core/intent_recognizer.py`), before clause parsing, check if the text is a pure pronoun reference ("save that", "read it", "export this"). If so, inject `active_artifact.content` as the resolved target.

**Latency impact: Zero** — O(1) in-memory lookup. No LLM call required for pronoun resolution.

---

## Allegation 2 — Missing Goal Continuity Layer

**Verdict: CONFIRMED**

The docs allege that the system processes turns individually with no persistent project-level goal awareness.

**What the code shows:**

- `WorkflowOrchestrator` handles discrete multi-step tasks (file workflows, browser workflows, calendar workflows) but these are short-lived operational states, not semantic project goals.
- `ContextStore.save_workflow_state()` (`core/context_store.py:L171`) persists workflow state with a 24-hour TTL, but this is for operational continuity, not goal tracking.
- No `ActiveGoal` dataclass exists anywhere.

**What the docs got wrong:** The severity is real but manageable. The `ContextStore` session state (already a JSON blob) can hold a goal without architectural surgery.

**Implementation Plan:**

### Step 1 — Add `ActiveGoal` to session state

```python
@dataclass
class ActiveGoal:
    goal_id: str
    title: str
    objective: str
    related_artifact_ids: list[str]
    turn_count: int          # incremented each turn; expire after N turns of silence
    updated_at: str
```

Store as part of `session_state` JSON blob — no new tables needed.

### Step 2 — Goal detection in `CapabilityBroker.build_plan()`

Add lightweight heuristic goal extraction for open-ended multi-sentence requests ("help me build...", "I want to create...", "let's work on..."). This runs purely on regex/keywords, no extra LLM call.

### Step 3 — Inject goal into `context_bundle`

`MemoryBroker.build_context_bundle()` (`core/memory_broker.py:L22`) already builds the per-turn context dict. Add `active_goal` to the bundle when it's set.

### Step 4 — Goal expiry

Expire goals after 10 turns of inactivity or on explicit cancellation. Check in `CapabilityBroker.build_plan()` before injecting.

**Latency impact: ~0 ms** — heuristic regex check, no inference.

---

## Allegation 3 — Missing Structured Output Typing

**Verdict: PARTIALLY CONFIRMED**

The docs allege outputs are all plain strings.

**What the code shows:**

- `CapabilityExecutionResult` (`core/capability_registry.py:L39`) already exists with typed fields: `ok: bool`, `name: str`, `output: Any`, `error: str`. This is NOT a plain string — the allegation is overstated.
- `ResultCache` (`core/result_cache.py`) caches these results by capability + args hash.
- However, `output: Any` is semantically untyped — there is no `output_type: str` field annotating whether it's a list, table, markdown, code etc. The LLM context injection in `CommandRouter._format_plan_responses()` stringifies everything before it reaches the model.

**Implementation Plan:**

### Extend `CapabilityExecutionResult` with semantic type

```python
@dataclass
class CapabilityExecutionResult:
    ok: bool
    name: str
    output: Any = ""
    error: str = ""
    descriptor: CapabilityDescriptor | None = None
    output_type: str = "text"   # ADD: "text"|"list"|"table"|"code"|"search_results"|"summary"
    metadata: dict = field(default_factory=dict)
```

Each capability handler sets `output_type` at return time. The `WorkingArtifact` stores this type. The `TaskGraphExecutor` can then pass typed results between steps.

**Latency impact: Zero.**

---

## Allegation 4 — Missing Cross-Turn Reference Resolution

**Verdict: PARTIALLY CONFIRMED**

The docs allege that pronoun references are not globally modeled.

**What the code shows:**

- `IntentRecognizer._split_into_clauses()` (`core/intent_recognizer.py:L70`) already prevents splitting when a pronoun references the prior clause ("take a screenshot and save it"). This is a correct observation.
- File disambiguation ("that one", "this one") exists for file context specifically.
- No session-level `reference_registry` tracking indexed items, last list, or selected entity exists.

**What the docs got right:** "Compare the second one with Gemma" would fail because "the second one" from a prior list has no binding.

**Implementation Plan:**

Extend the `WorkingArtifact` approach (Allegation 1 fix) to also track:

```python
reference_registry = {
    "last_list": [...],          # last enumerated list from assistant
    "selected_entity": ...,      # last entity the user referred to
    "active_document": ...,      # last file/document discussed
}
```

Store in session state alongside `active_artifact`. Resolve in `IntentRecognizer.plan()`. The reference registry is populated by the `ResponseFinalizer` (`core/response_finalizer.py`) which already post-processes outputs.

**Latency impact: Zero.**

---

## Allegation 5 — Missing Incremental Planning

**Verdict: FALSE — Already Implemented**

The docs allege there is no adaptive execution planning with dependency graphs.

**What the code shows:**

This is already implemented:

- `ToolStep` (`core/capability_broker.py:L16`) has `node_id: str`, `depends_on: list[str]`, and `retries: int`.
- `TaskGraphExecutor` (`core/task_graph_executor.py`) does full DAG-based parallel execution with wave scheduling. Step 1 completes, its output flows into Step 2 that depends on it.
- `CapabilityBroker._should_use_planner()` (`core/capability_broker.py:L398`) decides when to activate deeper planning vs. deterministic routing.
- `ResearchPlannerWorkflow` (`core/reasoning/workflows/research_planner.py`) is a concrete multi-step planning workflow with a state machine.
- `ConversationAgent` (`core/conversation_agent.py:L62`) selects `TaskGraphExecutor` when `routing.execution_engine == "parallel"`.

**No implementation needed.** The docs were written based on an earlier codebase state before the v2 refactor (Phases 4–6) was completed.

---

## Allegation 6 — Missing Unified Runtime State Layer

**Verdict: PARTIALLY CONFIRMED**

The docs allege state is scattered across isolated systems with no unified view.

**What the code shows:**

Significant unification has already happened:
- `MemoryService` (`core/memory_service.py`) is a unified facade over `ContextStore` + `MemoryBroker`.
- `Kernel` (`core/kernel/runtime.py`) is a DI container that exposes all major services under typed keys.
- EventBus coordinates cross-component communication.

However, there is still no single queryable dict that shows `{active_goal, active_artifact, active_workflow, selected_entities}` at a glance.

**Implementation Plan:**

Rather than a heavyweight "blackboard", add a lightweight `TurnContext` snapshot that aggregates the current runtime state for per-turn use:

```python
@dataclass
class TurnContext:
    session_id: str
    active_workflow: dict | None
    active_goal: ActiveGoal | None
    active_artifact: WorkingArtifact | None
    reference_registry: dict
    context_bundle: dict
```

Build it at the start of `FridayApp._execute_turn()` from `MemoryService` and pass it through the pipeline. This is a composition pattern, not a replacement for existing systems.

**Latency impact: ~1 ms** — all data already in memory, just assembled into one object.

---

## Allegation 7 — Missing Streaming Cognitive Feedback

**Verdict: FALSE — Already Implemented**

The docs allege the system returns only finalized outputs with no intermediate reasoning exposure.

**What the code shows:**

This is fully implemented:
- `TurnFeedbackRuntime` (`core/turn_feedback.py`) publishes `assistant_ack`, `assistant_progress`, `tool_started`, `tool_finished`, `llm_started`, `llm_first_token` events.
- `SpeechCoordinator` (`core/speech_coordinator.py:L31`) subscribes to `assistant_progress` and voices intermediate states.
- `TurnFeedbackRuntime.start_progress_timers()` schedules "I'm working on it" / "Still checking" messages after configurable delays.
- `EventBus` (`core/event_bus.py`) distributes these synchronously to all subscribers.
- `DialogueManager` (`core/dialogue_manager.py`) provides domain-specific acks for each capability type.

**No implementation needed.** This allegation is factually incorrect for the current codebase.

---

## Allegation 8 — Missing Long-Horizon Task Persistence

**Verdict: CONFIRMED**

The docs allege there is no persistent scheduler for recurring autonomous tasks.

**What the code shows:**

- `ResearchAgentService` uses threading for background research but this is per-session, not persistent across restarts.
- `ContextStore` stores workflows with a 24-hour TTL but has no scheduling/trigger mechanism.
- No `TaskScheduler`, no `PersistentTask` dataclass, no cron-like system exists.

**Implementation Plan:**

Keep this minimal and local-first:

### Step 1 — `PersistentTask` dataclass + SQLite table

```python
@dataclass
class PersistentTask:
    task_id: str
    trigger_type: str      # "on_start" | "hourly" | "daily" | "on_network"
    objective: str
    capability_name: str
    args: dict
    last_run_at: str | None
    created_at: str
    enabled: bool = True
```

Add a `persistent_tasks` table to the existing `data/friday.db` SQLite database. No new dependency needed.

### Step 2 — `TaskScheduler` background thread in `FridayApp`

A simple daemon thread that wakes up every 60 seconds, queries due tasks, and executes them via the existing capability pipeline. Uses `ContextStore` for persistence.

### Step 3 — Register capabilities to manage tasks

Add `schedule_task` and `list_scheduled_tasks` capabilities to the `CapabilityRegistry`.

**Latency impact: Zero on voice interactions** — runs in a background daemon thread.

---

## Allegation 9 — Missing Multi-Modal Working Context

**Verdict: CONFIRMED (scope adjusted)**

The docs allege no unified multimodal reasoning layer exists.

**What the code shows:**

- Files are handled as paths through `system_control/file_workspace.py` — no typed `ContextObject` system.
- No VLM module exists in `modules/`.
- Images, PDFs, and audio inputs cannot be semantically associated with each other in a context graph.

**Implementation Plan:**

The full `ContextObject` graph system described in the docs is over-engineered for the current hardware. The pragmatic fix is:

### Step 1 — Add a VLM plugin (see VLM document)

### Step 2 — Extend `WorkingArtifact` to cover multimodal inputs

```python
artifact_type: str  # extend to include "image" | "pdf" | "audio_transcript"
```

The same `active_artifact` mechanism from Allegation 1 handles multimodal references. "Use this with the previous notes" resolves the image artifact via the reference registry.

**Full context-graph linking is deferred** — the hardware constraints make a graph traversal at every turn too expensive. Lightweight linear artifact tracking covers 95% of the use cases.

---

## Allegation 10 — Missing Failure Recovery Intelligence

**Verdict: PARTIALLY CONFIRMED**

The docs allege failures return plain text errors with no recovery behavior.

**What the code shows:**

- `ToolStep.retries: int = 0` already exists in the dataclass but is **never set** by any code path — the field is wired but unused.
- `TaskGraphExecutor` catches exceptions and logs them but does not retry or fall back.
- `CapabilityDescriptor` has no `fallback_tools` field.

**Implementation Plan:**

### Step 1 — Wire up `ToolStep.retries`

In `TaskGraphExecutor._execute_node()`, add a retry loop that respects `step.retries`. Max retries: 2. Exponential backoff: 100 ms, 300 ms. This is a 10-line change.

### Step 2 — Add `fallback_capability` to `CapabilityDescriptor`

```python
@dataclass
class CapabilityDescriptor:
    ...
    fallback_capability: str = ""   # name of capability to try if this one fails
```

Tool handlers that have natural fallbacks (e.g., Chrome → Firefox) set this field at registration.

### Step 3 — Fallback routing in `TaskGraphExecutor`

After all retries exhausted, check `descriptor.fallback_capability` and attempt it before returning an error.

**Latency impact: Negligible** — retry delays only trigger on failure.

---

## Allegation 11 — Missing Resource-Aware Intelligence

**Verdict: CONFIRMED**

The docs allege the system has no runtime resource awareness and cannot adapt to RAM/CPU pressure.

**What the code shows:**

- `RuntimeMetrics` tracks only turn timing (duration_ms, route_duration_ms, first_ack_ms). No CPU, RAM, or thermal data.
- No adaptive scheduling based on hardware state exists.
- `LocalModelManager` has per-domain inference locks but does not unload models under RAM pressure.

**Implementation Plan:**

Keep it simple and latency-safe:

### Step 1 — `ResourceMonitor` singleton using `psutil`

```python
class ResourceMonitor:
    def snapshot(self) -> ResourceSnapshot:
        return ResourceSnapshot(
            cpu_percent=psutil.cpu_percent(interval=None),
            ram_percent=psutil.virtual_memory().percent,
            ram_available_mb=psutil.virtual_memory().available // (1024*1024),
        )
```

`psutil` is CPU-cheap (non-blocking, uses kernel counters). Already available in most Python environments.

### Step 2 — Adaptive policies in `CapabilityBroker.build_plan()`

```python
snapshot = self.app.resource_monitor.snapshot()
if snapshot.ram_percent > 85:
    # Force lightweight model for this turn
    style_hint = "concise"
if snapshot.cpu_percent > 90:
    # Skip background indexing, reduce tool timeout
    ...
```

### Step 3 — Surface metrics in existing `RuntimeMetrics.summary_lines()`

Add CPU/RAM to the existing summary so the GUI and logs can display them.

**Latency impact: ~1 ms per turn** — psutil snapshot is a non-blocking kernel call.

---

## Allegation 12 — Missing Self-Optimization Feedback Loop

**Verdict: PARTIALLY CONFIRMED**

The docs allege the system does not adapt based on long-term behavior.

**What the code shows:**

- `MemoryBroker.record_capability_outcome()` (`core/memory_broker.py:L72`) already records capability outcomes — the data collection exists.
- `RuntimeMetrics` tracks per-turn latency.
- However, no code reads these accumulated outcomes to actually adjust routing weights or verbosity.

**Implementation Plan:**

Keep it asynchronous and non-intrusive:

### Step 1 — `OptimizationSignal` recorder in `TaskGraphExecutor`

After each successful or failed execution, push an `OptimizationSignal` to a lightweight in-memory queue (not blocking the turn pipeline).

### Step 2 — Background `RouteOptimizer` thread

Runs during idle periods. Reads accumulated capability outcome data from `MemoryBroker` (already stored). Adjusts `RouteScorer` weights for capabilities that consistently fail or have high latency. No LLM required — pure statistical aggregation.

### Step 3 — Verbosity adaptation

Track response length vs. user follow-up behavior in `MemoryBroker`. If the user frequently asks for shorter answers, inject `style_hint = "concise"` into `CapabilityBroker.build_plan()`.

**Latency impact: Zero on active turns** — background-only operation.

---

## Summary Table

| # | Allegation | Verdict | Implementation Effort |
|---|---|---|---|
| 1 | Working Artifact Memory | CONFIRMED | Low — extend ContextStore session state |
| 2 | Goal Continuity Layer | CONFIRMED | Low — session state + heuristic detection |
| 3 | Structured Output Typing | PARTIALLY CONFIRMED | Very Low — one field on existing dataclass |
| 4 | Cross-Turn Reference Resolution | PARTIALLY CONFIRMED | Low — reuses artifact mechanism |
| 5 | Incremental Planning | FALSE — Already Implemented | None |
| 6 | Unified Runtime State | PARTIALLY CONFIRMED | Low — TurnContext composition object |
| 7 | Streaming Cognitive Feedback | FALSE — Already Implemented | None |
| 8 | Long-Horizon Task Persistence | CONFIRMED | Medium — SQLite table + daemon thread |
| 9 | Multi-Modal Working Context | CONFIRMED (reduced scope) | Covered by VLM document |
| 10 | Failure Recovery Intelligence | PARTIALLY CONFIRMED | Low — wire up existing `retries` field |
| 11 | Resource-Aware Intelligence | CONFIRMED | Low — psutil + adaptive policies |
| 12 | Self-Optimization Feedback Loop | PARTIALLY CONFIRMED | Medium — background optimizer thread |

---

## Recommended Implementation Order

### Phase A — Immediate (high value, low latency risk)

1. Working Artifact Memory (Allegation 1)
2. Extend `CapabilityExecutionResult` with `output_type` (Allegation 3)
3. Reference Registry (Allegation 4, reuses Allegation 1 infrastructure)
4. Wire `ToolStep.retries` + `fallback_capability` (Allegation 10)

### Phase B — Short-term (meaningful continuity gains)

5. Goal Continuity Layer (Allegation 2)
6. `TurnContext` snapshot (Allegation 6)
7. `ResourceMonitor` with adaptive policies (Allegation 11)

### Phase C — Medium-term (autonomy and optimization)

8. Persistent Task Scheduler (Allegation 8)
9. Background Route Optimizer (Allegation 12)
10. Multi-modal context (Allegation 9, covered by VLM implementation)

---

## Architectural Constraints Preserved

All implementation items above adhere to the constraints in `friday_constraints_and_latency_aware_architecture.md`:

- No always-on LLM reasoning added
- No reflection loops introduced
- No cloud dependency
- All features are deterministic or heuristic (no LLM required for artifact resolution, goal detection, reference resolution, retry logic, or resource monitoring)
- All background operations use daemon threads that cannot block voice interactions
- Estimated per-turn latency overhead from ALL Phase A + B items combined: **< 5 ms**
