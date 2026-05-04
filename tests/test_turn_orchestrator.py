"""Tests for TurnOrchestrator — Phase 3 (v2) single-flow turn handler."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.capability_broker import ToolPlan, ToolStep  # noqa: E402
from core.planning.intent_engine import IntentResult  # noqa: E402
from core.planning.turn_orchestrator import (  # noqa: E402
    TurnOrchestrator,
    TurnRequest,
    TurnResponse,
)
from core.planning.workflow_coordinator import WorkflowResume  # noqa: E402


def _build_orchestrator(*, plan=None, executor_response="ok"):
    intent_engine = MagicMock()
    intent_engine.classify.return_value = IntentResult(
        tool=None, source="none", confidence=0.0
    )

    planner_engine = MagicMock()
    planner_engine.plan.return_value = plan or ToolPlan(turn_id="t", mode="tool")

    workflow_coord = MagicMock()
    workflow_coord.try_resume.return_value = WorkflowResume(handled=False)

    memory_broker = MagicMock()
    memory_broker.build_context_bundle.return_value = {"persona": {"persona_id": "p1"}}

    executor = SimpleNamespace(
        execute=MagicMock(return_value=executor_response)
    )

    app = SimpleNamespace()
    app.session_id = "session-1"
    app.ordered_tool_executor = executor
    app.task_graph_executor = executor
    app.delegation_manager = SimpleNamespace(
        memory_curator=SimpleNamespace(curate=MagicMock())
    )
    app.conversation_agent = SimpleNamespace(_select_executor=lambda plan: executor)

    orch = TurnOrchestrator(
        app,
        intent_engine=intent_engine,
        planner_engine=planner_engine,
        workflow_coordinator=workflow_coord,
        memory_broker=memory_broker,
    )
    return orch, app, intent_engine, planner_engine, workflow_coord, memory_broker, executor


def test_orchestrator_returns_workflow_response_when_workflow_handles():
    orch, app, intent, planner, wf, memory, executor = _build_orchestrator()
    wf.try_resume.return_value = WorkflowResume(
        handled=True, response="event saved", name="calendar_event_workflow"
    )

    request = TurnRequest(text="tomorrow at 10am", source="text", session_id="session-1")
    response = orch.handle(request)

    assert isinstance(response, TurnResponse)
    assert response.response == "event saved"
    assert response.source == "workflow"
    assert response.plan_mode == "workflow"
    # Intent classifier and planner should not be called when a workflow handles it.
    intent.classify.assert_not_called()
    planner.plan.assert_not_called()
    executor.execute.assert_not_called()
    # Memory curation still happens for workflow turns.
    app.delegation_manager.memory_curator.curate.assert_called_once()


def test_orchestrator_calls_planner_and_executor_when_no_workflow():
    plan = ToolPlan(
        turn_id="t",
        mode="tool",
        ack="working on it",
        steps=[ToolStep(capability_name="weather", node_id="w")],
    )
    orch, app, intent, planner, wf, memory, executor = _build_orchestrator(
        plan=plan, executor_response="sunny and 22"
    )

    request = TurnRequest(text="how is the weather", session_id="session-1")
    response = orch.handle(request)

    assert response.response == "sunny and 22"
    assert response.spoken_ack == "working on it"
    assert response.plan_mode == "tool"
    intent.classify.assert_called_once()
    planner.plan.assert_called_once()
    executor.execute.assert_called_once_with(plan, "how is the weather", turn=None)


def test_orchestrator_marks_high_confidence_intent_as_intent_source():
    plan = ToolPlan(
        turn_id="t",
        mode="tool",
        steps=[ToolStep(capability_name="launch_app", node_id="x")],
    )
    orch, app, intent, planner, wf, memory, executor = _build_orchestrator(plan=plan)
    intent.classify.return_value = IntentResult(
        tool="launch_app",
        args={"app": "chrome"},
        confidence=1.0,
        source="regex",
        actions=[{"tool": "launch_app", "args": {"app": "chrome"}}],
    )

    response = orch.handle(TurnRequest(text="open chrome", session_id="s"))
    assert response.source == "intent"


def test_orchestrator_returns_error_response_on_planner_exception():
    orch, app, intent, planner, wf, memory, executor = _build_orchestrator()
    planner.plan.side_effect = RuntimeError("planner exploded")

    response = orch.handle(TurnRequest(text="anything", session_id="s"))
    assert "problem planning" in response.response
    assert response.error == "planner exploded"
    executor.execute.assert_not_called()


def test_orchestrator_returns_error_response_on_executor_exception():
    plan = ToolPlan(
        turn_id="t", mode="tool",
        steps=[ToolStep(capability_name="oops", node_id="o")],
    )
    orch, app, intent, planner, wf, memory, executor = _build_orchestrator(plan=plan)
    executor.execute.side_effect = RuntimeError("tool exploded")

    response = orch.handle(TurnRequest(text="run something", session_id="s"))
    assert "problem running" in response.response
    assert response.error == "tool exploded"


def test_orchestrator_records_duration_ms():
    orch, *_ = _build_orchestrator()
    response = orch.handle(TurnRequest(text="hi", session_id="s"))
    assert response.duration_ms >= 0.0


def test_orchestrator_writes_context_bundle_back_into_ctx():
    orch, app, intent, planner, wf, memory, executor = _build_orchestrator()
    ctx = SimpleNamespace(turn_id="t", trace_id="tr", source="text")
    orch.handle(TurnRequest(text="hi", session_id="s", turn_id="t"), ctx=ctx)
    assert ctx.context_bundle == {"persona": {"persona_id": "p1"}}
