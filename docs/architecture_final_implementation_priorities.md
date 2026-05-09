# FRIDAY Architecture — Final Implementation Priorities

## Filtering Methodology

The 12 allegations from the validation document are re-evaluated here against two additional constraints that the original analysis did not weight heavily enough:

1. **Token overhead per turn** — any data injected into the LLM context bundle costs inference time on every turn, not just when the feature is active. On a 4B model running at ~5–12 tok/sec on a CPU, every extra 20 tokens is a real latency cost.

2. **Background thread contention** — the i5-12th Gen runs both inference and background work on shared CPU cores. Poorly designed background threads compete directly with llama.cpp's inference thread pool.

Each allegation is given a final verdict: **IMPLEMENT**, **DEFER**, or **ALREADY DONE**.

---

## Final Verdict by Allegation

---

### Allegation 1 — Working Artifact Memory
**Final Verdict: IMPLEMENT**

**Why it passes:**
- Artifact is stored in the existing session-state JSON blob (`ContextStore.save_session_state()`). No new tables, no new DB queries per turn.
- Pronoun resolution is a pure string match before clause parsing — no LLM call, no embedding lookup.
- The artifact itself is never injected into the LLM prompt. Only the resolved content (when explicitly referenced) replaces a pronoun — which would have been sent to the LLM anyway.
- **Net token overhead: zero.** Net latency overhead: < 0.5 ms.

**Why it is necessary:**
Voice interactions heavily depend on "save that", "read it back", "export this", "use this". Without artifact tracking, these fail silently or require the user to repeat themselves. This is the highest-impact UX fix for the least implementation cost.

---

### Allegation 2 — Goal Continuity Layer
**Final Verdict: DEFER**

**Why it is deferred:**
Goal injection into `MemoryBroker.build_context_bundle()` means the active goal text appears in the LLM prompt on every turn for the duration of the goal. Even a short goal string adds 15–30 tokens per turn. On the 4B tool model with a 2048-token context budget, this is a real and recurring cost across the full duration of a project session.

The heuristic goal detection (regex) is free. The context injection is not.

**The specific performance risk:** A user working on a project for 30 turns adds ~750 extra tokens to LLM calls over that session. At 5 tok/sec on a CPU, this adds up to 2.5 minutes of inference time distributed across those turns — invisible per-turn but significant in aggregate.

**What to do instead:** The active workflow state (`ContextStore.get_active_workflow()`) already provides operational continuity for multi-step tasks. For long-term project goals, the conversation history already contains the relevant context — the LLM can infer continuity from it without explicit goal injection.

**Revisit when:** A larger context model (8K+ n_ctx) is adopted, or when a fast summary layer reduces injected goal text to < 10 tokens.

---

### Allegation 3 — Structured Output Typing
**Final Verdict: IMPLEMENT**

**Why it passes:**
Adding `output_type: str = "text"` to `CapabilityExecutionResult` is a single-field dataclass change. Zero runtime cost. This field is used by the artifact system (Allegation 1) to record what kind of content was produced. No prompt injection involved.

**Why it is necessary:**
Without this field, the `WorkingArtifact` from Allegation 1 cannot distinguish between a list, a code block, or a plain summary — which affects how downstream tools (save to file, read aloud, export) handle the artifact.

---

### Allegation 4 — Cross-Turn Reference Resolution
**Final Verdict: IMPLEMENT**

**Why it passes:**
The reference registry (`last_list`, `selected_entity`, `active_document`) is stored in the session-state JSON blob alongside the artifact — no additional storage cost. Resolution is a dictionary lookup before `IntentRecognizer.plan()` — no LLM call.

The registry is populated by `ResponseFinalizer` which already post-processes every response. The overhead is a single regex scan of the assistant's last output to detect enumerated lists or named entities. This scan happens once per turn after the response is generated, not during inference.

**Net latency overhead: < 1 ms.**

**Why it is necessary:**
"Compare the second one", "use that file", "show me the third option" are common voice patterns that currently break because there is no binding for ordinal or entity references from prior turns.

---

### Allegation 5 — Incremental Planning
**Final Verdict: ALREADY IMPLEMENTED**

`TaskGraphExecutor` with DAG execution, `ToolStep.depends_on`, `CapabilityBroker._should_use_planner()`, and `ResearchPlannerWorkflow` are all present and functional. No implementation needed.

---

### Allegation 6 — Unified Runtime State (TurnContext)
**Final Verdict: DEFER**

**Why it is deferred:**
The `TurnContext` dataclass proposed in the validation document is a convenience wrapper that assembles existing data into one object. It provides no new capability — it is a refactoring convenience.

Once Allegation 1 is implemented, `active_artifact` and `reference_registry` are accessible via `MemoryService`. The `Kernel` DI container already provides unified access to all services. Building `TurnContext` now is premature abstraction before the data it would aggregate even exists in the system.

**Revisit when:** Multiple callers start duplicating the same assembly pattern, making a single composition object worthwhile.

---

### Allegation 7 — Streaming Cognitive Feedback
**Final Verdict: ALREADY IMPLEMENTED**

`TurnFeedbackRuntime` already publishes `assistant_ack`, `assistant_progress`, `tool_started`, `tool_finished`, `llm_started`, `llm_first_token`. `SpeechCoordinator` subscribes to `assistant_progress` and voices intermediate states. No implementation needed.

---

### Allegation 8 — Long-Horizon Task Persistence (Task Scheduler)
**Final Verdict: DEFER**

**Why it is deferred:**
A `TaskScheduler` daemon thread waking every 60 seconds and executing capabilities poses a real contention risk on a single i5-12th Gen. If a scheduled task triggers a research query at the same moment the user is speaking, both compete for CPU time — the scheduled task runs the tool model and the user's turn runs the chat model simultaneously on the same physical cores.

This requires a dedicated priority/exclusion mechanism that does not yet exist in the architecture. Building the scheduler without it would create unpredictable latency spikes during voice interaction.

**The implementation is sound in principle** — SQLite persistence and a daemon thread are the right approach. But it requires a turn-exclusion gate (don't fire scheduled tasks while `turn_feedback.active_turns > 0`) that needs careful testing.

**Revisit when:** The voice pipeline has explicit "idle" detection that the scheduler can observe.

---

### Allegation 9 — Multi-Modal Working Context
**Final Verdict: COVERED BY VLM IMPLEMENTATION**

The `WorkingArtifact` from Allegation 1, extended with `artifact_type: "image" | "pdf" | "audio_transcript"`, handles the reference problem (90%+ of multimodal use cases). The full `ContextObject` graph system described in the original docs is over-engineered for the current hardware and context window budget.

The VLM implementation document covers the practical path forward.

---

### Allegation 10 — Failure Recovery Intelligence
**Final Verdict: IMPLEMENT (partial)**

**What to implement:**
- Wire up `ToolStep.retries` in `TaskGraphExecutor._execute_node()`. The field already exists; activating it is ~10 lines. Retries only add latency when tools fail — zero overhead on the happy path.
- Add `fallback_capability: str = ""` to `CapabilityDescriptor`. Handlers with natural fallbacks (e.g., Chrome → Firefox) set it at registration. No runtime cost until a failure occurs.

**What to defer:**
- The "Failure Memory" system (tracking repeated tool failures to adjust routing confidence) is a subset of Allegation 12 (self-optimization). It requires the same background infrastructure and carries the same contention risk. Defer alongside Allegation 12.

**Net overhead: Zero on success path. Adds retry delay only on failure.**

---

### Allegation 11 — Resource-Aware Intelligence
**Final Verdict: IMPLEMENT (restricted scope)**

**What to implement:**
A `ResourceMonitor` using `psutil` with a 5-second snapshot cache. The snapshot is taken once at the start of `FridayApp._execute_turn()` and stored as `app.resource_snapshot`. The check is non-blocking (reads kernel counters, no I/O).

**The one adaptive policy worth activating now:**
```python
if snapshot.ram_available_mb < 2000:  # < 2 GB free RAM
    # Don't load the tool model for this turn; use chat model only
    style_hint = "concise"
```

This prevents OOM crashes when the VLM is loaded alongside both Qwen models (total ~5.2 GB when all three are resident).

**What NOT to implement yet:**
- CPU-based task deferral — too complex to implement safely without a priority queue
- Model unloading under RAM pressure — needs testing to avoid mid-conversation unload during a multi-turn workflow
- Thermal-state adaptation — not exposed reliably on Linux without root

**Net overhead: ~1 ms per turn (single psutil.virtual_memory() call, cached for 5 seconds).**

---

### Allegation 12 — Self-Optimization Feedback Loop
**Final Verdict: DEFER**

**Why it is deferred:**
A background `RouteOptimizer` thread reading accumulated outcome data and writing back to `RouteScorer` weights requires either:
1. Locking `RouteScorer` during weight updates (which can stall an in-flight routing decision), or
2. Atomic weight swapping (complex to implement correctly without races).

The data collection side already exists (`MemoryBroker.record_capability_outcome()`). The analysis and application side needs careful concurrent design that is out of scope for a performance-constrained local system.

**Additionally:** The feedback loop takes weeks of usage to accumulate statistically meaningful signal. Implementing it now means building infrastructure that won't produce observable behavior for months.

**Revisit when:** Capability outcome data is being actively read and there are > 500 recorded outcomes to analyze.

---

## Final Implementation List

### Implement Now

| # | Feature | Files to Change | Effort |
|---|---|---|---|
| 1 | Working Artifact Memory | `core/capability_registry.py`, `core/context_store.py`, `core/task_graph_executor.py`, `core/intent_recognizer.py` | Low |
| 3 | Output Typing (`output_type` field) | `core/capability_registry.py` | Trivial |
| 4 | Reference Registry | `core/response_finalizer.py`, `core/context_store.py`, `core/intent_recognizer.py` | Low |
| 10 | Wire retries + `fallback_capability` | `core/capability_broker.py`, `core/capability_registry.py`, `core/task_graph_executor.py` | Low |
| 11 | ResourceMonitor (restricted) | `core/turn_feedback.py` or new `core/resource_monitor.py`, `core/app.py` | Low |

**Combined estimated per-turn overhead: < 2 ms**

### Already Done — No Action Needed

| # | Feature | Status |
|---|---|---|
| 5 | Incremental Planning | `TaskGraphExecutor` + `ToolStep.depends_on` fully operational |
| 7 | Streaming Cognitive Feedback | `TurnFeedbackRuntime` fully operational |

### Deferred — Revisit Later

| # | Feature | Primary Reason for Deferral |
|---|---|---|
| 2 | Goal Continuity | Per-turn token injection overhead on small context window |
| 6 | TurnContext Snapshot | Premature abstraction; data accessible via existing MemoryService |
| 8 | Task Scheduler | CPU contention risk without idle-detection gate |
| 12 | Self-Optimization | Lock complexity + insufficient data to act on yet |

### Covered Elsewhere

| # | Feature | Covered By |
|---|---|---|
| 9 | Multi-Modal Context | VLM implementation + WorkingArtifact `artifact_type` extension |

---

## What This Gives FRIDAY

Implementing only the five items above delivers:

- **Pronoun resolution** — "save that", "read it", "export this" work naturally
- **Typed output tracking** — downstream tools know whether they're handling a list, code, or text
- **Cross-turn entity references** — "the second one", "that file", "the document I mentioned" resolve correctly
- **Resilient execution** — tools retry on transient failures; fallbacks activate automatically
- **RAM-aware scheduling** — prevents OOM when VLM is loaded alongside both Qwen models

All without adding any LLM calls, any background threads, or any per-turn context window budget increase.
