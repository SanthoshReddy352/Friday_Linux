# FRIDAY Intent Routing Audit Report

**Date:** 2026-05-15  
**Scope:** All registered tools across `core/intent_recognizer.py` parser chain  
**Outcome:** 14 fixes applied across 3 passes; full test suite passes (482/482+)

---

## Executive Summary

A single user command — `"add a calendar event Lunch"` — routed to `manage_file` (the file-write tool) instead of `create_calendar_event`. Root cause: the parser chain placed `_parse_manage_file` before `_parse_reminder`, and a context-contamination bug caused `dialog_state.selected_file` (set by a prior screenshot) to be treated as the implicit target for any write action.

This audit catalogues every tool in the system, maps its routing coverage, identifies historical and latent failure modes, and documents the fixes applied.

---

## Architecture Overview

The intent pipeline is:

```
user text
    → IntentRecognizer._parse_clause()
        → (parser chain, first-match wins)
    → If no match: LLM tool router (ModelRouter)
    → CapabilityBroker.dispatch()
```

Parser chain order determines which tool intercepts ambiguous phrases. Order bugs cause **cross-domain hijacking** — a phrase that belongs to domain A is silently stolen by a parser for domain B that runs earlier in the chain.

---

## Tool-by-Tool Audit

### ✅ FIXED — Previously Failing

| Tool | Symptom | Root Cause | Fix Applied |
|---|---|---|---|
| `create_calendar_event` | `"add a calendar event Lunch"` → `manage_file` | `_parse_manage_file` ran before `_parse_reminder` | Reordered: reminder/notes parsers moved before file parsers |
| `set_reminder` | `"remind me at 5pm"` could hijack to file write | Same ordering bug | Same reorder fix |
| `manage_file` (write/append) | Screenshot context bled into write target — `"add a note"` after taking a screenshot wrote to the screenshot file | `_active_file_reference()` returned the screenshot from `dialog_state.selected_file` without requiring an explicit pronoun | Active-file guard: write/append now requires explicit pronoun (`it`, `that`, `this file`, etc.) |
| `summarize_file` | `"summarize my calendar"` could route to `summarize_file` | `_parse_file_action` summarize block had no domain exclusion | Added exclusion: calendar/news/reminder keywords bypass this branch |
| `read_file` | `"read my calendar events"` could route to `read_file` | `_parse_file_action` read block had no domain exclusion | Added exclusion: calendar/reminder keywords bypass this branch |
| `search_file` | `"find my meeting"` → `search_file` | `_parse_file_action` find block matched any `find` verb without requiring file context | Find/search now require "file" keyword or a file extension |
| `open_file` / `take_screenshot` | After "Which file?", saying "screenshot" → took new screenshot instead of opening screenshot file | "Which file?" prompt left no pending state; `_parse_screenshot` intercepted the bare word "screenshot" before `_parse_pending_selection` could use it | `dialog_state.pending_file_name_request` set when asking "Which file?"; checked first in `_parse_pending_selection`; user's word passed as explicit filename arg |
| `save_note` | `"make a note: buy milk"` → `manage_file` (asked "What should I name the file?") | `_parse_manage_file` caught "make" + no file guard; `_parse_notes` only matched "save note", "note down", "remember this" | Added "make a note", "jot down", "note that", "add to my notes" patterns to `_parse_notes` |
| `open_file` (candidate list) | `"screenshot"` with pending candidates → took new screenshot | `_parse_pending_selection` only did exact stem matching, not prefix matching | Added prefix matching (≥3 chars): "screenshot" now matches "screenshot_20260515.png" from candidate list |

---

### ✅ Correctly Routed — No Changes Needed

| Tool | Parser | Notes |
|---|---|---|
| `get_time` | `_parse_time_date` | Bare `\btime\b` removed from patterns; negative lookahead `(?!\s+of\b)` guards compound nouns |
| `get_date` | `_parse_time_date` | Correctly scoped |
| `take_screenshot` | `_parse_screenshot` | Requires explicit capture verb; hardened in 2026-05-14 pass |
| `set_volume` | `_parse_volume` | Requires audio context; hardened in 2026-05-14 pass |
| `get_cpu_ram` / `get_battery` | `_parse_system` | Bare `\bbattery\b` / `\bmemory\b` removed; requires status framing |
| `launch_app` | `_parse_launch_app` | `"open X"` / `"launch X"` dispatch; runs after file parsers |
| `play_youtube` / `play_youtube_music` | `_parse_browser_media` | Runs early; no cross-domain conflict |
| `set_volume` | `_parse_volume` | Runs early; audio context required |
| `analyze_screen` | `_parse_vision_action` | Added in 2026-05-09; runs before `_parse_file_action` — correct order |
| `search_google` | `_parse_google_search` | Requires explicit "search" + "google"/"web" framing |
| `send_email` | `_parse_email_action` | Explicit email verbs; runs before file parsers |
| `get_news_briefing` | `_parse_news_action` | Explicit news category keywords; runs before file parsers |
| `show_memories` / `save_note` | `_parse_memory_query` | Added in 2026-05-14; runs before file parsers |
| `enable_voice` / `disable_voice` | `_parse_voice_toggle` | Runs after file parsers — low collision risk |
| `focus_session` | `_parse_focus_session` | Runs early; no conflict observed |
| `dictate_text` | `_parse_dictation` | Runs early; no conflict observed |
| `research_topic` | `_parse_research_topic` | Explicit "research" verb; no conflict |

---

### ✅ FIXED (Pass 3) — Low-coverage tools given deterministic parsers

| Tool | Previous Risk | Fix Applied |
|---|---|---|
| `get_friday_status` | HIGH — "how are you doing?" could be answered as chat by LLM | Added `_parse_friday_status` — patterns: "friday status", "friday, are you ready", "are you ready friday", "assistant/runtime/model status", "check friday", "your status" |
| `get_world_monitor_news` | HIGH — tool is unregistered; could generate orphaned routing confusion | **RESOLVED** — `modules/world_monitor/__init__.py` `setup()` returns `None`; tool is never registered; `_parse_news_action` routes all news phrases to Feed Prism tools. No orphaned routing. |
| `query_document` | MEDIUM — conversational follow-ups without file path needed LLM routing | Added `_parse_query_document` — fires only when `[active_document=...]` prefix is injected by `_resolve_references`; routes any WH-question to `query_document` |
| `show_capabilities` | LOW — missing "what tools do you have", "what can I ask you" phrases | Expanded `_parse_help` with 5 new patterns covering "what tools do you have", "what features do you have", "what can I ask you", "list your tools", "tell me what you can do" |
| `start_fresh_session` / `resume_session` | LOW — hidden from help, only triggered by yes/no after goodbye flow | Correct by design — no change needed |

### ⚠️ LOW COVERAGE — Relies Entirely on LLM Routing

These tools have **zero deterministic parser coverage** and are only reachable via the LLM tool router. All previously HIGH/MEDIUM risks have been resolved above.

| Tool | Risk | Status |
|---|---|---|
| `start_fresh_session` / `resume_session` | LOW — hidden from help, only triggered by yes/no after goodbye flow | Correct by design |

---

## The 6 Fixes in Detail

### Fix 1: Parser Reordering (`_parse_clause` dispatch chain)

**Before:**
```
_parse_file_action → _parse_manage_file → _parse_voice_toggle → _parse_reminder → _parse_notes
```

**After:**
```
_parse_reminder → _parse_notes → _parse_file_action → _parse_manage_file → _parse_voice_toggle
```

**Why:** First-match wins. Calendar/reminder phrases containing words like "add", "create", "update" were intercepted by `_parse_manage_file` before `_parse_reminder` had a chance to claim them.

---

### Fix 2: `_parse_manage_file` Domain Guard

Added at entry of `_parse_manage_file`:

```python
if re.search(
    r"\b(?:calendar\s+event|event|meeting|appointment|reminder|reminders?)\b",
    clause_lower,
):
    return None
```

**Why:** Defense-in-depth. Even if the parser order changes in future, calendar phrases will never be claimed by file management.

---

### Fix 3: `_parse_manage_file` Active-File Context Guard

**Before:** Any write/append action used `_active_file_reference()` to find a target file from `dialog_state.selected_file`, even when the user said something completely unrelated to a file.

**After:** Write/append without an explicit filename now requires an explicit pronoun reference (`it`, `that`, `this file`, `the file`) in the text. Without one, the parser returns `None`.

**Why:** `dialog_state.selected_file` persists across turns (it's how "open it" works for files). A screenshot taken in turn 3 should not be silently treated as the target file in turn 7 when the user says "add a note."

---

### Fix 4: `_parse_file_action` Summarize Guard

Added exclusion list to the summarize branch:

```python
if re.search(r"\b(?:summarize|summary of|sum up)\b", clause_lower):
    if not re.search(
        r"\b(?:screen|display|desktop|monitor|email|emails|inbox|mail|messages?|"
        r"calendar|event|meeting|appointment|news|briefing|reminder|schedule|today)\b",
        clause_lower,
    ):
        return {"tool": "summarize_file", ...}
```

**Why:** "Summarize my calendar events" should never route to `summarize_file`.

---

### Fix 5: `_parse_file_action` Read Guard

Added exclusion to the read branch:

```python
if re.search(r"\b(?:read|show contents of|preview)\b", clause_lower) and (...):
    if not re.search(
        r"\b(?:calendar|event|meeting|appointment|reminder|schedule|news|briefing)\b",
        clause_lower,
    ):
        return {"tool": "read_file", ...}
```

**Why:** "Read my calendar" belongs to the calendar domain, not the file domain.

---

### Fix 6: `_parse_file_action` Find/Search Guard

Changed find/search branch from matching any `find`/`search`/`locate` verb to requiring file context:

```python
if re.search(r"\b(?:find|search|locate)\b", clause_lower) and (
    "file" in clause_lower
    or re.search(r"\.[a-z]{2,4}\b", clause_lower)  # has file extension
):
    return {"tool": "search_file", ...}
```

**Why:** "Find my meeting" should not route to `search_file`. The file extension check (`\.py`, `.pdf`, etc.) preserves the case where the user names a specific file type.

---

## Architectural Principles Applied

These fixes align with industry best practices for intent routing in voice assistants:

1. **Deterministic fast-path first** — well-defined intents (calendar, reminder, notes) are claimed by domain-specific parsers before any generic parser can intercept them.

2. **Domain guards as defense-in-depth** — even with correct ordering, each parser should reject phrases from other domains by keyword.

3. **Context-contamination prevention** — implicit context (active file, last tool) must not be applied unless the user's current utterance explicitly references it by pronoun or direct name.

4. **Exclusion lists over inclusion lists** — it is safer to enumerate what a parser does NOT handle than to enumerate every possible phrasing it should handle.

5. **LLM as last resort, not first** — the LLM tool router is fallback for genuinely ambiguous cases. Clearly defined commands (create event, set reminder, find file named X) should never require LLM inference.

---

## Test Coverage

4 new automated tests added to `tests/test_system_control_tools.py` for screenshot Wayland fixes.

The following intent routing behaviors are now covered by the existing unit test suite:
- `test_intent_recognizer.py` — tests for `_parse_reminder`, `_parse_manage_file`, `_parse_file_action`
- `tests/test_app_flow.py` — `test_on_demand_voice_mode_mutes_after_voice_turn` (the mic event sequencing bug fixed here)

Manual validation cases added to `docs/testing_guide.md` §17 as regression guards T-IR.1 through T-IR.4.

---

## Remaining Recommendations

All HIGH and MEDIUM items from the original audit have been resolved. The remaining item is architectural:

| Priority | Action |
|---|---|
| LOW | Consider a domain-classifier layer (fast regex → semantic cluster) for all 50+ tools to replace the flat first-match chain as the tool set grows |

---

*Generated from audit of `core/intent_recognizer.py` — 482/482 automated tests passing after all fixes.*
