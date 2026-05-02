"""TurnManager → TurnOrchestrator dispatch integration test.

Phase 3 of the v2 architecture. Verifies that when
`routing.orchestrator: "v2"` is set, TurnManager hands the turn to
TurnOrchestrator instead of taking the legacy CapabilityBroker path,
and that the legacy path is still used when the flag is unset.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.planning.turn_orchestrator import TurnResponse  # noqa: E402
from core.turn_manager import TurnManager  # noqa: E402


class _Cfg:
    def __init__(self, value: str | None):
        self._value = value

    def get(self, key, default=None):
        if key == "routing.orchestrator":
            return self._value if self._value is not None else default
        return default


def _build_app(orchestrator_value: str | None):
    """Minimal app stub satisfying TurnManager's needs for both paths."""
    app = SimpleNamespace()
    app.config = _Cfg(orchestrator_value)
    app.session_id = "sess-1"

    # Persistent / state stores
    app.context_store = MagicMock()
    app.context_store.get_session_state.return_value = {}
    app.routing_state = SimpleNamespace(voice_already_spoken=False)
    app.dialog_state = MagicMock()

    # Feedback runtime — return a turn record with a turn_id.
    turn_record = SimpleNamespace(turn_id="turn-abc")
    app.turn_feedback = MagicMock()
    app.turn_feedback.start_turn.return_value = turn_record

    # Capability registry — list_capabilities decides legacy router-vs-broker
    # path; populate so the broker branch is selected when v2 is off.
    app.capability_registry = MagicMock()
    app.capability_registry.list_capabilities.return_value = ["x"]

    # Legacy path objects (used only when v2 flag is off).
    app.router = MagicMock()
    app.router.process_text.return_value = "legacy-router-response"

    app._active_turn_record = None
    app.current_turn_context = None
    app._last_turn_speech_managed = False

    # Orchestrator stub — only consulted when flag == "v2".
    app.turn_orchestrator = MagicMock()
    app.turn_orchestrator.handle.return_value = TurnResponse(
        response="orchestrator-response",
        spoken_ack="ack-text",
        source="planner",
        trace_id="turn-abc",
        duration_ms=12.0,
        plan_mode="tool",
    )
    return app, turn_record


def test_v2_flag_routes_through_orchestrator():
    app, turn_record = _build_app("v2")
    conv_agent = MagicMock()
    tm = TurnManager(app, conv_agent)

    response = tm.handle_turn("hello", source="text")

    assert response == "orchestrator-response"
    app.turn_orchestrator.handle.assert_called_once()
    call_request = app.turn_orchestrator.handle.call_args.args[0]
    assert call_request.text == "hello"
    assert call_request.source == "text"
    assert call_request.session_id == "sess-1"
    assert call_request.turn_id == "turn-abc"
    # Legacy paths must NOT have been touched.
    conv_agent.build_tool_plan.assert_not_called()
    conv_agent.execute_tool_plan.assert_not_called()
    app.router.process_text.assert_not_called()
    # Feedback completion still emitted with the orchestrator response.
    app.turn_feedback.complete_turn.assert_called_once()
    args, kwargs = app.turn_feedback.complete_turn.call_args
    assert args[1] == "orchestrator-response"
    # spoken_ack from the orchestrator was forwarded to feedback.
    app.turn_feedback.emit_ack.assert_called_once_with(turn_record, "ack-text")


def test_default_flag_keeps_legacy_path():
    app, turn_record = _build_app(None)
    conv_agent = MagicMock()
    plan = SimpleNamespace(ack="", estimated_latency="interactive")
    conv_agent.build_tool_plan.return_value = (plan, {"persona": {}})
    conv_agent.execute_tool_plan.return_value = "legacy-broker-response"
    tm = TurnManager(app, conv_agent)

    response = tm.handle_turn("hello", source="text")

    assert response == "legacy-broker-response"
    app.turn_orchestrator.handle.assert_not_called()
    conv_agent.build_tool_plan.assert_called_once()
    conv_agent.execute_tool_plan.assert_called_once()


def test_v1_flag_explicit_keeps_legacy_path():
    app, turn_record = _build_app("v1")
    conv_agent = MagicMock()
    plan = SimpleNamespace(ack="", estimated_latency="interactive")
    conv_agent.build_tool_plan.return_value = (plan, {})
    conv_agent.execute_tool_plan.return_value = "legacy"
    tm = TurnManager(app, conv_agent)

    tm.handle_turn("hello", source="text")
    app.turn_orchestrator.handle.assert_not_called()


def test_v2_orchestrator_error_surfaces_through_feedback_fail_turn():
    app, turn_record = _build_app("v2")
    app.turn_orchestrator.handle.return_value = TurnResponse(
        response="failed text",
        source="planner",
        trace_id="turn-abc",
        duration_ms=1.0,
        error="boom",
    )
    conv_agent = MagicMock()
    tm = TurnManager(app, conv_agent)

    import pytest
    with pytest.raises(RuntimeError, match="boom"):
        tm.handle_turn("hello", source="text")
    app.turn_feedback.fail_turn.assert_called_once()
