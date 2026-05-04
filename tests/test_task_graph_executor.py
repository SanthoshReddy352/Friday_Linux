"""Tests for TaskGraphExecutor — Phase 4 (v2) parallel executor."""
from __future__ import annotations

import os
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from core.capability_broker import ToolPlan, ToolStep  # noqa: E402
from core.capability_registry import CapabilityExecutionResult  # noqa: E402
from core.task_graph_executor import TaskGraphExecutor, topological_waves, _Node  # noqa: E402


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------

def _make_app(executor_fn):
    """Build a minimal app stub satisfying TaskGraphExecutor's interface.

    *executor_fn* is the function used as `capability_executor.execute`.
    It receives (name, text, args) and must return a CapabilityExecutionResult.
    """
    app = SimpleNamespace()
    app.session_id = "session-test"
    app.capability_executor = SimpleNamespace(execute=executor_fn)
    app.capability_registry = SimpleNamespace(get_descriptor=lambda _name: None)
    app.result_cache = None
    app.memory_broker = None
    app.turn_feedback = None

    app.response_finalizer = SimpleNamespace(
        remember_tool_use=MagicMock(),
        finalize=lambda text: text,
    )
    app.routing_state = SimpleNamespace(set_decision=MagicMock())
    app.context_store = SimpleNamespace(clear_pending_online=MagicMock())
    app.ordered_tool_executor = SimpleNamespace(
        execute=MagicMock(return_value="ordered-fallback")
    )
    return app


def _ok_result(name, output):
    return CapabilityExecutionResult(ok=True, name=name, output=output)


def _err_result(name, error):
    return CapabilityExecutionResult(ok=False, name=name, output="", error=error)


def _plan(*steps, mode="tool"):
    return ToolPlan(turn_id="t1", mode=mode, steps=list(steps))


# ---------------------------------------------------------------------------
# topological_waves
# ---------------------------------------------------------------------------

def test_topological_waves_groups_independent_nodes_into_one_wave():
    nodes = [
        _Node(step=None, node_id="a", depends_on=[], retries=0, input_index=0),
        _Node(step=None, node_id="b", depends_on=[], retries=0, input_index=1),
        _Node(step=None, node_id="c", depends_on=["a", "b"], retries=0, input_index=2),
    ]
    waves = topological_waves(nodes)
    assert [sorted(n.node_id for n in wave) for wave in waves] == [["a", "b"], ["c"]]


def test_topological_waves_detects_cycles():
    nodes = [
        _Node(step=None, node_id="a", depends_on=["b"], retries=0, input_index=0),
        _Node(step=None, node_id="b", depends_on=["a"], retries=0, input_index=1),
    ]
    with pytest.raises(ValueError, match="cycle"):
        topological_waves(nodes)


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------

def test_independent_steps_run_in_parallel():
    """Two independent slow steps should finish in roughly one step's time,
    not the sum, when running through TaskGraphExecutor."""
    barrier = threading.Barrier(2, timeout=5)

    def fake_executor(name, text, args):
        barrier.wait()        # both threads must reach here before either proceeds
        time.sleep(0.05)
        return _ok_result(name, f"{name}-out")

    app = _make_app(fake_executor)
    executor = TaskGraphExecutor(app, max_workers=4)

    plan = _plan(
        ToolStep(capability_name="alpha", node_id="a"),
        ToolStep(capability_name="beta", node_id="b"),
    )
    started = time.monotonic()
    response = executor.execute(plan, "user text")
    elapsed = time.monotonic() - started

    assert "alpha-out" in response and "beta-out" in response
    # If sequential the barrier would deadlock past its 5s timeout. The
    # successful return alone proves both nodes ran concurrently; the timing
    # check is a soft confirmation.
    assert elapsed < 1.0


def test_dependency_output_injected_into_dependent_args():
    """A node listing another in `depends_on` should receive that node's
    output in args under the upstream's node_id."""
    seen_args: dict[str, dict] = {}

    def fake_executor(name, text, args):
        seen_args[name] = dict(args)
        return _ok_result(name, f"{name}-output")

    app = _make_app(fake_executor)
    executor = TaskGraphExecutor(app, max_workers=4)

    plan = _plan(
        ToolStep(capability_name="search", node_id="search"),
        ToolStep(
            capability_name="summarize",
            node_id="summary",
            depends_on=["search"],
            args={"hint": "be brief"},
        ),
    )
    executor.execute(plan, "research X")

    assert seen_args["search"] == {}
    # Downstream sees its own args plus the upstream's output keyed by node_id.
    assert seen_args["summarize"] == {"hint": "be brief", "search": "search-output"}


def test_response_order_matches_input_order_even_when_finishes_out_of_order():
    delays = {"alpha": 0.05, "beta": 0.0}

    def fake_executor(name, text, args):
        time.sleep(delays[name])
        return _ok_result(name, f"{name}-out")

    app = _make_app(fake_executor)
    executor = TaskGraphExecutor(app, max_workers=2)

    plan = _plan(
        ToolStep(capability_name="alpha", node_id="a"),
        ToolStep(capability_name="beta", node_id="b"),
    )
    response = executor.execute(plan, "go")

    # Joined response preserves planner order (alpha then beta), independent
    # of which finished first.
    assert response.index("alpha-out") < response.index("beta-out")


# ---------------------------------------------------------------------------
# Timeout & retry semantics
# ---------------------------------------------------------------------------

def test_per_step_timeout_records_error_response():
    def fake_executor(name, text, args):
        time.sleep(0.5)
        return _ok_result(name, "never-seen")

    app = _make_app(fake_executor)
    executor = TaskGraphExecutor(app, max_workers=2)

    plan = _plan(
        ToolStep(capability_name="fast", node_id="f"),
        ToolStep(capability_name="slow", node_id="s", timeout_ms=50),
    )
    # Make "fast" actually fast so it doesn't dominate
    delays = {"fast": 0.0, "slow": 0.5}

    def selective_executor(name, text, args):
        time.sleep(delays.get(name, 0))
        return _ok_result(name, f"{name}-out")

    app.capability_executor = SimpleNamespace(execute=selective_executor)
    response = executor.execute(plan, "go")

    assert "fast-out" in response
    assert "timed out after 50ms" in response


def test_failed_step_retried_then_succeeds():
    attempts = {"flaky": 0}

    def fake_executor(name, text, args):
        attempts[name] += 1
        if attempts[name] < 3:
            return _err_result(name, "transient")
        return _ok_result(name, "finally")

    app = _make_app(fake_executor)
    executor = TaskGraphExecutor(app, max_workers=2)

    plan = _plan(
        ToolStep(capability_name="ok", node_id="o"),
        ToolStep(capability_name="flaky", node_id="f", retries=2),
    )
    response = executor.execute(plan, "go")

    assert attempts["flaky"] == 3
    assert "finally" in response


def test_failed_step_after_exhausted_retries_returns_error():
    def fake_executor(name, text, args):
        return _err_result(name, "always-fails")

    app = _make_app(fake_executor)
    executor = TaskGraphExecutor(app, max_workers=2)

    plan = _plan(ToolStep(capability_name="bad", node_id="b", retries=1),
                 ToolStep(capability_name="good", node_id="g"))
    # Make "good" succeed
    def mixed(name, text, args):
        if name == "good":
            return _ok_result(name, "good-out")
        return _err_result(name, "boom")
    app.capability_executor = SimpleNamespace(execute=mixed)

    response = executor.execute(plan, "go")
    assert "good-out" in response
    assert "Error running command: boom" in response


# ---------------------------------------------------------------------------
# Dispatch — modes that should forward to OrderedToolExecutor
# ---------------------------------------------------------------------------

def test_single_step_plan_forwards_to_ordered():
    app = _make_app(lambda *_: _ok_result("x", "out"))
    executor = TaskGraphExecutor(app)
    plan = _plan(ToolStep(capability_name="only", node_id="x"))
    result = executor.execute(plan, "go")
    assert result == "ordered-fallback"
    app.ordered_tool_executor.execute.assert_called_once()


def test_reply_mode_returns_plan_reply_directly():
    app = _make_app(lambda *_: _ok_result("x", "out"))
    executor = TaskGraphExecutor(app)
    plan = ToolPlan(turn_id="t", mode="reply", reply="hi there")
    assert executor.execute(plan, "ignored") == "hi there"
