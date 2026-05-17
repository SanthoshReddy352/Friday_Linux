# JARVIS (vierisid) vs FRIDAY — Comparative Report

> **Date:** 2026-05-16
> **Reference repo:** `https://github.com/vierisid/jarvis`
> **Local clone for source-reading:** `scratch/jarvis-ref/` (shallow, depth=1)
> **Method:** Cloned and read jarvis source files directly. Cross-referenced against
> FRIDAY's `core/`, `modules/`, and `skills/`. Findings cite exact files on both sides.
>
> **This document does not propose code changes by itself.** Section 14 is the
> compatibility matrix; section 15 is the recommended top-10 adoption list.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Positioning](#2-project-positioning)
3. [Architectural Comparison](#3-architectural-comparison)
4. [Memory & Knowledge Systems](#4-memory--knowledge-systems)
5. [Tool Inventory Comparison](#5-tool-inventory-comparison)
6. [Multi-Agent & Delegation](#6-multi-agent--delegation)
7. [Awareness & Proactivity](#7-awareness--proactivity)
8. [Authority & Safety](#8-authority--safety)
9. [Workflows & Automation](#9-workflows--automation)
10. [Goal Pursuit](#10-goal-pursuit)
11. [Cross-OS Strategy — Tool Implementation Patterns](#11-cross-os-strategy--tool-implementation-patterns)
12. [What jarvis Does Better than FRIDAY](#12-what-jarvis-does-better-than-friday)
13. [What FRIDAY Does Better than jarvis](#13-what-friday-does-better-than-jarvis)
14. [Compatibility Validation Matrix](#14-compatibility-validation-matrix)
15. [Prioritized Adoption Roadmap — Top 10 Ports](#15-prioritized-adoption-roadmap--top-10-ports)
16. [References & Caveats](#16-references--caveats)

---

## 1. Executive Summary

`vierisid/jarvis` and FRIDAY share the same product north star — a personal AI
assistant that does work for you — but they make almost opposite engineering bets.
JARVIS is an **always-on TypeScript daemon** with a **Go sidecar fleet** that talks to
cloud LLMs and runs across many machines. FRIDAY is a **single-process Python voice
assistant** with **local on-device LLMs** that runs on one machine and listens for
a wake word.

The differences are not just stylistic. They drive what each project can do well:

| Where jarvis is genuinely ahead | Where FRIDAY is genuinely ahead |
|---|---|
| Continuous desktop awareness (5-second screen capture, OCR, struggle detection) | Truly local voice loop (wake word + on-device STT + on-device chat/tool LLM + Piper TTS) |
| Multi-machine fleet via Go sidecar with JWT-auth WebSocket | Sophisticated Wayland/X11 screenshot fallback chain (8 strategies in one file) |
| Visual + NL workflow builder with 50+ node types | LangGraph-backed stateful multi-turn workflows |
| OKR-style goal pursuit with morning/evening rhythm + escalation | Three-tier memory (episodic/semantic/procedural) + Mem0 + ChromaDB |
| Authority engine with audit trail, governed categories, voice-approval gating | Capability descriptor schema (connectivity/latency_class/permission_mode/side_effect_level) |
| Multi-LLM router with provider fallback chain (7 providers) | TurnOrchestrator v2 with TaskGraphExecutor (parallel tool plans) |
| Vault knowledge graph: entities + facts + relationships + commitments | World Monitor geopolitical news plugin |

The single most useful pattern jarvis offers FRIDAY is its **Go sidecar cross-OS
template**. jarvis's TypeScript-side `linux.ts`/`windows.ts`/`macos.ts` are mostly
stubs that throw "use sidecar"; the real cross-platform work lives in
`sidecar/platform_{linux,windows,darwin}.go` files guarded by `//go:build` tags, with
a **preflight stage** that reports unavailable capabilities to the brain on
connect. FRIDAY could adopt the *shape* of this pattern (per-platform adapter
modules + preflight) without adopting the sidecar architecture itself — see
§11.4 and §15.

The single most useful pattern FRIDAY offers jarvis is its **local-first stance** —
jarvis cannot work offline at all, since the brain requires an LLM provider and the
sidecars require the brain. FRIDAY can drive its full conversation loop on a laptop
with no network. This is a strategic moat the comparison should not erode.

---

## 2. Project Positioning

### 2.1 jarvis — always-on autonomous daemon

From `README.md` and `VISION.md`:

- **Tagline:** "the most powerful autonomous AI daemon on the planet"
- **Process model:** A long-running **brain daemon** (Bun + TypeScript) holding state,
  exposing HTTP + WebSocket + a React 19 dashboard. Multiple **sidecars** (Go binaries
  with JWT-auth WebSocket connections) attach from any machine and provide
  desktop/browser/terminal/filesystem/clipboard/screenshot capabilities on that
  machine. The brain decides; the sidecars do.
- **Persona of the user:** A solo founder / power user who wants the agent to act
  on goals across multiple devices, with continuous awareness of what they're
  doing on screen.
- **LLM stance:** Cloud-first. Bundles Anthropic, OpenAI, Gemini, Ollama, Groq,
  NVIDIA, OpenRouter providers — `bun run src/llm/test.ts` verifies setup. Local
  via Ollama is supported but the README treats Anthropic Sonnet 4.5 as the
  recommended default.
- **Tests:** "379 tests passing across 22 test files", "~65,000 lines TypeScript + Go".
- **Distribution:** `bun install -g @usejarvis/brain`, Docker, or a curl one-liner.
  License is Jarvis Source Available License 2.0 (RSALv2-based) — not OSI-approved
  open source.

### 2.2 FRIDAY — local-first voice assistant

From `CLAUDE.md`, `config.yaml`, `core/app.py`:

- **Tagline:** "local-first, cross-platform AI assistant (Linux + Windows)" with a
  "modular plugin architecture", "v2 turn orchestration pipeline", and "three-tier
  memory system (episodic, semantic, procedural)".
- **Process model:** A **single Python process** (Tkinter HUD via `gui/hud.py`, no
  dashboard) with a wake-word loop, voice-first turn pipeline, and an in-process
  plugin/Extension system. Same process, no IPC, one machine.
- **Persona of the user:** A power user who wants a private voice assistant with
  the conversational UX of a Jarvis-style AI, runnable on personal hardware.
- **LLM stance:** Local-first. `config.yaml` declares:
  - chat model: `mlabonne_Qwen3-1.7B-abliterated-Q4_K_M.gguf` (preload, n_ctx=4096)
  - tool model: `mlabonne_Qwen3-4B-abliterated-Q4_K_M.gguf` (preload, n_ctx=2048)
  - vision: `SmolVLM2-2.2B-Instruct-Q4_K_M.gguf`
  - STT: `whisper base.en` (int8, 8 CPU threads)
  - wake word: `hey_friday.onnx` (openwakeword)
  - TTS: Piper (local)
- **Tests:** "378 tests pass" per `MEMORY.md` (Production hardening 2026-05-14).
  ~15,500 lines in `core/` + `modules/`.
- **Distribution:** `setup.sh` / `setup.ps1` scripts; not packaged for an installer.

### 2.3 Side-by-side capability matrix

| Capability | jarvis | FRIDAY |
|---|---|---|
| Language(s) | TypeScript (Bun) + Go (sidecar) | Python 3 |
| Process model | Daemon + N sidecars over WebSocket | Single process |
| GUI | React 19 + Tailwind 4 + `@xyflow/react` dashboard | Tkinter HUD (`gui/hud.py`) |
| Voice in | Web Audio (WebM over WS) + openwakeword | Whisper local STT + openwakeword + clap detector |
| Voice out | Edge TTS / ElevenLabs (cloud) | Piper (local, on-disk binary) |
| Wake word | openwakeword (ONNX) | openwakeword (ONNX `hey_friday`) |
| Vision | Cloud Vision (Anthropic/Gemini) | SmolVLM2-2.2B local GGUF + cloud fallback via `gemini_live_skill` |
| Cross-OS | Build-tagged Go binaries in sidecar | `platform.system()` branching inside Python modules |
| Memory model | Single SQLite vault (~30 tables) | ChromaDB + SQLite (`data/friday.db`) + Mem0 + 3-tier in-memory layer |
| Tool registration | `ToolRegistry.register(ToolDefinition)` in TS | `CapabilityRegistry.register_tool(spec, handler, metadata)` in Python |
| Routing | LLM-only (agent loop, up to 200 iterations) | 3-tier waterfall (IntentEngine → PlannerEngine[Qwen] → ChatModel[Qwen]) |
| Parallel tool execution | Workflow engine has parallel `Promise.all` waves | `TaskGraphExecutor` topological waves (`core/task_graph_executor.py`) |
| Workflows | Visual builder + NL builder + YAML, 50+ nodes | `WorkflowOrchestrator` LangGraph state machines + a handful of workflows in `core/workflow_orchestrator.py` |
| Goal tracking | 5-level OKR hierarchy with health/escalation | `task_manager` plugin (notes + reminders) |
| Authority | Numeric levels + governed categories + audit + voice-gate | `ConsentService` + `PermissionTier` + `online_permission_mode` |
| Continuous awareness | 5–10 s screen capture + OCR + struggle detector | None continuous; on-demand vision and `world_monitor` polling |
| Multi-agent | Hierarchy tree + `delegate_task` + sub-agent runner + commitments | Single-agent + `core/delegation.py` (147 LoC) + workspace_agent / research_agent modules |
| External comms | Telegram, Discord, Signal, WhatsApp channels | WhatsApp skill + email_ops skill |
| Cloud integrations | Google API + Google Auth (OAuth) | Gemini Live skill |
| Plugin distribution | TypeScript SDK + GitHub-based | Python modules in-tree under `modules/` and `skills/` |

---

## 3. Architectural Comparison

### 3.1 Process model — daemon+sidecar vs single-process plugin

**jarvis:**
```
DAEMON (Bun, one process)
├── HTTP + WebSocket server (Bun.serve)
├── React dashboard served from same port
├── LLMManager (provider fallback chain)
├── Vault (bun:sqlite, WAL mode)
├── AgentHierarchy + AgentTaskManager + sub-agent runner
├── AuthorityEngine + AuthorityLearner + EmergencyController
├── AwarenessService (consumes sidecar events)
├── WorkflowEngine (NodeRegistry + executor + variables)
├── GoalService (rhythm timer 60s + accountability 5min + health 15min)
└── ToolRegistry (registers ~30+ tools at boot)
    │
    │ JWT-authenticated WebSocket (one per sidecar)
    ▼
SIDECAR 1: Go binary running on machine A
SIDECAR 2: Go binary running on machine B
SIDECAR N: ...
  each sidecar advertises capabilities = [terminal, filesystem, desktop, browser,
                                          clipboard, screenshot, system_info,
                                          awareness, ocr]
  brain routes RPC calls to sidecars by name via the `target` parameter on tools
```

**FRIDAY:** `core/app.py` (`FridayApp`) wires 24 services in explicit order in
`__init__`. There is no separate process — the same Python interpreter that listens
for the wake word also queries the local LLM, runs tool handlers, plays TTS, and
shows the Tkinter HUD.

**Implication:** jarvis can be deployed *across* machines (one brain, many sidecars).
FRIDAY is single-machine by design. Adding sidecar support to FRIDAY would be a
large change (new IPC layer, auth, retry semantics) that is not justified unless the
project is going to support fleet deployment — see §14 (`INCOMPATIBLE` row).

### 3.2 Language stack — TypeScript/Bun+Go vs Python

| Concern | jarvis | FRIDAY |
|---|---|---|
| Runtime | Bun (not Node) — `bun:sqlite`, `Bun.serve`, `Bun.spawn`, `Bun.file` | CPython 3.11+ |
| Type safety | TypeScript strict; ESM | Python typing (gradual; many modules typed via `from __future__ import annotations`) |
| Concurrency | Single-threaded event loop, Promise.all for parallel work | `asyncio` + `ThreadPoolExecutor`; LLM inference threads guarded by `asyncio.Lock` in v2 |
| Native code | Go sidecar handles platform syscalls; TS daemon stays pure | All Python; native syscalls via subprocess shells or platform-specific libs (`mss`, `pyautogui`, `gi`) |
| LLM client | `llama.cpp` not used; relies on remote provider HTTP APIs | `llama-cpp-python` for local GGUF inference |

**Implication:** Code reuse between the two projects requires translation, not
copy-paste. The *patterns* port; the code does not.

### 3.3 Control flow — agent loop vs TurnOrchestrator

**jarvis:** A standard "agent loop". `sub-agent-runner.ts` runs up to **200
iterations** of "LLM proposes tool call → execute → feed back result" until the LLM
emits a stop_reason of `end_turn`. The system prompt + vault context + tools list +
authority rules are injected each iteration.

**FRIDAY (v2):** A **single turn**. `TurnOrchestrator.handle()` runs three stages:
1. `IntentEngine.classify()` — deterministic parsers (regex + alias + scorer); if
   confidence ≥ 0.9, short-circuit to that tool.
2. `PlannerEngine.plan()` — Qwen tool model produces an `ExecutionPlan` (DAG of
   `ToolNode` with dependencies).
3. `TaskGraphExecutor.execute(plan)` — topological waves, `asyncio.gather` per wave.

There is no looping agent. A multi-step task is one DAG executed in waves, then a
response. If a tool fails, the wave records the error and continues with
independent nodes.

**Trade-off:** jarvis's agent loop is more flexible (can react to a tool result by
choosing a completely different next tool). FRIDAY's plan-then-execute is faster
and more predictable, but cannot revise the plan mid-flight.

### 3.4 Concurrency — Bun async vs asyncio+ThreadPool

**jarvis:** Pure async/await on a single Bun thread. Workflow engine runs nodes via
`Promise.all` for parallelism; sub-agents are launched as background Promises that
`onComplete` fires when done (`src/agents/task-manager.ts:62-87`).

**FRIDAY:** `asyncio` event loop for the orchestration; `ThreadPoolExecutor` for
LLM inference (since `llama-cpp-python` is synchronous). v2 design (per
`docs/friday_architecture.md` §11) gives each LLM domain its own executor + lock,
and research summarisation a separate executor so it cannot starve a turn.

### 3.5 Plugin systems

| Aspect | jarvis | FRIDAY |
|---|---|---|
| Registration call | `toolRegistry.register({ name, description, category, parameters, execute })` (`src/actions/tools/registry.ts:30-37`) | `ctx.register_capability(spec, handler, metadata)` (`core/extensions/protocol.py:61-82`) |
| Parameter schema | `Record<string, ToolParameter>` with `{type, description, required}` validated at register time and per call | `dict` schema; richer descriptor includes `connectivity`, `latency_class`, `permission_mode`, `side_effect_level`, `streaming`, `output_schema`, `provider_kind` (`core/capability_registry.py:21-36`) |
| Distribution | `package.json` workspace + GitHub-based extension repos | In-tree under `modules/` and `skills/`; no external SDK |
| Isolation from kernel | None explicit — tools get globals via imports | `ExtensionContext` exposes only `registry`, `events`, `consent`, `config` (no `FridayApp` ref) — explicitly narrow by design (`core/extensions/protocol.py:22-99`) |

**Verdict:** FRIDAY's `CapabilityDescriptor` is *richer* than jarvis's
`ToolDefinition`. jarvis tools cannot declare `online`-ness, latency class, or
side-effect level. FRIDAY's `ExtensionContext` is also a cleaner isolation
boundary than jarvis's "tools just import what they need".

---

## 4. Memory & Knowledge Systems

This is one of the largest design deltas. jarvis has a **single SQLite Vault** with
~30 typed tables modelling explicit entities/relationships; FRIDAY has a **three-tier
in-process memory layer** (episodic/semantic/procedural) plus ChromaDB and Mem0,
sitting on top of `ContextStore` (SQLite) and accessed via the `MemoryService` facade.

### 4.1 jarvis Vault — typed knowledge graph

`src/vault/schema.ts` initialises **all tables on startup**. The knowledge-graph
core is:

| Table | Purpose | Notable columns |
|---|---|---|
| `entities` | People/projects/tools/places/concepts/events | `type` enum constraint, `name`, `properties` JSON |
| `facts` | Atomic knowledge | `subject_id` (FK → entities), `predicate`, `object`, `confidence ∈ [0,1]`, `source`, `verified_at` |
| `relationships` | Typed edges | `from_id`, `to_id`, `type`, `properties` JSON |
| `commitments` | Promises the AI made | `what`, `when_due`, `priority`, `status`, `retry_policy`, `assigned_to`, `result` |
| `observations` | Raw events | `type`, `data`, `processed` flag |
| `vectors` | Embeddings | `ref_type`, `ref_id`, `embedding` BLOB, `model` |
| `agent_messages` | Inter-agent comms | `from_agent`, `to_agent`, `type` (task/report/question/escalation), `priority`, `requires_response`, `deadline` |
| `personality_state` | Personality model JSON | single row by default |
| `conversations` + `conversation_messages` | Chat history | `channel`, `role` (user/assistant/system), `tool_calls` |

…plus 20+ feature-specific tables: `content_items`, `approval_requests`,
`audit_trail`, `approval_patterns`, `screen_captures`, `awareness_sessions`,
`awareness_suggestions`, `workflows`, `workflow_versions`, `workflow_executions`,
`workflow_step_results`, `workflow_variables`, `goals`, `goal_progress`,
`goal_check_ins`, `sidecars`, `settings`, `documents`, `webapp_templates`,
`recent_objects`, `agent_activity`. Schema lives in one file; migrations are
inline `ALTER TABLE … try { } catch { }` blocks.

**The model is explicit:** the LLM (or a deterministic extractor in `src/vault/
extractor.ts`) produces typed entities/facts/relationships after each response, and
the next prompt can pull *typed* recall ("find all `facts` where `subject = "Alice"`
and `predicate = "works_at"`").

### 4.2 FRIDAY memory — three-tier + Mem0 + Chroma

FRIDAY's design is layered and richer in *kinds* of memory, but lacks explicit
entity/relationship typing.

| Layer | File | Stores | Backed by |
|---|---|---|---|
| `EpisodicMemory` | `core/memory/episodic.py` | Verbatim turns | `ContextStore.turns` (SQLite) — 30-day rolling window |
| `SemanticMemory` | `core/memory/semantic.py` | `{key, value, confidence}` upserts with `PRUNE_FLOOR = 0.5` | `ContextStore.memory_items` |
| `ProceduralMemory` | `core/memory/procedural.py` | `(capability_name, ctx_key) → {successes, total}` bandit-style success rates | In-memory + SQLite persistence |
| `Mem0 client` | `core/mem0_client.py` | LLM-extracted user facts (background-queued via `TurnGatedMemoryExtractor`) | Mem0 cloud or self-hosted |
| ChromaDB | `data/chroma/` | Document RAG embeddings | Chroma SQLite |
| `MemoryService` | `core/memory_service.py` | Single read/write facade unifying all the above | — |

The facade is explicit (`build_context_bundle`, `record_turn`, `learn_fact`,
`recall_semantic`, `top_capabilities`, `get_active_workflow`,
`save_workflow_state`, `clear_workflow_state`) and was added in Phase 2 of the v2
refactor specifically to stop the 12 sites that used to call
`app.context_store.*` directly (`docs/friday_architecture.md` §12).

### 4.3 Extraction pipelines

**jarvis:** `src/vault/extractor.ts` runs after each LLM response (and on goal
completion, awareness session end). LLM-based extraction emits typed entities and
facts via `createEntity` / `createFact` / `createRelationship`. Confidence is
recorded per fact.

**FRIDAY:** `core/memory_extractor.py` + `core/mem0_client.py` queue extraction
*after* the turn (`_extractor.queue_turn(user_text, assistant_text)` in
`memory_service.py:103`). Mem0 produces user-fact strings; there are no typed
entities or relationships. Confidence exists on `SemanticMemory` items
(`PRUNE_FLOOR = 0.5`) but is not propagated through the broader memory stack.

### 4.4 What FRIDAY is missing from jarvis Vault

| Concept | jarvis has | FRIDAY has | Gap |
|---|---|---|---|
| Typed entities (person/project/tool/place/concept/event) | ✅ `entities` table | ❌ stored as free text in semantic memory | LLM can't query "what tools did Alice mention" |
| Typed relationships | ✅ `relationships` with typed edges | ❌ none | No graph traversal queries |
| Commitments | ✅ `commitments` table with `when_due`, `priority`, `status`, `retry_policy` | Partial — `task_manager` plugin stores reminders, but not a unified commitments concept | LLM can't ask "what did I promise to do today" |
| Audit trail of AI decisions | ✅ `audit_trail` table | ❌ — only logs to `RotatingFileHandler` | Cannot retrospectively answer "why did FRIDAY do X" |
| Inter-agent messages | ✅ `agent_messages` table | ❌ — no formal message log | Sub-agents (`workspace_agent`, `research_agent`) are isolated |
| Goal hierarchy | ✅ `goals` + `goal_progress` + `goal_check_ins` | Partial — `task_manager` plugin reminders only | No OKR-style structure |

### 4.5 What jarvis Vault is missing from FRIDAY memory

| Concept | FRIDAY has | jarvis has | Gap |
|---|---|---|---|
| Procedural memory (capability success rates) | ✅ `ProceduralMemory` bandit-style | ❌ no equivalent | jarvis cannot prefer reliable tools over flaky ones based on history |
| Triple-tier separation (episodic/semantic/procedural) | ✅ explicit | ❌ everything in one vault | jarvis cannot prune by tier or retrieve at a specific tier |
| Document-RAG via ChromaDB | ✅ `document_intel` module + Chroma | Vault `vectors` table exists but the document-RAG flow is less developed | jarvis lacks a polished "ingest my Documents folder" pipeline |
| `MemoryService` facade | ✅ explicit single read/write surface | ❌ tools query the vault directly | jarvis schema changes ripple across many files |

---

## 5. Tool Inventory Comparison

### 5.1 Tools present in BOTH

Both projects implement these (with differences in depth):

- **Shell command execution** — jarvis `run_command` (`src/actions/tools/builtin.ts`),
  FRIDAY `subprocess` calls inside several modules
- **File operations** — jarvis `read_file`, `write_file`, `list_directory`; FRIDAY
  `skills/file_ops.py` + `modules/system_control/file_search.py`
- **Clipboard** — jarvis `get_clipboard` / `set_clipboard` (sidecar-routed);
  FRIDAY does not have a dedicated clipboard tool (gap)
- **Screen capture** — jarvis `capture_screen` (sidecar); FRIDAY
  `modules/system_control/screenshot.py` (8-fallback chain for Wayland/X11/Win)
- **System info** — jarvis `get_system_info`; FRIDAY
  `core/system_capabilities.py` + `sys_info.py`
- **Browser control** — both use Chrome DevTools Protocol; jarvis has 7 browser
  tools (`browser_navigate`, `_snapshot`, `_click`, `_type`, `_scroll`,
  `_evaluate`, `_screenshot`, `_upload_file`); FRIDAY has
  `modules/browser_automation/plugin.py`
- **Vision** — both can analyse screenshots; jarvis via cloud Vision, FRIDAY via
  local SmolVLM2 + `gemini_live_skill`
- **Voice in/out** — both have wake word + STT + TTS; jarvis uses Edge
  TTS/ElevenLabs (cloud), FRIDAY uses Whisper + Piper (local)

### 5.2 Tools UNIQUE to jarvis

These have no FRIDAY equivalent:

| Tool / system | File | Notable |
|---|---|---|
| Visual workflow builder (50+ nodes) | `src/workflows/nodes/{actions,error,logic,transform,triggers}/` | xyflow React UI |
| NL workflow builder | `src/workflows/nl-builder.ts` | "describe a workflow in English" → `WorkflowDefinition` JSON via LLM |
| Authority Engine with audit | `src/authority/engine.ts`, `audit.ts`, `learning.ts`, `emergency.ts` | 5-step decision, governed categories, soft gates, voice-approval gate |
| Continuous awareness pipeline | `src/awareness/{service,intelligence,suggestion-engine,struggle-detector,context-tracker,analytics}.ts` | 5-second screen capture, weighted struggle signals |
| Goal pursuit (OKR) | `src/goals/{service,rhythm,accountability,estimator,nl-builder}.ts` | 5-level hierarchy with escalation states |
| Multi-agent hierarchy | `src/agents/{hierarchy,delegation,task-manager,sub-agent-runner,orchestrator}.ts` | parent_id tree + delegateTask + commitments + background sub-agents |
| Sidecar fleet & sidecar routing | `src/actions/tools/sidecar-route.ts`, `sidecar-list.ts` | Every tool optionally takes a `target` param to route to a remote sidecar |
| Multi-channel comms | `src/comms/channels/{telegram,discord,signal,whatsapp}.ts` | Single dispatch through `comms/` |
| Multi-provider LLM router | `src/llm/{manager,anthropic,openai,gemini,ollama,groq,nvidia,openrouter}.ts` | Per-provider retry (3x) + 90s timeout + fallback chain |
| Content pipeline | `src/actions/tools/content.ts` + `content_items` table | youtube/blog/twitter/podcast stages |
| Approval delivery | `src/authority/approval-delivery.ts` | Routes approval cards to chat/Telegram/Discord |
| Webapp templates | `webapp_templates` table | Per-app browser navigation playbooks |
| Personality state | `src/personality/` + `personality_state` table | Persistent personality model |

### 5.3 Tools UNIQUE to FRIDAY

These have no jarvis equivalent:

| Tool / system | File | Notable |
|---|---|---|
| `hey_friday` wake word | `models/hey_friday.onnx` + `modules/voice_io/wake_porcupine.py` | Custom-trained wake word model |
| Clap detector | `modules/voice_io/clap_detector.py` + `skills/clap_control_skill.py` | Toggle assistant via two claps |
| Local on-device chat + tool LLM | Qwen3-1.7B + Qwen3-4B Q4_K_M GGUF | Full conversation works offline |
| Local on-device VLM | SmolVLM2-2.2B GGUF | Vision without cloud calls |
| Piper TTS (local) | `piper/` binary | Speech without network |
| Document RAG with Chroma + markitdown | `modules/document_intel/plugin.py` | Indexes `~/Documents`, auto/idle-only mode |
| Gemini Live skill | `skills/gemini_live_skill.py` | Real-time multimodal Gemini |
| World Monitor news | `modules/world_monitor/plugin.py` | Geopolitical news aggregator |
| Research agent | `modules/research_agent/plugin.py` | Multi-source web research with `ThreadPoolExecutor(3)` |
| Workspace agent | `modules/workspace_agent/` | Manages spreadsheets / docs |
| Focus session | `modules/focus_session/plugin.py` | Pomodoro-style focus timer |
| WhatsApp skill | `skills/whatsapp_skill.py` + `skills/whatsapp/` | Send/read WhatsApp messages |
| Email ops | `skills/email_ops.py` | SMTP send + IMAP read |
| Datetime ops | `skills/datetime_ops.py` | Natural-language date parsing |
| ProceduralMemory bandit | `core/memory/procedural.py` | Track which capabilities succeed |
| `task_manager` (1267 LoC) | `modules/task_manager/plugin.py` | Notes + reminders with NL time parsing |
| Sophisticated Wayland screenshot | `modules/system_control/screenshot.py` (515 LoC) | 8-strategy fallback for GNOME Wayland |
| World monitor + greeter + persona | Several plugins | Personalized greeting + persona swap |
| Capability descriptor schema | `core/capability_registry.py` | `connectivity`/`latency_class`/`permission_mode`/`side_effect_level`/`fallback_capability` per tool |
| Three-tier inference (regex → Qwen-tool → Qwen-chat) | `core/router.py` + `IntentEngine` | Fast-path for deterministic intents |

### 5.4 Tool-count summary

| Category | jarvis count | FRIDAY count |
|---|---|---|
| Built-in tools (handler functions) | ~30 (`builtin.ts` + `desktop.ts` + `browser/*` + `terminal/*`) | ~50+ (sum of handlers across 16 modules + 14 skills) |
| Workflow nodes | 50+ | N/A (workflows are LangGraph state machines, not node-based) |
| External integrations | Google API + 4 chat channels + 7 LLM providers | Gemini Live + WhatsApp + email + 1 LLM family (Qwen via llama-cpp) |
| Modules / plugins | Tools loaded at boot, not modular | 16 modules + 14 skills |

---

## 6. Multi-Agent & Delegation

### 6.1 jarvis

- **`AgentHierarchy`** (`src/agents/hierarchy.ts`) — maintains a tree of agents
  keyed on `parent_id`. `addAgent`, `removeAgent` (recursive), `getChildren`,
  `getParent`, `getPrimary`, `getTree`. ~113 lines.
- **`delegateTask`** (`src/agents/delegation.ts`) — verifies parent-child
  relationship + parent's `authority.can_spawn_children`, then creates a
  `commitment` in the vault, sends an `agent_messages` row with type=`task`,
  sets the child's task. Returns `{success, agent_id, commitment_id}`.
- **`reportCompletion`** — child sends a `report` message back to parent and clears
  its own task.
- **`AgentTaskManager`** (`src/agents/task-manager.ts`) — `launch()` returns a task
  ID immediately and runs `runSubAgent` in the background. Tracks `running` /
  `completed` / `failed` and supports cleanup of completed tasks older than 10
  minutes.
- **`sub-agent-runner.ts`** (309 lines) — the actual agent loop for sub-agents,
  with its own tool list and LLM context.
- **Roles** — 8 YAML files in `roles/`: `activity-observer`, `ceo-founder`,
  `chief-of-staff`, `dev-lead`, `executive-assistant`, `marketing-director`,
  `personal-assistant`, `research-specialist`, `system-admin` (plus a
  `specialists/` subdir).

### 6.2 FRIDAY

- **`core/delegation.py`** (207 lines) — has the `Delegate` concept but is much
  thinner: assigns sub-tasks to specific module agents (`research_agent`,
  `workspace_agent`) and waits for results synchronously.
- **`modules/research_agent/plugin.py`** (161 lines) — multi-source research with
  parallel fetching (`ThreadPoolExecutor(max_workers=3)`).
- **`modules/workspace_agent/`** — google workspace helpers.
- **No hierarchical agent tree.** No `parent_id` concept. No `commitments` table
  to track promises.

### 6.3 Gap analysis

FRIDAY's "agents" are static module instances that handle specific subtasks. jarvis
agents are runtime-spawned entities with role, parent, status, current task,
authority level, and an inbox. The closest FRIDAY equivalent is the
`WorkflowOrchestrator`'s state-machine workflows, which can pause and resume across
turns but don't *spawn* additional reasoning agents.

**Adoption candidate?** A lightweight agent registry could be added to FRIDAY using
the existing `core/skill.py` + `delegation.py` scaffolding. The hard part is the
commitment store — jarvis's `commitments` table is genuinely useful even without
multi-agent, and could be added to `MemoryService` independently (see §15 #2).

---

## 7. Awareness & Proactivity

### 7.1 jarvis

**Pipeline** (`src/awareness/service.ts`):
1. Sidecars push events: `screen_capture`, `context_changed`, `idle_detected`,
   `ocr_text` (OCR runs in the sidecar to avoid round-trip).
2. `ContextTracker` updates the current `awareness_session`.
3. `AwarenessIntelligence` runs cloud-Vision analysis on cooldown
   (`cloud_vision_cooldown_ms`).
4. `StruggleDetector` (`src/awareness/struggle-detector.ts`, 342 lines) maintains a
   3.5-minute rolling window of up to 30 snapshots and computes 4 weighted signals:
   - `trialAndError` (0.30) — change but no progress
   - `undoRevert` (0.25) — repeated reverts
   - `repeatedOutput` (0.25) — same compiler/terminal output
   - `lowProgress` (0.20) — content barely changes
   Composite ≥ 0.5 with a 2-minute grace + 3-minute cooldown fires a struggle event.
5. `SuggestionEngine` proposes interventions (rate-limited by
   `suggestion_rate_limit_ms`).
6. Events go to the dashboard widget; suggestions can be `delivered`,
   `dismissed`, or `acted_on` (tracked in `awareness_suggestions` table).
7. Retention pruning runs every 10 minutes, downgrading `full` captures to
   `key_moment` or `metadata_only` based on `retention_tier`.

Configuration knobs: `capture_interval_ms`, `screen_interval_ms`,
`window_interval_ms`, `min_change_threshold`, `stuck_threshold_ms`, `ocr_enabled`,
`capture_dir`.

### 7.2 FRIDAY

- **`world_monitor` module** — geopolitical news polling, not awareness.
- **`greeter` module** — personalised greeting at session start.
- **`vision` module + `vision_skill`** — on-demand "look at my screen and tell me
  what's there" requests. No continuous capture loop.
- **`focus_session`** — pomodoro timer; no awareness of what the user is doing.

### 7.3 Gap analysis

FRIDAY has no continuous-awareness loop. This is one of jarvis's largest
differentiators. Adopting it in FRIDAY would require:

1. A capture timer (could use `core/turn_runner.py` scheduling infra).
2. Use FRIDAY's existing `screenshot.py` (already battle-tested for Wayland).
3. Local OCR (Tesseract via `pytesseract`) — keeps it on-device.
4. A `StruggleDetector`-style signal computation (could port directly to Python).
5. A suggestion delivery channel — FRIDAY currently has voice + HUD; jarvis has
   chat + Telegram + Discord + notification.
6. Storage tables in `ContextStore` (analogous to `screen_captures`,
   `awareness_sessions`, `awareness_suggestions`).

See §15 #4 for the recommendation. **Concern:** continuous capture on a laptop is
expensive and the privacy implications are non-trivial — defer to an explicit
"awareness mode" toggle rather than always-on.

---

## 8. Authority & Safety

### 8.1 jarvis Authority Engine

`src/authority/engine.ts` (301 lines) implements a **5-step decision** for every
tool call:

1. **Temporary grants** — parent agent can grant a child temporary authority
   for specific categories.
2. **Per-action overrides** — explicit allow/deny rules per role.
3. **Context rules** — time-based, tool-name-based, or always-on rules with
   `effect: 'allow' | 'deny' | 'require_approval'`.
4. **Numeric level check** — agent's level vs `AUTHORITY_REQUIREMENTS[action]`.
5. **Governed category check** — if level is sufficient but the action category
   is in `governed_categories`, still require approval.

**Action categories** (`src/roles/authority.ts`): `read_data`, `write_data`,
`delete_data`, `send_message`, `send_email`, `execute_command`, `install_software`,
`make_payment`, `modify_settings`, `spawn_agent`, `terminate_agent`,
`access_browser`, `control_app`.

**Impact map** (`IMPACT_MAP`): each category maps to `read | write | external | destructive`.

**Voice-approval gating** (`gateVoiceApprovalResolution`):
- Destructive impacts (payment, delete, terminate, exec, install, modify_settings)
  **never** resolve by voice — only by dashboard click.
- Non-destructive needs STT confidence ≥ 0.85, else returns `{kind: 'clarify'}`.

**Other Authority components:**
- `audit.ts` — every decision goes to `audit_trail` table with `agent_id`,
  `tool_name`, `authority_decision`, `approval_id`, `executed`, `execution_time_ms`.
- `learning.ts` — after N consecutive approvals of the same `(action_category,
  tool_name)`, suggests adding a permanent override. Threshold default = 5.
- `approval-delivery.ts` — routes approval cards to chat, Telegram, or Discord.
- `emergency.ts` — `pause` / `resume` / `kill` / `reset` lifecycle. While `paused`,
  every tool returns `[SYSTEM PAUSED]`. `killed` requires explicit `reset()`.
- `deferred-executor.ts` — runs the original tool after approval is granted.

### 8.2 FRIDAY safety

- **`ConsentService`** (`core/kernel/consent.py`) — gates online/network capabilities.
- **`PermissionService`** — infers `side_effect_level` from tool names.
- **`PermissionTier`** — `always_ok` / `ask_first` / `ask_each_time`.
- **`online_permission_mode`** in `config.yaml` — `ask_first` by default.
- **No audit trail.** Logs are flat files (`logs/`) with `RotatingFileHandler`.
- **No approval delivery channel.** Approval is a voice/HUD prompt only.
- **No learning of approval patterns.**
- **No emergency pause/kill.** The user kills the process directly.

### 8.3 Gap analysis

| Concept | jarvis | FRIDAY | Adoption value |
|---|---|---|---|
| 5-step decision flow | ✅ | Simplified (3-state PermissionTier) | Medium — FRIDAY model is sufficient for current scope |
| Action categories | ✅ 13 | ❌ — uses `side_effect_level` heuristic | High — explicit categories improve consent UX |
| `audit_trail` SQL table | ✅ | ❌ — only file logs | **High — easy port, big debuggability win** |
| Voice approval safety gate | ✅ | ❌ — voice "yes" resolves any pending prompt | **High — prevents misheard "yes" from approving destructive actions** |
| Approval delivery channels | ✅ (chat, Telegram, Discord) | Voice + HUD only | Low (unless adding remote channels) |
| Consecutive-approval learning | ✅ | ❌ | Medium — quality-of-life improvement |
| Emergency pause/kill | ✅ | ❌ | Low — process kill is fine for single-user |

See §15 #3 for the recommendation.

---

## 9. Workflows & Automation

### 9.1 jarvis

`src/workflows/engine.ts` orchestrates execution via:
- **NodeRegistry** — pluggable nodes registered at boot, organised by category:
  - `actions/`: telegram, code-execution, send-message, run-tool, agent-task,
    gmail, shell-command, file-write, discord, calendar-action, notification,
    http-request — 12 nodes
  - `error/`: retry, error-handler, fallback — 3 nodes
  - `logic/`: loop, switch, merge, if-else, delay, race, template-render,
    variable-get, variable-set — 9 nodes
  - `transform/`: csv-parse, json-parse, map-filter, aggregate, regex-match — 5 nodes
  - `triggers/`: process, file-change, cron, manual, poll, calendar, webhook,
    screen-event, email, clipboard, git — 11 trigger nodes
- **Top-level triggers** in `src/workflows/triggers/`: `cron`, `poller`,
  `screen-condition`, `webhook`, `observer-bridge` (bridges sidecar awareness
  events to workflows), `manager` (coordinates triggers).
- **Variables** with template substitution (`template.ts`, `variables.ts`).
- **Executor** runs topological sort with optional parallel waves.
- **NLWorkflowBuilder** (`nl-builder.ts`): LLM converts NL description into a
  `WorkflowDefinition` JSON object with nodes/edges.
- **YAML import/export** (`yaml.ts`).
- **Auto-suggest** (`auto-suggest.ts`): LLM watches user behaviour and proposes
  workflows.
- **Versioning** — `workflow_versions` table; each save bumps the version.
- **Execution history** — `workflow_executions` + `workflow_step_results` tables.
- **Self-healing** — `error/retry.ts`, `error/fallback.ts`, `error/error-handler.ts`.

The dashboard renders an `@xyflow/react` graph editor where the user can drag
nodes around and connect them.

### 9.2 FRIDAY

`core/workflow_orchestrator.py` (820 lines):
- LangGraph `StateGraph` if available, else falls back to a simple state machine.
- A handful of multi-turn workflows hard-coded into the orchestrator
  (calendar event creation, reminder, file write confirmation, dictate-or-generate).
- Cancellation tokens for "cancel", "abort", "nevermind", "stop", etc. (with
  fuzzy match for "cancle", "canecl", etc.).
- Yes/no parsers for affirmative/negative answers.

There is no:
- Visual workflow editor
- NL workflow builder
- Cron/poll/webhook triggers
- Pluggable node registry
- Versioning of workflows
- Execution history table
- Self-healing retry/fallback as a node

### 9.3 Gap analysis

jarvis's workflow engine is a much bigger system than FRIDAY's. The honest read
is that **FRIDAY's `WorkflowOrchestrator` is in a different category**: it handles
multi-turn conversational state machines (calendar dialogs), not arbitrary
automation graphs.

**Adopting a jarvis-style workflow engine in FRIDAY would be a large project**
— see §14 (`COMPATIBLE_WITH_ADAPTATION`, L effort) — but adopting just the
**trigger types** (cron, file-watch, clipboard-watch, screen-event) could give
FRIDAY a proactive layer without rebuilding the whole engine. See §15 #5.

---

## 10. Goal Pursuit

### 10.1 jarvis OKR system

`src/goals/service.ts` runs 3 timers as a `Service`:
- `rhythmTimer` — every 60s, checks for morning/evening windows
- `accountabilityTimer` — every 5min, monitors for escalation
- `healthTimer` — every 15min, recalculates goal health

**Goal schema** (`goals` table in vault):
- `level`: objective / key_result / milestone / task / daily_action
- `parent_id`: hierarchical parent (FK to `goals.id`)
- `score`: 0.0–1.0
- `status`: draft / active / paused / completed / failed / killed
- `health`: on_track / at_risk / behind / critical
- `time_horizon`: life / yearly / quarterly / monthly / weekly / daily
- `escalation_stage`: none / pressure / root_cause / suggest_kill
- `authority_level`: required to operate on this goal
- `dependencies` JSON, `tags` JSON
- `estimated_hours`, `actual_hours`

**Auxiliary tables:**
- `goal_progress` — every score change (with `score_before`/`score_after`)
- `goal_check_ins` — morning_plan + evening_review (with `goals_reviewed`,
  `actions_planned`, `actions_completed`)

**Awareness-bridge** (`src/goals/awareness-bridge.ts`) — auto-advances goal
progress when the awareness pipeline detects relevant activity.

**Drill-sergeant escalation** (`src/goals/accountability.ts`) — pressure messages
when a goal is behind, then root-cause inquiry, then suggest_kill.

**NL builder** (`src/goals/nl-builder.ts`) — "I want to ship the auth refactor by
EOQ" → structured goal tree.

### 10.2 FRIDAY

`modules/task_manager/plugin.py` (1267 lines):
- Notes table + reminders table in `data/friday.db`.
- Reminder triggers via `reminder_workflow` (a `WorkflowOrchestrator` workflow).
- NL time parsing (24h/12h/spoken/relative/ISO).
- No goal hierarchy.
- No `score` / `health` / `escalation`.
- No daily rhythm.

### 10.3 Gap analysis

jarvis's goal system is genuinely interesting and not present in FRIDAY. The
tables and schema would port cleanly (SQLite on both sides). The hard parts:
- The morning/evening rhythm needs a place to live — could go in
  `core/task_runner.py` (already runs daemon threads).
- The drill-sergeant escalation needs a voice/HUD delivery path — could go through
  the existing `SpeechCoordinator`.
- The awareness bridge presupposes a continuous awareness loop, which FRIDAY
  doesn't have. So the awareness bridge would either need to be deferred or built
  alongside §15 #4.

See §15 #7.

---

## 11. Cross-OS Strategy — Tool Implementation Patterns

> **This is the section most directly responding to the user's request.**
> The user wants a "great source for creating tools for different OSes" from jarvis.

### 11.1 jarvis pattern: Go sidecar with build constraints

The key insight from reading jarvis source: **the TypeScript daemon does NOT
handle cross-platform anything**. `src/actions/app-control/windows.ts` and
`macos.ts` are both stub classes that throw `'Not implemented. Use sidecar
desktop tools with a target parameter.'`. The Linux `.ts` impl works directly
when the daemon runs on Linux, but the strategic answer for all three OSes is
the **Go sidecar**.

The sidecar pattern has 5 parts:

**Part 1 — Capability enum (`sidecar/types.go`):**

```go
const (
    CapTerminal   SidecarCapability = "terminal"
    CapFilesystem SidecarCapability = "filesystem"
    CapDesktop    SidecarCapability = "desktop"
    CapBrowser    SidecarCapability = "browser"
    CapClipboard  SidecarCapability = "clipboard"
    CapScreenshot SidecarCapability = "screenshot"
    CapSystemInfo SidecarCapability = "system_info"
    CapAwareness  SidecarCapability = "awareness"
    CapOCR        SidecarCapability = "ocr"
)
```

These are declared *once*, in a platform-agnostic file.

**Part 2 — Platform-specific implementations via Go build tags:**

`sidecar/platform_linux.go` (`//go:build linux`) uses `xclip`, `scrot`, `xdotool`,
`ps`, `which`.

`sidecar/platform_windows.go` (`//go:build windows`) uses `powershell`, the
PowerShell `Get-Clipboard` / `Set-Clipboard` cmdlets, `System.Windows.Forms` for
screenshot, and an inline C# `Add-Type` block calling `user32.dll`'s
`GetForegroundWindow` / `GetWindowThreadProcessId` / `GetWindowText` for the
active window. Example:

```go
//go:build windows
func platformClipboardRead() (string, error) {
    return runCmd("powershell", []string{"-command", "Get-Clipboard"}, "")
}
func platformGetActiveWindow() (appName string, windowTitle string) {
    out, _ := exec.CommandContext(ctx, "powershell.exe", "-command",
        `Add-Type @'
using System; using System.Runtime.InteropServices; ...
public class FG { [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); ... }
'@
[FG]::Get()`).Output()
    ...
}
```

`sidecar/platform_darwin.go` (`//go:build darwin`) uses `pbpaste`, `pbcopy`,
`screencapture`, and `osascript`:

```go
//go:build darwin
func platformClipboardRead() (string, error) {
    return runCmd("pbpaste", nil, "")
}
func platformGetActiveWindow() (appName string, windowTitle string) {
    out, _ := exec.Command("osascript", "-e",
        `tell application "System Events" to get name of first process whose frontmost is true`).Output()
    ...
}
```

**Each file declares the same function signatures.** The Go compiler picks the
right file based on `GOOS`. No conditional imports, no `if/else` chains — the
function `platformClipboardRead()` only exists in the file matching the build OS.

**Part 3 — Preflight validation per platform:**

`sidecar/preflight.go` (platform-agnostic) iterates the configured capabilities
and asks `checkClipboard()`, `checkScreenshot()`, etc. Each `check*()` is
*also* build-tag'd per OS:

`sidecar/preflight_linux.go`:
```go
func checkClipboard() string {
    if _, err := exec.LookPath("xclip"); err == nil { return "" }
    if _, err := exec.LookPath("xsel"); err == nil { return "" }
    return "xclip or xsel not found"
}
func checkScreenshot() string {
    for _, tool := range []string{"scrot", "import", "gnome-screenshot"} {
        if _, err := exec.LookPath(tool); err == nil { return "" }
    }
    return "no screenshot tool found"
}
func checkDesktop() string {
    if os.Getenv("DISPLAY") == "" && os.Getenv("WAYLAND_DISPLAY") == "" {
        return "no display server"
    }
    if _, err := exec.LookPath("xdotool"); err != nil {
        return "xdotool not found"
    }
    return ""
}
```

`sidecar/preflight_windows.go`:
```go
func checkClipboard() string {
    if _, err := exec.LookPath("powershell"); err != nil { return "powershell not found" }
    return ""
}
```

**The result:** every sidecar reports `available` and `unavailable` capabilities to
the brain on connect (`SidecarRegistration` in `types.go`). The dashboard shows
warnings for unavailable ones. The brain never tries to route a tool that the
target sidecar cannot execute.

**Part 4 — Capability routing via `target` parameter:**

Every brain-side tool (`src/actions/tools/builtin.ts:` `run_command`,
`get_clipboard`, etc.) takes an optional `target` parameter:

```typescript
target: {
  type: 'string',
  description: 'Sidecar name or ID to run on a remote machine (omit for local execution)',
  required: false,
}
```

`sidecar-route.ts` dispatches the RPC to the right sidecar; `sidecar-list.ts`
exposes `list_sidecars` to the LLM so it can choose.

**Part 5 — JWT-auth WebSocket protocol:**

`sidecar/client.go` establishes the WS connection; `sidecar/main.go` accepts a
`--token <jwt>` to enrol and persists it. The brain stores enrolled sidecars in
the `sidecars` vault table.

### 11.2 FRIDAY current pattern: inline platform branching

FRIDAY uses `platform.system()` or `os.name` branches **inside the same Python
module**. A grep for `platform.system|sys.platform|os.name` across `modules/` and
`skills/` returns ~30 hits across these files:

| File | What it branches on |
|---|---|
| `modules/system_control/file_search.py` | Linux/Windows/Darwin paths |
| `modules/system_control/screenshot.py` | Wayland vs X11 vs Windows (8-fallback chain) |
| `modules/system_control/media_control.py` | OS-specific volume control |
| `modules/voice_io/tts.py` | piper.exe vs piper |
| `modules/voice_io/audio_devices.py` | Windows-specific device enum |
| `modules/voice_io/stt.py` | blocksize tuning for Windows |
| `modules/voice_io/wake_porcupine.py` | Porcupine binary paths per OS |
| `modules/voice_io/clap_detector.py` | Windows-specific path handling |
| `modules/voice_io/register_autostart.py` | Windows Registry vs Linux desktop file |
| `modules/vision/screenshot.py` | Windows-specific path |
| `modules/news_feed/service.py` | Locale per OS |

`CLAUDE.md` "Platform Notes" enumerates the recurring gotchas:
- `start_new_session=True` (Linux/macOS) vs `creationflags=DETACHED_PROCESS` (Windows)
- venv python paths
- `strftime("%-I")` is Linux-only — use `.lstrip("0")` workaround on Windows
- always pass `encoding="utf-8", errors="replace"` to subprocess

This works, but it scatters platform logic across many files. There's no
single place to audit "what does FRIDAY do on Windows" or "what's missing on
macOS". Worse, the LLM router doesn't *know* which capabilities are
unavailable on the current host — there's no preflight stage filtering the
capability registry.

### 11.3 Comparison — what sidecar buys you vs cost

| Property | jarvis (sidecar) | FRIDAY (inline) |
|---|---|---|
| Multi-machine support | ✅ — sidecars on any host | ❌ — single process |
| True platform isolation | ✅ — Go build tags compile only the right file | ⚠️ — runtime branches in one file |
| Preflight gating of LLM tool choices | ✅ — unavailable capabilities never registered | ❌ — LLM can call a tool that will fail |
| Native syscalls without binding pain | ✅ — Go's `os/exec` + raw `Add-Type` for Win32 | ⚠️ — needs `pywin32` / `gi` / etc. per binding |
| Same-machine deployment cost | High — extra Go binary, JWT enrolment | Zero — already running |
| Code complexity | High — two languages, IPC protocol, auth | Low — one process |
| Crash isolation | ✅ — sidecar crash doesn't kill brain | ❌ — module crash can take down assistant |
| Debugging | Harder — distributed traces | Easier — one process, one logger |

**The sidecar model wins when:** you want multi-machine, you want native syscalls
without binding hell, or you want crash isolation.

**The inline model wins when:** you only target one machine, you already have
Python on every host, and you want simple debugging.

**FRIDAY's stated scope is single-machine Linux/Windows** (`CLAUDE.md`). The
sidecar architecture is **overkill**. But the *patterns within the sidecar* —
build-tag-style platform splitting, and preflight validation — can absolutely be
adopted in Python.

### 11.4 Recommended pattern for FRIDAY — Python-native adaptation

The goal is to capture the *good parts* of jarvis's pattern (clear platform split,
preflight validation, registry filtering) without paying the cost of a separate
process.

**Recommended directory layout:**

```
modules/system_control/
├── plugin.py              # registers capabilities, picks the right adapter
├── adapters/
│   ├── __init__.py        # platform.system() dispatcher
│   ├── _interface.py      # ABC: PlatformAdapter with required methods
│   ├── linux.py           # uses xclip/scrot/xdotool, Wayland portals, etc.
│   ├── windows.py         # uses pywin32 / PowerShell / Get-Clipboard
│   └── macos.py           # uses pbcopy/pbpaste/osascript/screencapture
├── preflight.py           # per-platform availability checks
└── ...
```

**`_interface.py`** declares the API once:

```python
from abc import ABC, abstractmethod

class PlatformAdapter(ABC):
    @abstractmethod
    def clipboard_read(self) -> str: ...
    @abstractmethod
    def clipboard_write(self, text: str) -> None: ...
    @abstractmethod
    def capture_screen(self, out_path: str) -> None: ...
    @abstractmethod
    def get_active_window(self) -> tuple[str, str]: ...  # (app_name, window_title)
    @abstractmethod
    def default_shell(self) -> str: ...
```

**`adapters/__init__.py`** picks the adapter at import time (mirrors jarvis's
`getAppController()` in `interface.ts`):

```python
import platform

def get_adapter() -> "PlatformAdapter":
    system = platform.system()
    if system == "Linux":
        from .linux import LinuxAdapter
        return LinuxAdapter()
    if system == "Windows":
        from .windows import WindowsAdapter
        return WindowsAdapter()
    if system == "Darwin":
        from .macos import MacOSAdapter
        return MacOSAdapter()
    raise RuntimeError(f"Unsupported platform: {system}")
```

**`preflight.py`** mirrors `sidecar/preflight.go`:

```python
import shutil, os
from dataclasses import dataclass

@dataclass
class CapabilityAvailability:
    name: str
    available: bool
    reason: str = ""

def check_clipboard() -> CapabilityAvailability:
    if platform.system() == "Linux":
        if shutil.which("xclip") or shutil.which("xsel"):
            return CapabilityAvailability("clipboard", True)
        return CapabilityAvailability("clipboard", False, "xclip or xsel not found")
    if platform.system() == "Windows":
        if shutil.which("powershell") or shutil.which("pwsh"):
            return CapabilityAvailability("clipboard", True)
        return CapabilityAvailability("clipboard", False, "powershell not found")
    if platform.system() == "Darwin":
        if shutil.which("pbpaste"):
            return CapabilityAvailability("clipboard", True)
        return CapabilityAvailability("clipboard", False, "pbpaste not found")
    return CapabilityAvailability("clipboard", False, "unsupported OS")
```

**Plugin `on_load`** runs preflight before registering tools:

```python
def on_load(self):
    self.adapter = get_adapter()
    self.availability = run_preflight_checks()

    if self.availability["clipboard"].available:
        self.app.router.register_tool(
            {"name": "get_clipboard", "description": "Read clipboard", "parameters": {}},
            lambda t, a: self.adapter.clipboard_read(),
            capability_meta={"side_effect_level": "read"},
        )
    else:
        logger.warning(
            "clipboard tool not registered: %s",
            self.availability["clipboard"].reason,
        )
```

**The result:** the router never sees a tool that won't work on this host. The
HUD can show a "missing tools" panel by querying `self.availability`. The LLM
tool selector cannot hallucinate using a tool that doesn't exist on this OS.

### 11.5 Concrete tool-implementation template (lifted from jarvis sidecar)

For each cross-OS tool FRIDAY wants to add, the template is:

1. **Declare the interface** in `adapters/_interface.py` (one abstractmethod per
   operation).
2. **Implement per platform** in `adapters/linux.py`, `windows.py`, `macos.py`. Each
   file imports only its OS-specific dependencies inside the file (so importing
   `linux.py` on Windows doesn't crash trying to import `pywin32`).
3. **Add a preflight check** in `preflight.py` that uses `shutil.which()`, env-var
   checks, and `try-import` patterns to detect availability.
4. **Plugin `on_load` runs preflight first**, then conditionally registers the
   capability with `capability_meta` reflecting the side-effect level and
   connectivity.
5. **Document the install instructions** in the adapter's `__doc__` so the
   preflight failure message can tell the user what to install (jarvis does this
   in `LinuxAppController.ensureTool` — see `src/actions/app-control/linux.ts:14-22`):

```python
class LinuxAdapter(PlatformAdapter):
    """xclip-based clipboard, scrot/grim/portal screenshot, xdotool window.

    Install:
      Ubuntu/Debian: sudo apt install xclip xdotool scrot
      Fedora:        sudo dnf install xclip xdotool scrot
      Arch:          sudo pacman -S xclip xdotool scrot
    """
```

### 11.6 If FRIDAY ever wants multi-machine

If FRIDAY ever wants to control multiple devices (e.g. a desktop + a server), the
jarvis Go-sidecar pattern is a proven blueprint:

- **Brain stays Python** on the user's primary machine.
- Write a **Go (or Rust) sidecar** that exposes the same `PlatformAdapter` surface
  over a WebSocket or gRPC channel.
- Add a `target` parameter to each Python tool capability — exact mirror of
  jarvis's pattern in §11.1 part 4.
- Auth via short-lived JWT (jarvis uses RS256-signed tokens from the brain's JWKS).

This is **not a recommendation to do now** — see §14 `INCOMPATIBLE` for current
single-machine scope. It's a "you have a reference implementation if you ever
want it" note.

---

## 12. What jarvis Does Better than FRIDAY

Ranked by user-visible value:

1. **Continuous desktop awareness** — 5-second screen capture, hybrid Vision+OCR,
   struggle detection, proactive suggestions. FRIDAY has none of this.
2. **Cross-OS architecture with preflight** — `//go:build` tag-split implementations
   + capability advertising means the brain never tries to do something the host
   can't. FRIDAY scatters `platform.system()` branches inline.
3. **OKR goal-pursuit system** — hierarchical goals with health, escalation, daily
   rhythm, awareness-bridge. FRIDAY has reminders but not goals.
4. **Visual workflow builder** — drag-and-drop graph editor with 50+ node types,
   NL builder, YAML export, versioning, execution history.
5. **Multi-agent hierarchy** — runtime-spawned agents with parent_id, delegate_task,
   commitments table, sub-agent background runner.
6. **Authority Engine** — 5-step decision flow, audit_trail SQL, voice-approval
   safety gate, consecutive-approval learning, emergency pause/kill.
7. **Multi-LLM router with provider fallback** — Anthropic / OpenAI / Gemini /
   Ollama / Groq / NVIDIA / OpenRouter with 3-attempt retry + 90s timeout +
   automatic failover.
8. **Typed knowledge graph (Vault)** — entities/facts/relationships/commitments
   with confidence scores and typed predicates. FRIDAY stores facts as free text.
9. **Multi-channel proactive delivery** — Telegram, Discord, Signal, WhatsApp,
   desktop notifications. FRIDAY's only output is voice + HUD.
10. **Comprehensive triggers** — cron, webhook, file-watch, screen-event, poller,
    clipboard-watch, calendar, email, git — for proactive workflows.
11. **Web dashboard** — React 19 UI for managing everything visually; the Tkinter
    HUD in FRIDAY is functional but limited.
12. **Multi-machine fleet** — one brain, many sidecars on any host.
13. **Content pipeline** — `content_items` table with youtube/blog/twitter/podcast
    stages for content creators.

## 13. What FRIDAY Does Better than jarvis

Ranked by strategic moat:

1. **Truly local-first** — Qwen3 chat/tool LLM + SmolVLM2 vision + Whisper STT +
   Piper TTS + openwakeword. Works offline. jarvis cannot.
2. **Wake-word voice loop** — `hey_friday` ONNX model + clap detector + dictation
   mode. jarvis has voice but it's web-app-style PTT.
3. **Three-tier memory model** — episodic / semantic / procedural separation.
   jarvis has one Vault for everything.
4. **ProceduralMemory bandit** — capability success rates inform future routing.
   jarvis cannot prefer reliable tools over flaky ones based on past outcomes.
5. **Sophisticated screenshot fallback** — `modules/system_control/screenshot.py`
   has an 8-strategy chain for GNOME Wayland (Mutter ScreenCast / PipeWire,
   gdbus, xdg-portal, grim, spectacle, X11 tools, pyautogui). jarvis sidecar uses
   only the first available of scrot/import/gnome-screenshot.
6. **Capability descriptor schema** — `connectivity`, `latency_class`,
   `permission_mode`, `side_effect_level`, `streaming`, `fallback_capability`
   per tool. jarvis `ToolDefinition` has only name/description/category/params.
7. **`ExtensionContext` isolation by design** — extensions cannot reach the
   kernel. jarvis tools just import what they need.
8. **TurnOrchestrator v2 design** — single control flow, `TaskGraphExecutor`
   topological parallel waves, `TurnTrace` structured spans. jarvis uses a
   sequential agent loop up to 200 iterations.
9. **`MemoryService` facade** — single read/write surface; storage layer
   evolvable without rippling changes. jarvis tools query vault directly.
10. **Document RAG with markitdown + Chroma** — `modules/document_intel` with
    auto-indexing in idle, configurable chunk size, max tokens. jarvis has a
    `vectors` table but no polished ingestion pipeline.
11. **World Monitor news plugin** — geopolitical news aggregator (FRIDAY-unique
    domain).
12. **Three-tier inference routing** — regex/intent fast path → Qwen tool model →
    Qwen chat model. jarvis goes straight to LLM every time.
13. **Locally-hosted vision** — SmolVLM2-2.2B local GGUF. jarvis depends on
    Anthropic/Gemini Vision.

---

## 14. Compatibility Validation Matrix

For each jarvis advantage from §12, classified against FRIDAY's current
architecture. Effort: **S** ≤ 1 week of focused work, **M** = 1–3 weeks, **L** ≥ 1 month.

| # | jarvis feature | Tag | Effort | Target FRIDAY file(s) | Integration touchpoint | Notes |
|---|---|---|---|---|---|---|
| 12.1 | Continuous desktop awareness | COMPATIBLE_WITH_ADAPTATION | L | new `modules/awareness/` + reuse `modules/system_control/screenshot.py` | `MemoryService` (new tables), `EventBus` (new event types), `TurnOrchestrator` (consume `awareness_event`) | Privacy + CPU concerns; gate behind explicit `awareness_mode_enabled` config |
| 12.2 | Cross-OS adapter pattern with preflight | **COMPATIBLE** | M | new `modules/<each>/adapters/{linux,windows,macos}.py` + `preflight.py` | `CapabilityRegistry.register_tool` is already metadata-aware; preflight just filters before registration | **Highest-leverage easy win** (see §15 #1) |
| 12.3 | OKR goal-pursuit | COMPATIBLE_WITH_ADAPTATION | M | new `modules/goals/` + extend `MemoryService` with goal tables | `WorkflowOrchestrator` (daily rhythm as workflow), `task_runner.py` (timers), HUD (rendering) | Schema ports cleanly; the awareness-bridge sub-feature depends on §12.1 |
| 12.4 | Visual + NL workflow builder | INCOMPATIBLE (visual) / COMPATIBLE_WITH_ADAPTATION (NL) | L | n/a for visual (no web dashboard); for NL → extend `WorkflowOrchestrator` with an LLM-driven `nl_builder.py` | `PlannerEngine` already produces DAGs; could be repurposed | Visual editor needs a web UI FRIDAY doesn't have; NL builder is doable |
| 12.5 | Multi-agent hierarchy | COMPATIBLE_WITH_ADAPTATION | M | new `core/agent_hierarchy.py` + extend `core/delegation.py` | `MemoryService` (new `commitments`, `agent_messages` tables), `TaskGraphExecutor` (run sub-agents as nodes) | Closest port; FRIDAY already has the `Delegate` concept |
| 12.6 | Authority audit_trail + voice-approval gate | **COMPATIBLE** | S | new `core/audit_trail.py` + extend `core/kernel/consent.py` | `CapabilityExecutor.execute` (log every call), `SpeechCoordinator` (call `gate_voice_approval` before resolving) | Quick win; pure additive |
| 12.7 | Multi-LLM router with provider fallback | ALREADY_PRESENT (degenerate) | S | `core/model_manager.py` already supports model swap | Currently FRIDAY only configures llama-cpp; could add `OpenAIBackend`, `AnthropicBackend` classes | Most users want local; only worth it if FRIDAY wants cloud-fallback story |
| 12.8 | Typed knowledge graph (entities/facts/relationships/commitments) | COMPATIBLE_WITH_ADAPTATION | M | extend `core/memory_service.py` + new `core/memory/graph.py` + new SQLite tables | `MemoryExtractor` (emit typed extractions), `build_context_bundle` (typed recall) | Big quality lift for personalisation |
| 12.9 | Multi-channel proactive delivery | COMPATIBLE | M per channel | new `modules/comms/{telegram,discord,whatsapp}.py` (whatsapp_skill already partial) | `EventBus` subscriber pattern; needs token storage in `ConfigService` | Each channel is independent; can ship one at a time |
| 12.10 | Comprehensive triggers (cron/file-watch/screen/clipboard/git/email) | COMPATIBLE | M | new `modules/triggers/` with one file per trigger type | `EventBus` (publish `trigger_fired`), `WorkflowOrchestrator` (subscribe), `TurnOrchestrator` (consume) | Each trigger type is small; cron/file-watch are easiest |
| 12.11 | Web dashboard | INCOMPATIBLE (against scope) | L | n/a | n/a | FRIDAY is GUI-via-Tkinter by design; building a web dashboard is a different product |
| 12.12 | Multi-machine fleet | INCOMPATIBLE (against scope) | XL | new sidecar process | n/a | Single-machine is a stated scope; defer |
| 12.13 | Content pipeline | INCOMPATIBLE (against scope) | M | new `modules/content_pipeline/` | n/a | Targets content creators; FRIDAY's user persona is different |

**Summary by tag:**
- **ALREADY_PRESENT (or partially):** 1 (LLM router degenerate case)
- **COMPATIBLE (drop-in design fit):** 3 (cross-OS adapter, audit/voice-gate, comms channels)
- **COMPATIBLE_WITH_ADAPTATION:** 6 (awareness, goals, NL workflow builder, agents, knowledge graph, triggers)
- **INCOMPATIBLE (conflicts with FRIDAY's local-first / single-process / single-machine scope):** 3 (visual workflow editor, web dashboard, fleet)

---

## 15. Prioritized Adoption Roadmap — Top 10 Ports

Ordered by `(user-visible value × strategic value) / effort`. Each entry has a
"skip if" disqualifier so this stays advisory, not prescriptive.

### #0 — First-run user onboarding & persistent user profile · ✅ shipped 2026-05-16

- **From:** N/A — this is FRIDAY-original, prompted by the observation that FRIDAY
  could not answer "what is my name?" despite months of memory infrastructure
  work. jarvis has nothing analogous in this exact form; the closest analogue is
  jarvis's `vault/entities` table for a `person` entity (Report §4.1).
- **Why it matters:** Every downstream memory feature in this roadmap (#2 typed
  commitments, #9 typed knowledge graph, Mem0 / Vault-style extraction) is
  useless if FRIDAY has no name to call the user. Onboarding is the *source* of
  the facts those structures store. This had to come before the other memory
  ports.
- **Implementation summary:**
  - New `modules/onboarding/` (extension + `OnboardingWorkflow`) — 5-question
    state machine (name → role → location → preferences → comm_style) registered
    in `core/workflow_orchestrator.py`.
  - Profile stored in existing `ContextStore.facts` table under
    `namespace="user_profile"` — no schema change.
  - `modules/greeter/extension.py` detects empty profile on startup and seeds
    the workflow, then on subsequent runs substitutes the stored name for `sir`
    in every greeting/phrase.
  - `core/assistant_context.py` injects a `The user's profile:` block into the
    chat system prompt on every turn, **independent of Mem0** — fixing the
    "FRIDAY doesn't know my name" regression.
  - New `update_user_profile` capability lets the user amend fields mid-session
    ("call me X", "I live in Y").
- **Status:** Implemented; 15 new tests pass (`tests/test_onboarding_workflow.py`,
  `tests/test_assistant_context_profile_injection.py`); full suite 611 passed.
  Manual test plan: `docs/testing_guide.md` §23, regression guards T-23.4 / T-23.8.

### #1 — Cross-OS adapter pattern with preflight

- **From:** `sidecar/platform_{linux,windows,darwin}.go` + `sidecar/preflight.go`
- **Why it matters:** FRIDAY's stated scope is cross-platform Linux + Windows.
  Current `platform.system()` branches are scattered across 11 files. Adopting the
  adapter+preflight pattern (in-process — *not* the sidecar) gives FRIDAY:
  - A single audit point for "what works on Windows"
  - LLM never picks a tool that won't run on this host
  - Clean install-instruction messages when a tool is missing
- **Compatibility:** COMPATIBLE — pure Python, no new processes, no architectural
  conflict.
- **Effort:** M (1–3 weeks). Each module can migrate independently.
- **Target FRIDAY files:** Start with `modules/system_control/` (the worst
  offender). Create `adapters/{linux,windows,macos}.py` + `preflight.py`. Then
  `voice_io/` (already has 5 platform branches). Then `vision/`.
- **Integration touchpoint:** `CapabilityRegistry.register_tool` — wrap calls in
  `if availability['cap'].available:`.
- **Risks:** Adapter pattern can over-engineer if a tool only needs a 3-line
  branch. Apply only to capabilities with non-trivial OS divergence.
- **Skip if:** FRIDAY decides to drop Windows support, in which case all
  branching can be deleted instead of refactored.

### #2 — Vault-style commitments table

- **From:** jarvis `commitments` table (`src/vault/schema.ts:139-170`) and
  `src/vault/commitments.ts`
- **Why it matters:** FRIDAY's only "track what was promised" mechanism is
  reminders in `task_manager`. A first-class commitments concept lets the LLM
  query "what did I promise the user to do" and lets workflows escalate when
  promises slip.
- **Compatibility:** COMPATIBLE_WITH_ADAPTATION — add table + facade methods.
- **Effort:** S (≤ 1 week).
- **Target FRIDAY files:** new `core/memory/commitments.py`,
  `core/memory_service.py` (add `record_commitment` / `complete_commitment` /
  `list_pending_commitments`), `data/friday.db` schema migration.
- **Integration touchpoint:** `MemoryService` (public facade); `task_manager`
  plugin (reuse for reminders).
- **Risks:** Need to decide whether the LLM extracts commitments automatically or
  the user/code creates them explicitly. Start explicit, add extraction later.
- **Skip if:** `task_manager` reminders are deemed sufficient and the project
  doesn't want a second SQL store.

### #3 — Authority audit_trail + voice-approval safety gate

- **From:** `src/authority/audit.ts` (table at `src/vault/schema.ts:367-389`) +
  `gateVoiceApprovalResolution` in `src/roles/authority.ts`
- **Why it matters:** Two bugs FRIDAY currently has by design:
  - No way to ask "why did FRIDAY do X yesterday" — only flat log files.
  - A misheard "yes" can approve a pending online tool. There's no impact-tier
    safety floor.
- **Compatibility:** COMPATIBLE — both are pure additions.
- **Effort:** S (≤ 1 week). Two small modules.
- **Target FRIDAY files:**
  - new `core/audit_trail.py` (table + insert + query)
  - extend `core/kernel/consent.py` with an `ImpactTier` enum and a
    `gate_voice_approval(category, stt_confidence)` function
  - call audit insert from `CapabilityExecutor.execute`
  - call voice-gate from `SpeechCoordinator` when resolving a pending approval
- **Integration touchpoint:** `CapabilityExecutor`, `SpeechCoordinator`.
- **Risks:** Need to classify existing tools into impact tiers (`read`/`write`/
  `external`/`destructive`). The `side_effect_level` field on `CapabilityDescriptor`
  is the natural home.
- **Skip if:** Approvals are rare and the user is fine without forensics.

### #4 — Continuous awareness loop (opt-in)

- **From:** `src/awareness/{service,struggle-detector,suggestion-engine}.ts`
- **Why it matters:** Biggest user-visible differentiator jarvis has. Genuine
  proactive assistance ("you've been stuck in this stack trace for 3 minutes, want
  me to search the error?") is not possible without it.
- **Compatibility:** COMPATIBLE_WITH_ADAPTATION — needs significant porting but
  reuses FRIDAY's existing `screenshot.py`. Privacy makes opt-in mandatory.
- **Effort:** L (≥ 1 month).
- **Target FRIDAY files:**
  - new `modules/awareness/{plugin,service,struggle_detector,suggestion_engine}.py`
  - reuse `modules/system_control/screenshot.py`
  - add `pytesseract` for local OCR (or Whisper.cpp's `ggml-ocr` if available)
  - new `MemoryService` tables for captures + sessions + suggestions
  - HUD widget for delivering suggestions
- **Integration touchpoint:** `TurnOrchestrator` (consume `awareness.struggle`
  events), `EventBus`, `SpeechCoordinator` (optional voice nudges).
- **Risks:**
  - CPU cost on a laptop — capture rate must be configurable, default disabled.
  - Privacy — anything captured stays on disk; needs clear retention policy and a
    big "awareness is recording" indicator.
  - Misfires — jarvis's grace + cooldown logic must be ported faithfully or
    you'll get notification spam.
- **Skip if:** Battery / privacy concerns outweigh the value, or you're not
  ready to build a notification surface beyond voice.

### #5 — Trigger types (cron, file-watch, clipboard-watch)

- **From:** `src/workflows/triggers/{cron,observer-bridge,poller,screen-condition,webhook}.ts`
  and `src/workflows/nodes/triggers/{cron,file-change,clipboard,calendar}.ts`
- **Why it matters:** FRIDAY currently does nothing proactively (other than
  `world_monitor` polling and `task_manager` reminders). Adding 3–4 generic
  triggers gives the user "when X happens, run capability Y" — without building
  the full visual workflow engine.
- **Compatibility:** COMPATIBLE — Python has `watchfiles`, `apscheduler`,
  `pyperclip` for these.
- **Effort:** M (1–3 weeks for 3 trigger types).
- **Target FRIDAY files:** new `modules/triggers/{cron,file_watch,clipboard,
  process,webhook}.py`. Each publishes events to `EventBus`.
- **Integration touchpoint:** `EventBus` → `WorkflowOrchestrator` (subscribes) or
  `TurnOrchestrator` (consumes as a synthetic turn).
- **Risks:** Webhook trigger requires opening a port — security review needed.
- **Skip if:** FRIDAY is intended to be purely reactive (voice-only).

### #6 — Multi-agent hierarchy (lightweight version)

- **From:** `src/agents/{hierarchy,delegation,task-manager,sub-agent-runner}.ts`
- **Why it matters:** Long research / multi-step tasks block the main turn for
  seconds-to-minutes. A background sub-agent runner that returns a `task_id`
  immediately lets FRIDAY say "I'll work on that, ping you when done" and resume.
- **Compatibility:** COMPATIBLE_WITH_ADAPTATION — FRIDAY's
  `ThreadPoolExecutor`-based `research_agent` is a half-implementation.
- **Effort:** M (1–3 weeks).
- **Target FRIDAY files:** new `core/agent_hierarchy.py`, extend
  `core/delegation.py`, refactor `modules/research_agent/plugin.py` to use the
  hierarchy.
- **Integration touchpoint:** `MemoryService` (new `agent_messages` table for
  inter-agent comms + `commitments` from §15 #2), `TaskGraphExecutor` can run
  sub-agent tasks as nodes.
- **Risks:** Threads + locks must be carefully scoped to avoid the inference-lock
  contention bug already documented in `docs/friday_architecture.md` §1.2.
- **Skip if:** FRIDAY is happy to block the user during long tasks.

### #7 — OKR-style goal hierarchy

- **From:** `src/goals/{service,rhythm,accountability}.ts` + `goals` table
- **Why it matters:** `task_manager` reminders are time-driven, not progress-driven.
  A goal hierarchy with health and rhythm gives FRIDAY a coaching role.
- **Compatibility:** COMPATIBLE_WITH_ADAPTATION — schema ports cleanly; rhythm
  needs a timer source.
- **Effort:** M (1–3 weeks for MVP).
- **Target FRIDAY files:** new `modules/goals/plugin.py`,
  `core/memory_service.py` (goal CRUD methods), new SQLite tables.
- **Integration touchpoint:** `task_runner.py` for rhythm timers, HUD/voice for
  morning/evening check-ins.
- **Risks:** Without the awareness-bridge (§15 #4), auto-advance is impossible;
  user has to score manually. Decide whether that's enough for MVP.
- **Skip if:** Reminders are sufficient and you don't want to introduce a goal
  hierarchy UX.

### #8 — Multi-LLM provider fallback

- **From:** `src/llm/{manager,anthropic,openai,gemini,ollama,groq}.ts`
- **Why it matters:** Local LLMs can fail (OOM, model file corrupt, llama-cpp
  bug). A fallback to a cloud LLM keeps the assistant responsive.
- **Compatibility:** COMPATIBLE — but conflicts with FRIDAY's *local-first*
  positioning. Worth doing only as an explicit "cloud_fallback" mode.
- **Effort:** S (≤ 1 week) for the abstract; M to ship + test all providers.
- **Target FRIDAY files:** `core/model_manager.py` (already has model abstraction),
  new `core/llm_providers/{anthropic,openai,gemini}.py`.
- **Integration touchpoint:** `PlannerEngine` and `ChatModel` call sites.
- **Risks:** Goes against the project's local-first stance — must be opt-in and
  the cloud call must respect `ConsentService.online_permission_mode`.
- **Skip if:** Local LLM reliability is acceptable in practice.

### #9 — Typed knowledge-graph extension to MemoryService

- **From:** `src/vault/{schema,entities,facts,relationships,extractor}.ts`
- **Why it matters:** FRIDAY's semantic memory is free-text `key: value`. Typed
  entities + relationships let the LLM (and `build_context_bundle`) do real graph
  queries — "who is Alice, what does she work on, which tools are in her stack".
- **Compatibility:** COMPATIBLE_WITH_ADAPTATION — additive to `MemoryService`.
- **Effort:** M (1–3 weeks).
- **Target FRIDAY files:** new `core/memory/graph.py`, extend
  `core/memory_service.py`, extend `core/memory_extractor.py` to emit typed
  extractions, new tables `entities`, `facts`, `relationships`.
- **Integration touchpoint:** `build_context_bundle` (inject relevant entities),
  `MemoryExtractor` (replace free-text Mem0 extraction with typed extraction or
  run both).
- **Risks:** Mem0 already does most of this in cloud — duplicates effort. Need
  to decide whether to replace Mem0 or run side-by-side.
- **Skip if:** Current Mem0-based extraction is producing good-enough recall.

### #10 — Telegram / Discord proactive delivery channel

- **From:** `src/comms/channels/{telegram,discord}.ts` + `src/authority/approval-delivery.ts`
- **Why it matters:** FRIDAY is silent when the user isn't at the computer.
  Reminders and proactive suggestions could ping the user via Telegram.
- **Compatibility:** COMPATIBLE — single new module per channel.
- **Effort:** S–M per channel (≤ 1 week each).
- **Target FRIDAY files:** new `modules/comms/{telegram,discord}.py`.
- **Integration touchpoint:** `EventBus` (subscribe to `reminder_fired`,
  `awareness_struggle`, `goal_at_risk`), `ConfigService` (bot tokens).
- **Risks:** Bot tokens are sensitive — keep them in OS keyring, not config.yaml.
  Outbound network requests must go through `ConsentService`.
- **Skip if:** User is always at the computer and voice delivery is enough.

---

## 16. References & Caveats

### 16.1 jarvis source files cited

All paths relative to the cloned repo at `scratch/jarvis-ref/`:

- **Architecture:** `README.md`, `VISION.md`, `QUICKSTART.md`
- **Sidecar / cross-OS:**
  - `sidecar/types.go` (capability enum, RPC types, registration)
  - `sidecar/platform_linux.go`, `platform_windows.go`, `platform_darwin.go`
  - `sidecar/preflight.go`, `preflight_linux.go`, `preflight_windows.go`
  - `sidecar/main.go`, `client.go`, `handlers.go`
- **Actions / tools:**
  - `src/actions/tools/registry.ts` (ToolRegistry, ToolDefinition)
  - `src/actions/tools/builtin.ts` (~30 tool implementations)
  - `src/actions/tools/desktop.ts`, `agents.ts`, `delegate.ts`, `goals.ts`,
    `commitments.ts`, `documents.ts`, `approval-tool.ts`, `sidecar-route.ts`,
    `sidecar-list.ts`, `content.ts`, `workflows.ts`, `research.ts`
  - `src/actions/app-control/interface.ts` (AppController interface +
    `getAppController()` dispatcher)
  - `src/actions/app-control/linux.ts` (working impl), `windows.ts` and
    `macos.ts` (stubs)
- **Vault:**
  - `src/vault/schema.ts` (all 30+ tables + indexes + migrations)
- **Authority:**
  - `src/authority/engine.ts` (5-step decision)
  - `src/authority/learning.ts` (consecutive-approval pattern detection)
  - `src/authority/emergency.ts` (pause/kill/reset)
  - `src/roles/authority.ts` (action categories + impact map + voice-gate)
- **Agents:**
  - `src/agents/hierarchy.ts`, `delegation.ts`, `task-manager.ts`
- **Awareness:**
  - `src/awareness/service.ts`, `struggle-detector.ts`
- **LLM router:**
  - `src/llm/manager.ts` (fallback chain + retry + timeout)
- **Goals:**
  - `src/goals/service.ts` (3 timers + CRUD)
- **Workflows:**
  - `src/workflows/engine.ts`, `nl-builder.ts`
  - `src/workflows/nodes/{actions,error,logic,transform,triggers}/`
  - `src/workflows/triggers/{cron,poller,observer-bridge,screen-condition,webhook,manager}.ts`
- **Comms:**
  - `src/comms/channels/{telegram,discord,signal,whatsapp}.ts`

### 16.2 FRIDAY files cited

- **Architecture:** `docs/friday_architecture.md`, `CLAUDE.md`, `config.yaml`,
  `core/app.py`
- **Capability + extension:** `core/capability_registry.py`,
  `core/extensions/protocol.py`, `core/skill.py`
- **Routing:** `core/router.py`, `core/intent_recognizer.py`,
  `core/task_graph_executor.py`, `core/turn_context.py`, `core/turn_manager.py`
- **Memory:** `core/memory/{episodic,semantic,procedural,embeddings}.py`,
  `core/memory_service.py`, `core/memory_broker.py`, `core/memory_extractor.py`,
  `core/mem0_client.py`, `core/session_rag.py`
- **Workflows:** `core/workflow_orchestrator.py`
- **Plugins / modules:**
  - `modules/system_control/{plugin.py,screenshot.py,file_search.py,media_control.py}`
  - `modules/world_monitor/plugin.py`
  - `modules/task_manager/plugin.py`
  - `modules/research_agent/plugin.py`, `modules/workspace_agent/`
  - `modules/voice_io/{stt.py,tts.py,wake_porcupine.py,clap_detector.py}`
  - `modules/vision/plugin.py`, `modules/browser_automation/plugin.py`
- **Skills:** `skills/{whatsapp_skill.py,gemini_live_skill.py,email_ops.py,
  vision_skill.py,clap_control_skill.py}`
- **Cross-OS:** `SETUP_GUIDE.md`, `SETUP_GUIDE_WINDOWS.md`, "Platform Notes" in
  `CLAUDE.md`

### 16.3 Caveats

- **Source coverage:** I read all files cited above directly from the local clone.
  Files not cited were not read (e.g. UI under `scratch/jarvis-ref/ui/`,
  `src/personality/`, `src/cli/`, `src/sites/`). Where I describe jarvis
  features from those areas (e.g. dashboard UI), the description comes from
  `README.md` / `VISION.md`, not source.
- **jarvis was at commit HEAD on the `main` branch as of clone time** (depth=1).
  Cannot speak to historical or future versions.
- **FRIDAY state:** Cross-checked against `MEMORY.md` which records the v2
  refactor as "complete" and 378 tests passing as of 2026-05-14. Where I cite
  v2 components (TurnOrchestrator, TaskGraphExecutor, MemoryService), they exist
  in the code as confirmed by `core/` directory listing.
- **Effort estimates** in §14/§15 are rough — assume one experienced engineer
  familiar with both codebases, working full-time.
- **Compatibility tags** describe *technical fit*, not whether the feature is
  *desirable* to add. That is a product decision.
- **The clone at `scratch/jarvis-ref/` is gitignored** (`scratch/` is already
  excluded from the FRIDAY repo). Delete it manually when no longer needed:
  `rm -rf scratch/jarvis-ref/`.
