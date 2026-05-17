# FRIDAY Linux — Project Instructions

## Knowledge Graph (RAG)

A pre-built knowledge graph of this codebase lives at `/home/tricky/Friday_Linux/graphify-out/`.

**Before answering any question about the codebase** (architecture, where something is defined, how components connect, what calls what), query the graph first:

```
/graphify query "<your question>"
```

Files in `graphify-out/`:
- `graph.json` — 2,797 nodes, 4,915 edges across the full project (excludes `libs_backup/`)
- `GRAPH_REPORT.md` — community map, god nodes, and surprising connections
- `graph.html` — interactive visualization (open in browser)

Use the graph to:
- Find which file/class owns a concept before reading code
- Trace call chains (e.g. how a voice turn flows from STT → Router → Capability → TTS)
- Identify which community a module belongs to before exploring that area
- Verify inferred relationships before acting on them (edges tagged INFERRED need confirmation)

**Key god nodes** (highest connectivity — touch these carefully):
1. `STTEngine` (110 edges) — `modules/voice_io/stt.py`
2. `FridayApp` (74 edges) — `core/app.py`
3. `TaskManagerPlugin` (74 edges) — `modules/task_manager/plugin.py`
4. `CommandRouter` (73 edges) — `core/router.py`
5. `BrowserMediaService` (73 edges) — `modules/browser_automation/service.py`

Keep the graph up to date: after adding or changing significant files, run `/graphify . --update` to incrementally re-extract only the changed files.

## Project Overview

FRIDAY is a local-first, cross-platform AI assistant (Linux + Windows). It uses a modular plugin architecture with a capability registry, a v2 turn orchestration pipeline, and a three-tier memory system (episodic, semantic, procedural).

## Testing Guide (single source of truth)

`docs/testing_guide.md` is the **only** manual testing reference for this project.

**After modifying or adding any feature, you MUST:**
1. Add a row to the Modification Log in `docs/testing_guide.md` with today's date, the affected section, and a one-line description of the change.
2. Add or update test cases in the relevant section using the next available `[T-N.M]` ID.
3. Add a regression guard to §17 if the test is must-not-break.
4. Update `tests/` (automated suite) in the same change when the behavior can be unit-tested.

**Every test you write MUST include a `**Verify:**` block** with at least one runnable command:
- Routing / response tests → `grep -i "phrase" logs/friday.log | tail -5`
- DB side-effects → `sqlite3 data/friday.db "SELECT ... ORDER BY id DESC LIMIT 3;"`
- File creation → `ls -la ~/path && cat ~/path`
- Config changes → `python -c "from core.config import ConfigManager; c=ConfigManager(); c.load(); print(c.get('key'))"`
- Pure visual / audio → `**Verify:** Visual check — [what to look for].`
Never write a test whose only pass criterion is "FRIDAY responds correctly".

Do **not** update the old `docs/manual_testing_guide.md` — it is archived for historical reference only.

## Response & Plan Logging

**After every query response**, save the exchange to `responses/` in the project root:
- Folder: `responses/`
- Filename: `YYYY-MM-DD_HH-MM-SS.md` (date/time the query was received)
- File must contain:
  - `## Prompt` — the exact user message
  - `## Response` — the full response/work produced

**In plan mode**, additionally save the plan to `plan/` in the project root:
- Folder: `plan/`
- Filename: `YYYY-MM-DD_HH-MM-SS_plan.md` (same timestamp as the query)
- File must contain the complete plan as produced by ExitPlanMode

Both folders must exist; create them if absent. These files are logs — never modify a saved file after writing it.

## Platform Notes

This is a cross-platform project (Linux + Windows). Platform-specific code must guard with `platform.system()` or `os.name`. Key patterns already in use:
- Subprocess spawning: `start_new_session=True` (Linux/macOS) vs `creationflags=DETACHED_PROCESS` (Windows)
- Venv python: `.venv/bin/python3` (Linux) vs `.venv/Scripts/python.exe` (Windows)
- `strftime("%-I")` is Linux-only — use `.lstrip("0")` on Windows-safe format instead
- Always pass `encoding="utf-8", errors="replace"` to `subprocess.run(..., text=True)`
