"""Tests for the natural-language path through workspace_agent's
``create_calendar_event`` handler.

The handler used to require explicit ISO ``start`` / ``end`` args, so a
voice request like "schedule a dentist appointment today at 6 pm" hit a
"I need an event title, start time, and end time" prompt every turn and
the actual ``gws.calendar_create_event`` call was never made. The fix
delegates parsing to ``app.task_manager`` and falls back to a local
extractor when task_manager's regex misses a phrasing.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.task_manager.plugin import TaskManagerPlugin  # noqa: E402
from modules.workspace_agent.extension import (  # noqa: E402
    WorkspaceAgentExtension,
    _to_iso_local,
)


@pytest.fixture
def app():
    inst = MagicMock()
    inst.config = MagicMock()
    inst.config.get = MagicMock(return_value=None)
    inst.session_id = "test"
    inst.context_store = MagicMock()
    inst.event_bus = MagicMock()
    inst.router = MagicMock()
    return inst


@pytest.fixture
def workspace_with_task_manager(app):
    plugin = TaskManagerPlugin(app)  # registers app.task_manager
    extension = WorkspaceAgentExtension()
    extension.ctx = MagicMock()
    extension.ctx._app_ref = app
    return extension, plugin


@pytest.mark.parametrize(
    "raw_text, expected_summary, expected_hour",
    [
        ("schedule a dentist appointment today at 6 pm", "dentist appointment", 18),
        ("create a calendar event titled movie today at 9 pm", "movie", 21),
        ("create an event titled red row tomorrow at 8 pm", "red row", 20),
        ("add lunch with sara on friday at 1pm", "lunch with sara", 13),
        ("schedule meeting with bob today at 3pm", "with bob", 15),
    ],
)
def test_create_event_parses_natural_text(
    workspace_with_task_manager, raw_text, expected_summary, expected_hour,
):
    extension, _ = workspace_with_task_manager

    captured = {}

    def fake_create(summary, start, end, description=""):
        captured.update({"summary": summary, "start": start, "end": end, "description": description})
        return {"id": "evt-123"}

    with patch("modules.workspace_agent.extension.gws.calendar_create_event", side_effect=fake_create):
        result = extension._handle_create_event(raw_text, {})

    assert "added" in result.lower(), result
    assert "calendar" in result.lower()
    assert captured["summary"] == expected_summary
    # Start time should match the requested local hour.
    parsed_start = datetime.fromisoformat(captured["start"])
    assert parsed_start.hour == expected_hour
    # End defaults to start + 1 hour.
    parsed_end = datetime.fromisoformat(captured["end"])
    assert parsed_end - parsed_start == timedelta(hours=1)


def test_create_event_uses_iso_args_when_provided(workspace_with_task_manager):
    extension, _ = workspace_with_task_manager
    captured = {}

    def fake_create(summary, start, end, description=""):
        captured.update({"summary": summary, "start": start, "end": end})
        return {"id": "evt-iso"}

    args = {
        "summary": "manual event",
        "start": "2026-06-01T09:00:00+05:30",
        "end": "2026-06-01T10:30:00+05:30",
    }
    with patch("modules.workspace_agent.extension.gws.calendar_create_event", side_effect=fake_create):
        extension._handle_create_event("", args)

    assert captured["summary"] == "manual event"
    assert captured["start"].startswith("2026-06-01T09:00:00")
    assert captured["end"].startswith("2026-06-01T10:30:00")


def test_create_event_honours_for_duration(workspace_with_task_manager):
    extension, _ = workspace_with_task_manager
    captured = {}

    def fake_create(summary, start, end, description=""):
        captured.update({"start": start, "end": end})
        return {"id": "evt-dur"}

    raw = "schedule meeting with bob for 30 minutes today at 3pm"
    with patch("modules.workspace_agent.extension.gws.calendar_create_event", side_effect=fake_create):
        extension._handle_create_event(raw, {})

    parsed_start = datetime.fromisoformat(captured["start"])
    parsed_end = datetime.fromisoformat(captured["end"])
    assert parsed_end - parsed_start == timedelta(minutes=30)


def test_create_event_prompts_when_time_missing(workspace_with_task_manager):
    extension, _ = workspace_with_task_manager
    with patch("modules.workspace_agent.extension.gws.calendar_create_event") as create:
        result = extension._handle_create_event("schedule dinner", {})
    create.assert_not_called()
    # Either a "when should X start" prompt or a generic ask — but in any
    # case we must not silently call gws.
    assert "when" in result.lower() or "start" in result.lower()


def test_iso_helper_includes_local_offset():
    dt = datetime(2026, 5, 1, 18, 0, 0)
    iso = _to_iso_local(dt)
    # Either +HH:MM or -HH:MM, never naive.
    assert iso[-6] in ("+", "-"), f"missing offset in {iso}"
    assert iso[-3] == ":", f"non-RFC3339 offset in {iso}"
