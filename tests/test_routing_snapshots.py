"""Routing snapshot tests.

Locks the deterministic-fallback behavior of CommandRouter so the Phase 1+
refactor (which dismantles the router) cannot silently regress real-world
voice/text flows.

How it works:
  * tests/snapshots/routing_snapshots.yaml carries fixture inputs and
    expected tool dispatches.
  * For each fixture we spin up a fresh CommandRouter with NO LLM loaded
    (LLM=None forces the deterministic path) and register a curated tool
    catalog matching what real plugins register at startup. Handlers are
    capturing stubs that record (name, args).
  * The fixture's `expects.calls` list is matched in order against the
    captured dispatches.

The catalog deliberately mirrors the production specs from:
  modules/system_control/plugin.py
  modules/task_manager/plugin.py
  modules/world_monitor/plugin.py
  modules/browser_automation/plugin.py
  modules/voice_io/plugin.py
  modules/llm_chat/plugin.py

If any of those files add or change a tool spec in a way that would alter
routing, that fixture should be updated (or added) here in the same PR.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.dialog_state import DialogState
from core.router import CommandRouter


SNAPSHOT_FILE = Path(__file__).parent / "snapshots" / "routing_snapshots.yaml"


# ---------------------------------------------------------------------------
# Tool catalog (mirrors production plugin specs, handlers replaced by capture)
# ---------------------------------------------------------------------------

TOOL_CATALOG = [
    # --- system_control ----------------------------------------------------
    {
        "name": "get_system_status",
        "description": "Report overall system health: CPU usage, RAM usage, and battery level.",
        "parameters": {},
        "context_terms": ["system info", "system information", "system details", "system status"],
    },
    {
        "name": "get_friday_status",
        "description": "Report FRIDAY runtime status.",
        "parameters": {},
        "context_terms": ["friday status", "assistant status", "runtime status", "model status"],
    },
    {
        "name": "get_battery",
        "description": "Check the current battery percentage.",
        "parameters": {},
        "context_terms": ["battery", "charge", "power"],
    },
    {
        "name": "get_cpu_ram",
        "description": "Show current CPU and RAM usage statistics.",
        "parameters": {},
        "context_terms": ["cpu usage", "ram usage", "memory usage", "performance", "resource usage"],
    },
    {
        "name": "launch_app",
        "description": "Open or launch a desktop application by name.",
        "parameters": {
            "app_name": "string",
            "app_names": "array[string]",
        },
        "context_terms": ["browser", "calculator", "chrome", "firefox", "files", "nautilus"],
    },
    {
        "name": "set_volume",
        "description": "Control system audio volume.",
        "parameters": {
            "direction": "string",
            "steps": "integer",
            "percent": "integer",
        },
        "context_terms": ["volume", "audio", "sound", "mute", "unmute", "louder", "quieter"],
    },
    {
        "name": "take_screenshot",
        "description": "Capture the current screen.",
        "parameters": {},
    },
    {
        "name": "search_file",
        "description": "Search for a file by name.",
        "parameters": {
            "filename": "string",
            "folder": "string",
            "extension": "string",
        },
    },
    {
        "name": "manage_file",
        "description": "Create, write, append, or read a text file.",
        "parameters": {
            "action": "string",
            "filename": "string",
            "folder": "string",
            "content": "string",
            "extension": "string",
        },
    },
    {
        "name": "open_file",
        "description": "Open a specific file using the default application.",
        "parameters": {"filename": "string"},
    },
    {
        "name": "read_file",
        "description": "Read or preview the contents of a file.",
        "parameters": {"filename": "string"},
    },
    {
        "name": "summarize_file",
        "description": "Summarize the contents of a file offline.",
        "parameters": {"filename": "string"},
    },
    {
        "name": "list_folder_contents",
        "description": "List the visible files inside a folder.",
        "parameters": {"folder": "string"},
    },
    {
        "name": "open_folder",
        "description": "Open a folder in the system file manager.",
        "parameters": {"folder": "string"},
    },
    {
        "name": "select_file_candidate",
        "description": "Choose one file from a pending list of candidates.",
        "parameters": {},
    },
    {
        "name": "confirm_yes",
        "description": "User confirms a pending action.",
        "parameters": {},
    },
    {
        "name": "confirm_no",
        "description": "User declines or cancels a pending action.",
        "parameters": {},
    },
    {
        "name": "shutdown_assistant",
        "description": "Close the application and say goodbye.",
        "parameters": {},
        "aliases": ["bye", "goodbye", "exit program", "close assistant", "switch off"],
    },
    # --- task_manager ------------------------------------------------------
    {
        "name": "get_time",
        "description": "Tell the current time.",
        "parameters": {},
        "context_terms": ["time", "clock", "what time"],
    },
    {
        "name": "get_date",
        "description": "Tell today's date.",
        "parameters": {},
        "context_terms": ["date", "today", "day of"],
    },
    # --- world_monitor -----------------------------------------------------
    {
        "name": "get_world_monitor_news",
        "description": "Fetch concise WorldMonitor news briefings from category-specific feeds.",
        "parameters": {
            "category": "string",
            "focus": "string",
            "country_code": "string",
            "limit": "integer",
            "min_threat": "string",
            "window_hours": "integer",
        },
        "aliases": [
            "world monitor",
            "global intelligence",
            "global news",
            "global news brief",
            "geopolitical brief",
        ],
        "context_terms": ["world monitor", "geopolitical", "global brief"],
    },
    # --- browser_automation -----------------------------------------------
    {
        "name": "play_youtube",
        "description": "Play a song or video on YouTube.",
        "parameters": {"query": "string"},
        "context_terms": ["youtube", "play"],
    },
    {
        "name": "play_youtube_music",
        "description": "Play a song on YouTube Music.",
        "parameters": {"query": "string"},
        "context_terms": ["youtube music"],
    },
    {
        "name": "browser_media_control",
        "description": "Control playback in the browser tab.",
        "parameters": {"action": "string"},
    },
    {
        "name": "open_browser_url",
        "description": "Open a URL in the browser.",
        "parameters": {"url": "string"},
    },
    # --- voice_io ----------------------------------------------------------
    {
        "name": "enable_voice",
        "description": "Turn on voice listening.",
        "parameters": {},
        "context_terms": ["enable voice", "turn on voice", "start listening"],
    },
    {
        "name": "disable_voice",
        "description": "Turn off voice listening.",
        "parameters": {},
        "context_terms": ["disable voice", "turn off voice", "stop listening"],
    },
    {
        "name": "set_voice_mode",
        "description": "Change the listening mode.",
        "parameters": {"mode": "string"},
    },
    # --- llm_chat (catch-all fallback) ------------------------------------
    {
        "name": "llm_chat",
        "description": "Open-ended chat with the local model.",
        "parameters": {"query": "string"},
    },
]


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def _load_fixtures():
    with open(SNAPSHOT_FILE) as fh:
        doc = yaml.safe_load(fh)
    return doc.get("fixtures", [])


FIXTURES = _load_fixtures()


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------


def _build_router():
    """Fresh CommandRouter with deterministic-only path and full tool catalog."""
    event_bus = MagicMock()
    router = CommandRouter(event_bus)
    router.llm = None
    router.tool_llm = None
    router.enable_llm_tool_routing = False
    router.dialog_state = DialogState()

    captured: list[tuple[str, dict]] = []

    def make_handler(name):
        def _handler(text, args):
            captured.append((name, dict(args or {})))
            # Return a deterministic stub so multi-action plans still concatenate
            return f"<{name}>"
        return _handler

    for spec in TOOL_CATALOG:
        router.register_tool(spec, make_handler(spec["name"]))

    return router, captured


def _format_id(fixture):
    return fixture["id"]


@pytest.mark.parametrize("fixture", FIXTURES, ids=_format_id)
def test_routing_snapshot(fixture):
    router, captured = _build_router()
    expects = fixture.get("expects", {}) or {}

    response = router.process_text(fixture["input"])

    if expects.get("no_match"):
        # No-match means: nothing was dispatched, OR only the chat fallback
        # ran and returned the canonical "didn't understand" reply, OR the
        # input was entirely empty/punctuation and process_text returned "".
        if captured:
            assert all(name == "llm_chat" for name, _ in captured), (
                f"[{fixture['id']}] expected no_match but dispatched: {captured}"
            )
        else:
            assert response == "" or "didn't understand" in (response or "").lower()
        return

    expected_calls = expects.get("calls", []) or []
    assert len(captured) >= len(expected_calls), (
        f"[{fixture['id']}] too few dispatches. expected at least "
        f"{len(expected_calls)}, captured {len(captured)}: {captured}"
    )

    for i, expected in enumerate(expected_calls):
        actual_name, actual_args = captured[i]
        assert actual_name == expected["tool"], (
            f"[{fixture['id']}] call #{i}: expected tool '{expected['tool']}', "
            f"got '{actual_name}' (full capture: {captured})"
        )
        for k, v in (expected.get("args") or {}).items():
            assert actual_args.get(k) == v, (
                f"[{fixture['id']}] call #{i} ({actual_name}): "
                f"arg '{k}' expected {v!r}, got {actual_args.get(k)!r} "
                f"(full args: {actual_args})"
            )

    if "response_contains" in expects:
        assert expects["response_contains"] in (response or ""), (
            f"[{fixture['id']}] response missing substring "
            f"{expects['response_contains']!r}: {response!r}"
        )


def test_fixtures_have_unique_ids():
    """Catch typos / dup fixtures early — pytest's parametrize would otherwise
    silently overwrite duplicates."""
    ids = [f["id"] for f in FIXTURES]
    assert len(ids) == len(set(ids)), f"duplicate fixture ids: {sorted(ids)}"


def test_fixture_count_floor():
    """Phase 0 commits to a minimum coverage floor. If fixtures drop below
    this, the regression net has shrunk — investigate before lowering."""
    assert len(FIXTURES) >= 25, f"snapshot fixtures dropped to {len(FIXTURES)}; minimum is 25"
