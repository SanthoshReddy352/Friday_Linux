# FRIDAY Refactor — Batched Implementation Plan

## Context

End-to-end manual testing (logs in `docs/Issues.md`, summarized) surfaced 14 categorized defects in FRIDAY's intent routing, multi-turn state, voice handling, memory pipeline, and tool coverage. Specific evidence captured in the logs:

- `Vector store unavailable: No module named 'chromadb'` on boot → RAG silently degraded.
- `set voice to manual` failed; `set voice mode to manual` worked → router is over-anchored.
- `create a calender evnet` (typo) fell through to chat mode.
- The word `next` in `…next year is my promotion` hijacked the YouTube `skip` workflow.
- `schedule a meeting in 15 minutes` saved the event with title `in 15 minutes`.
- `save that to a file called reverse.py` saved to the previously active `ideas.md`.
- After `Friday end memo` saved a memo, `read it` returned `ideas.md` not the memo.
- `read my latest email` returned `Gmail auth failed: Failed to get token`.
- A chat turn crashed with `Requested tokens (5445) exceed context window of 4096`.
- The word `enough` paused TTS but left the workflow alive (no global cancel).

Goal: address every issue holistically while preserving voice-first latency (sub-300ms routing budget), local CPU-only inference, and graceful offline fallback. The user has approved a 6-batch ordered execution, each committable independently.

---

## Architectural Decisions (User-approved)

1. **Routing**: Restore the `EmbeddingRouter` (already wired in `core/router.py:47`) by installing `sentence-transformers`; layer `rapidfuzz` for typo tolerance and add semantic boundary checks. Reserve Gemma-270M as a *future A/B* batch — only adopted if benchmarks show it beats fuzzy+embed under a 300ms budget.
2. **Calendar**: Single canonical path = **Google Workspace via `gws_client`**. Remove `create_calendar_event` / `list_calendar_events` / `move_calendar_event` / `cancel_calendar_event` handlers from `modules/task_manager/plugin.py`; keep reminders (`set_reminder`, `list_reminders`) which are local-only. Fix the `gws auth: Failed to get token` blocker as part of this batch.
3. **Web Research Agent**: Replace the `searxng_client` instance pool with `duckduckgo.com/html` scraping + `trafilatura` extraction.
4. **Scope**: All 14 issues, 6 ordered batches. Pause for user review between each batch.

---

## Research Synthesis (compact)

**Task 1 — Modern web research agents.** Perplexity-style stacks combine: (a) a search front-end (DuckDuckGo HTML, Brave API, or scraped Google SERP) → (b) URL fetch with realistic headers and short timeouts → (c) main-content extraction via `trafilatura`, `readability-lxml`, or `boilerpy3` → (d) chunking + cosine reranking of paragraphs against the query → (e) constrained synthesis with citation. For FRIDAY's CPU-only constraint we adopt: `httpx` async fetch of DDG HTML, `trafilatura.extract()` for main content, MiniLM cosine rerank against the query, Qwen3-1.7B for the final synthesis with `[1]`/`[2]` citation markers. Bypasses anti-bot via realistic UA + 1–2s jitter; no API key.

**Task 2 — Memory architecture.** Frontier assistants partition: (a) **immediate** session buffer (last ~20 turns, raw) (b) **episodic** long-term per-session summaries indexed by date/topic (c) **semantic** durable facts (user prefs, names, projects) in a vector store (d) **procedural** capability outcomes (success/failure traces). Retrieval is **gated** — not every turn pays the cost. Triggers: (i) pronoun present → semantic + working-artifact lookup; (ii) named entity present → semantic recall; (iii) capability invocation → procedural lookup. Context pruning uses a 70%-of-window watermark: once exceeded, summarize the oldest unsummarized block via the 1.7B chat model and replace with a single system note. FRIDAY already has the three tiers (`core/memory/episodic.py`, `semantic.py`, `procedural.py`) plus Mem0 wiring — what's missing is (a) the boot-time `chromadb` dependency check and (b) the watermark/pruning logic in `core/assistant_context.py:build_chat_messages()`.

**Task 3 — Tool framework.** MCP and AutoGen converge on the same minimum contract: each tool is a pure async function with (i) a Pydantic-typed input model, (ii) a Pydantic-typed output model, (iii) a docstring with explicit success/failure shapes, (iv) deterministic error envelopes (no raised exceptions across the tool boundary), (v) optional progress yields. For FRIDAY we keep the existing `register_tool(spec, handler, metadata)` API but wrap it with a `@capability(...)` decorator that derives the JSON schema from a Pydantic model and enforces an `Either[Ok, Err]` return shape. Atomic decomposition: `manage_file` and `open_file` become `create_file`, `append_to_file`, `delete_from_file`, `replace_in_file`, `read_file`, `open_file` (one verb each). The dialog flows orchestrate atoms; the LLM never sees a "manage_file" mega-tool.

**Task 4 — Function-Gemma-270M evaluation.** A 270M GGUF Q4 loads in ~150ms cold and runs at ~80–120 tok/s on i5-12 CPU. Cost-per-call dominated by prompt processing (~250ms for a 200-token prompt). If used *only* for argument extraction on intents that already deterministically match (≈70% of turns), per-turn overhead is acceptable. But replacing the deterministic+embedding router with Gemma-270M for *every* turn risks 300ms median routing latency — fatal for voice. Verdict: **defer** to a later A/B batch. Ship the embedding-router fix first; revisit only if Issues 8 and 11 persist in real-world testing.

---

## Batch 1 — Environment & Dependency Hardening (Issue 1)

Goal: no silent capability loss on boot.

- Update `requirements.txt` with pinned versions for `chromadb`, `sentence-transformers`, `markitdown[pdf]`, `trafilatura`, `rapidfuzz`, `httpx`, and `duckduckgo-search` (the last only as a dev convenience — implementation will not depend on it).
- Add `scripts/preflight.py`: imports every critical dep; on failure prints the exact `pip install …` command and exits non-zero **before** model load. Wire into `main.py` ahead of `FridayApp.__init__`.
- Add a `core/bootstrap/preflight.py` programmatic version invoked by `LifecycleManager` so the GUI mode also fails fast.
- Surface degraded modes in the HUD (`gui/hud.py`) — small badge if `chromadb`, `sentence-transformers`, or `markitdown` is unavailable, with a one-click "Show fix command" tooltip.
- Update `docs/testing_guide.md` with a new §0 "Preflight" section and add the regression row `[T-0.1] preflight aborts on missing chromadb`.

Critical files: `requirements.txt`, `main.py`, `core/bootstrap/lifecycle.py`, `scripts/preflight.py` (new), `gui/hud.py`, `docs/testing_guide.md`.

Verify: `python scripts/preflight.py` exits 0 with all deps; uninstall one dep → exits 1 with actionable message; `python main.py` boots with full RAG; logs no longer show `Vector store unavailable`.

---

## Batch 2 — Intent Routing & Semantic Boundaries (Issues 2, 7, 8, 9, 11)

Goal: human-tolerant routing under 50ms p95, no global keyword hijacks, correct entity order.

### 2a. Activate the EmbeddingRouter
- `core/embedding_router.py`: confirm MiniLM model path, lazy-load on first use, persist embedding cache to `data/embed_cache.npz`.
- `core/router.py:280`: keep the early dispatch, but require **two-signal agreement** to fire embedding-only — cosine ≥0.62 AND no slot extraction needed (already gated; verify the blocklist on line 50 is honored).
- Add a structured-args bridge: when embedding suggests a tool that needs args, hand off to the LLM tool planner with the embedding suggestion as a hint, not a decision.

### 2b. Loosen rigid regex with rapidfuzz (Issues 2, 8)
- Replace exact-phrase anchors in `core/router.py:_default_patterns_for()` (lines 1043–1092) with a unified `_match_command(text, canonical_phrase, threshold=85)` helper using `rapidfuzz.fuzz.token_set_ratio`. Tokens like "mode" become optional via canonical phrase list per intent, not regex alternation.
- New module `core/text_normalize.py`: STT-typo correction table (`calender→calendar`, `evnet→event`, `recieve→receive`, …) applied **once** before routing, kept short and conservative.
- Keep the embedding router as the second line of defense: anything that fuzzy-misses but is semantically close still routes correctly.

### 2c. Semantic boundary checks for global keyword listeners (Issue 9)
- `core/workflow_orchestrator.py:BrowserMediaWorkflow.can_continue()` (line 224): only fire on bare media verbs when (a) a media workflow is *currently active*, **or** (b) the utterance is short (<5 tokens) and contains no other action verb. Implement via a new `_is_media_command(text)` predicate that rejects sentences containing personal-fact verbs (`work`, `remember`, `learn`, `said`, etc.).
- Add an `intent_priority` to each workflow descriptor; tighten the precedence so `FileWorkflow` / `ReminderWorkflow` outrank `BrowserMediaWorkflow` when both partially match.

### 2d. Entity extraction order (Issue 11)
- `core/intent_recognizer.py:_extract_summary_entity()` and `_extract_start_dt()`: extract temporal expressions **first** with `dateparser` (already a transitive dep) or a tight regex, strip them from the input, then run title extraction on the residue. Add a unit test for `schedule a meeting in 15 minutes` → `title="Meeting"`, `start_delta=15m`.

### 2e. Tool taxonomy disambiguation (Issue 7)
- The collision lives in `modules/task_manager/plugin.py:189-200`. Two changes: (i) remove the `calendar|agenda|events` alternation from the reminders regex — keep it `reminders` only; (ii) the new GWS-only calendar (Batch 5) owns `calendar|agenda|events`. Net: `what's on my calendar` → GWS; `list reminders` → local.

Critical files: `core/router.py`, `core/embedding_router.py`, `core/intent_recognizer.py`, `core/workflow_orchestrator.py`, `core/text_normalize.py` (new), `modules/task_manager/plugin.py`, `tests/test_router_fuzzy.py` (new), `tests/test_entity_extraction.py` (new), `docs/testing_guide.md`.

Verify: `set voice to manual` works; `create a calender evnet` routes correctly; `…next year is my promotion` does not trigger media skip; `schedule a meeting in 15 minutes` extracts `title=Meeting` + `delta=15m`. Add `[T-2.x]` rows for each.

---

## Batch 3 — Barge-In & Global Cancellation (Issue 3)

Goal: `stop`/`enough`/`wait`/`Friday cancel` are real interrupts, not just TTS pauses.

- New module `core/interrupt_bus.py`: `InterruptBus` singleton with `signal(reason, scope)` and async `wait_for_signal()`. Scope = `tts | inference | workflow | all`. Cancellation is **cooperative** — every long-running coroutine checks the bus at await points.
- `modules/voice_io/stt.py:BARGE_IN_WORDS` (line 20) and `TASK_CANCEL_WORDS`: collapse into a single `STOP_WORDS` set. On detection, emit `interrupt_bus.signal("user_stop", scope="all")`.
- `modules/voice_io/tts.py`: subscribe to `tts|all` scope; flush queue and release `_speak_lock`.
- `core/model_manager.py:60-63`: each inference path acquires the lock as today **and** subscribes to `inference|all` scope. On signal: `llama_cpp` supports `stopping_criteria` — pass an `InterruptStoppingCriteria` that returns True when the bus has fired, then release the lock.
- `core/workflow_orchestrator.py:continue_active()`: check the bus at the top of each turn; if signaled, cancel the active workflow (already exposed via `cancel_active_workflow`) and reset `DialogState.pending_clarification` / `pending_file_request` / `pending_file_name_request`.
- `core/dialog_state.py`: add a `reset_pending(reason)` helper, call it from the cancel path.
- The phrase `Friday cancel` (anywhere) becomes a global cancel verb; document in `docs/testing_guide.md`.

Critical files: `core/interrupt_bus.py` (new), `modules/voice_io/stt.py`, `modules/voice_io/tts.py`, `core/model_manager.py`, `core/workflow_orchestrator.py`, `core/dialog_state.py`, `tests/test_interrupt_bus.py` (new), `docs/testing_guide.md`.

Verify: during a long TTS playback, saying `enough` halts speech, releases the inference lock (next turn works immediately), and clears any pending clarification. `Friday cancel` mid-workflow returns to neutral.

---

## Batch 4 — Multi-Turn State Machines (Issues 4, 5, 6, 7, 10)

Goal: deterministic, cancellable, pronoun-correct file workflows.

### 4a. Generic state machine framework
- New module `core/workflows/state_machine.py`: `class WorkflowFSM`, declarative `State`, `Transition`, `pending_slots`. Each state has `enter(ctx)`, `handle(text, ctx)`, `exit(ctx)`. Global cancel transition (driven by `interrupt_bus`) wired automatically. Replaces the ad-hoc `_handle_*` methods in `core/workflow_orchestrator.py:FileWorkflow`.
- `WorkingArtifact` gains `created_at: datetime` and `scope: Literal["session","explicit","auto"]`. Auto-set artifacts expire after **3 turns** of non-reference; explicit-set artifacts persist until overwritten. (Issue 10 / Issue 7 fix.)

### 4b. File creation FSM (Issue 4) — exact flow from `docs/Issues.md`
- States: `Idle → AwaitName → Created → AskWriteContent → AskDictateOrGenerate → DictationLoop|GenerationTopic → Save → Done`.
- `AwaitName`: if name missing, prompt; on response, validate filename (legal chars, no path traversal) and resolve folder via `DialogState.last_folder` or default `~/Documents`.
- `Created`: set the new file as the **explicit-scope** working artifact, eclipsing any prior one. Pronouns `it/that/this` now resolve to the new file. (Fixes Issue 10 directly.)
- `AskWriteContent`: `"Created file X. Would you like me to write anything in it?"` → yes/no parser; no → `Done` (graceful terminate, artifact remains).
- `AskDictateOrGenerate`: dictate → start dictation session with target file set to current artifact; generate → ask topic if none, run Qwen3-1.7B with a constrained prompt, save.
- Global rule: `Friday cancel` at any state → `Idle` and clear pending slots (`InterruptBus`-driven).
- Post-creation: `read it` / `open it` resolve to the just-created file (Issue 7 follow-up).

### 4c. File edit FSM (Issue 5)
- Replace `append`-only handler with `EditWorkflow`. States: `Idle → AwaitTarget → AwaitAction(Add|Delete|Update) → AwaitDetails → Confirm → Execute → Done`.
- `Add`: same dictate-or-generate sub-flow as creation, then append to the file's tail (preserve trailing newline).
- `Delete`: prompt for what to delete; pass the file content + the target snippet to Qwen3-4B with a **strict** system prompt that returns *only* the new file content with the snippet removed. Diff-validate (no more than the requested span changed) before write. If diff fails, return to `AwaitDetails`.
- `Update`: same harness as `Delete` but the LLM rewrites the matched section; same diff-validation.
- Cancellation and pronoun rules identical to 4b.

### 4d. save_note alignment (Issue 6)
- The `save_note` intent in `modules/task_manager/plugin.py` is a standalone tool, not a dictation operation. Decouple: `save_note` accepts inline content (`save note milk, bread` → content="milk, bread") **and** can start a short dictation session if no content is provided (`save note → "What's the note?" → dictate → save`). Remove the misleading `"I'm not in a dictation session right now"` error.

### 4e. Dictation followup (Issue 7)
- `modules/dictation/service.py:91-109` — after the save, populate the working artifact with `source_path=session.file_path`, `capability_name="dictation"`, `scope="explicit"`. One-line fix backed by 4a.

Critical files: `core/workflows/state_machine.py` (new), `core/workflows/file_creation.py` (new), `core/workflows/file_edit.py` (new), `core/workflow_orchestrator.py` (register the new FSMs, retire `FileWorkflow`), `core/context_store.py` (artifact scope/timestamp), `modules/dictation/service.py`, `modules/task_manager/plugin.py`, `tests/test_file_creation_fsm.py` (new), `tests/test_file_edit_fsm.py` (new), `tests/test_artifact_scope.py` (new), `docs/testing_guide.md`.

Verify: walk through every state of Issue 4 & 5 flows; `Friday cancel` works at each prompt; `save that to reverse.py` correctly creates `reverse.py` (not `ideas.md`); after dictation memo save, `read it` reads the memo.

---

## Batch 5 — Missing Tools (Issues 12, 13) & Confirmation Hygiene

Goal: full calendar CRUD on the GWS path; offline-first weather; no `"yes"` cross-talk between pending confirmations.

### 5a. Google Workspace calendar full CRUD
- Fix the auth blocker first: `modules/workspace_agent/gws_client.py` — diagnose `Gmail auth failed: Failed to get token`. Likely the keyring entry or the `gws` CLI session expired. Add a `gws_client.ensure_auth()` that detects "Failed to get token" and surfaces a clear "Run `gws auth` once" message to the user (not a silent failure).
- Add `update_calendar_event(event_id, title?, start?, end?, description?)`, `cancel_calendar_event(event_id_or_title)`, `delete_calendar_event(event_id)` to `gws_client.py` and register as tools in `modules/workspace_agent/extension.py`.
- Remove the calendar handlers from `modules/task_manager/plugin.py` (lines ~196 patterns, handler funcs). Keep reminders (`set_reminder`, `list_reminders`) — those are local and orthogonal.
- Resolve `cancel the next event` / `update the dentist meeting to 4pm`: a small entity resolver that loads upcoming events and matches by `title` / `next` / `today's 3pm` etc. Use rapidfuzz token match for title resolution.

### 5b. Weather tool (Issue 13)
- New plugin `modules/weather/plugin.py`: tool `get_weather(location: str, when?: "now"|"today"|"tomorrow"|"week" = "now")`.
- Implementation: Open-Meteo (`api.open-meteo.com`, no API key) for forecast; Nominatim (`nominatim.openstreetmap.org`) for geocoding, with a 24h disk cache.
- Mark `connectivity="online"`, `latency_class="fast"`. Should bypass the `"Go online?"` clarify prompt because weather is universally implicit-online (already covered by `consent.py:CURRENT_INFO_PATTERNS:60` — verify the auto-approve path fires).

### 5c. Confirmation hygiene (logs anomaly: `yes` to weather routed to `Saved ideas.md`)
- `core/capability_broker.py:244-291`: `pending_online` is keyed by session only. Make it scope-aware — store `{tool_name, slot_signature, expires_at}` and clear it when a turn passes that doesn't match. A `yes` is only honored if the immediately-previous turn was the confirmation prompt for the *same* pending tool.
- Add `core/capability_broker.py:_invalidate_stale_pending()` called at the top of every turn; default TTL 60s.

Critical files: `modules/workspace_agent/gws_client.py`, `modules/workspace_agent/extension.py`, `modules/task_manager/plugin.py`, `modules/weather/plugin.py` (new), `modules/weather/openmeteo.py` (new), `core/capability_broker.py`, `core/consent.py`, `tests/test_weather.py` (new), `tests/test_calendar_crud.py` (new), `tests/test_confirmation_scope.py` (new), `docs/testing_guide.md`.

Verify: `cancel my 3pm event` works; `update dentist to 4pm` works; `what's the weather in Mumbai` returns a structured forecast in <2s and does *not* trigger the chat fallback; `yes` after a weather prompt only resolves the weather pending, never another workflow.

---

## Batch 6 — Web Research, Memory, Context Window

Goal: working research agent; tiered memory with retrieval gating; no more 4096-token blowouts.

### 6a. Research Agent rewrite
- Replace `modules/research_agent/searxng_client.py` with `modules/research_agent/ddg_client.py`:
  - `httpx.AsyncClient` (HTTP/2, realistic UA), `GET https://html.duckduckgo.com/html/?q=…`, parse SERP with `selectolax` (faster than bs4).
  - For top-N results (default 5), parallel `httpx.get(url, timeout=4.0)`, then `trafilatura.extract(html)` for clean text.
  - Cosine-rerank paragraphs against the query using the same MiniLM model from Batch 2; keep top-K paragraphs under a 1500-token budget.
  - Synthesize with Qwen3-1.7B; system prompt enforces citation markers `[1]`, `[2]`, returned as a citations list alongside the answer.
- `service.py` orchestrates fetch+extract+rerank+synthesize as 4 async stages with a 6s total budget. Stream the answer to TTS as soon as the first sentence is ready.

### 6b. Memory & retrieval gating
- `core/assistant_context.py:build_chat_messages()` (lines 166-200): add a **retrieval gate** — semantic recall only runs when (a) the user's text contains a proper noun / pronoun, **or** (b) the topic shifted (cosine drop > 0.4 vs. previous turn). Otherwise inject only the last-3-turn buffer + persona.
- Define explicit tier contracts in `core/memory/__init__.py`:
  - Immediate buffer = `core/dialog_state.history` (last 20).
  - Episodic = SQLite `turns` table with a per-session summary materialized every 20 turns.
  - Semantic = ChromaDB `friday_memory` + Mem0 facts.
  - Procedural = `core/memory/procedural.py` capability traces (already in place).
- Move all `memory_service` writes through a single `record_turn(turn)` entry point (already added in 2026-05-14 hardening — verify no caller bypasses it).

### 6c. Context window pruning
- New helper `core/context_window.py:fit_messages(messages, model_n_ctx, response_budget=512)`:
  - Token-count via `llama_cpp.Llama.tokenize` (already imported).
  - If `prompt_tokens > model_n_ctx - response_budget`: summarize the **oldest** unsummarized block (5+ turns) via Qwen3-1.7B with `max_tokens=200`. Replace the block with a system message: `[summary: 5 turns earlier — …]`.
  - Cache summaries on the session so repeated turns don't re-summarize.
- Wire into `modules/llm_chat/plugin.py:_build_messages()` and the tool-planner prompt.

Critical files: `modules/research_agent/ddg_client.py` (new), `modules/research_agent/extractor.py` (new), `modules/research_agent/service.py` (rewrite), `modules/research_agent/plugin.py`, `core/assistant_context.py`, `core/context_window.py` (new), `core/memory/__init__.py`, `core/memory_service.py`, `modules/llm_chat/plugin.py`, `tests/test_ddg_research.py` (new), `tests/test_context_window.py` (new), `tests/test_memory_gating.py` (new), `docs/testing_guide.md`.

Verify: `research the latest news on Mars helicopter` returns a 2-3 sentence cited synthesis in <6s; a 30-turn chat session never crashes with the 4096-token error; semantic recall fires only on pronouns/named entities (check the new debug log line).

---

## Code Interfaces

### Capability framework (Batch 4 prep / Batch 6 finalize)

```python
# core/capability_framework.py
from pydantic import BaseModel
from typing import Generic, TypeVar, Literal, Awaitable, Callable
from dataclasses import dataclass

I = TypeVar("I", bound=BaseModel)
O = TypeVar("O", bound=BaseModel)

class Ok(BaseModel, Generic[O]):
    status: Literal["ok"] = "ok"
    value: O

class Err(BaseModel):
    status: Literal["err"] = "err"
    code: str          # "invalid_args" | "not_found" | "permission" | "external" | "internal"
    message: str
    recoverable: bool

Result = Ok[O] | Err

@dataclass(frozen=True)
class CapabilityMeta:
    connectivity: Literal["local", "online", "either"]
    latency_class: Literal["instant", "fast", "slow"]
    permission_mode: Literal["auto", "ask_first", "explicit"]
    side_effect_level: Literal["none", "read", "write", "destructive"]
    streaming: bool = False

def capability(name: str, meta: CapabilityMeta):
    def deco(fn: Callable[[I], Awaitable[Result]]):
        # derives JSON schema from fn's first arg Pydantic model,
        # registers via app.router.register_tool at plugin load
        ...
        return fn
    return deco
```

### Tiered memory

```python
# core/memory/tiers.py
class ImmediateBuffer:           # core/dialog_state.History
    def recent(self, n: int = 20) -> list[Turn]: ...

class EpisodicTier:               # SQLite turns + per-session summaries
    def fetch_session_summary(self, session_id: str) -> str | None: ...
    def fetch_recent_episodes(self, query_embedding, k: int = 3) -> list[Episode]: ...

class SemanticTier:               # ChromaDB + Mem0
    def search(self, query: str, k: int = 5) -> list[Fact]: ...
    def upsert_fact(self, text: str, metadata: dict) -> None: ...

class ProceduralTier:             # capability outcome traces
    def lookup_outcomes(self, capability: str, k: int = 3) -> list[ProcedureTrace]: ...

class MemoryBroker:
    def build_context(self, query: str, session_id: str, *, gate: bool = True) -> ContextBundle: ...
    def record_turn(self, turn: Turn) -> None: ...
```

### Workflow FSM

```python
# core/workflows/state_machine.py
@dataclass
class State:
    name: str
    enter: Callable[[FSMContext], Awaitable[Response | None]] | None = None
    handle: Callable[[str, FSMContext], Awaitable[Transition]] | None = None

@dataclass
class Transition:
    target_state: str
    response: Response | None = None
    update_slots: dict[str, Any] = field(default_factory=dict)
    cancel: bool = False

class WorkflowFSM:
    name: str
    states: dict[str, State]
    start_state: str
    pending_slots: list[str]      # for slot-filling
    cancel_words: set[str]        # auto-wired to InterruptBus

    async def start(self, ctx: FSMContext) -> Response: ...
    async def handle_turn(self, text: str, ctx: FSMContext) -> Response: ...
    async def cancel(self, ctx: FSMContext, reason: str) -> Response: ...
```

---

## Verification (end-to-end)

After each batch, run the targeted automated tests **and** walk the relevant section of `docs/testing_guide.md` manually with `python main.py`. Each batch's commit message references the issue numbers it closes.

Final acceptance criteria — all 14 issues exercised via the testing guide, plus:
- `pytest tests/ -x` passes (current baseline: 378 passing; target: ~430+ after new tests).
- Boot-to-first-greeting latency unchanged (≤4s) — confirm Batches 1 and 6's added work runs lazily.
- Average routing latency p95 < 50ms on deterministic paths; < 250ms when the embedding router fires.
- No 4096-token errors over a synthetic 50-turn chat stress test.

---

## Modification Log obligation

Per project `CLAUDE.md`, every batch must add a row to `docs/testing_guide.md` Modification Log dated 2026-05-15 (and following days), add or update test cases with the next `[T-N.M]` ID, and add a §17 regression guard for any must-not-break behavior introduced.
