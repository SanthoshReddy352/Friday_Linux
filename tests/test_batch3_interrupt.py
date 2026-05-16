"""Tests for Batch 3 — Interrupt bus & global cancellation (Issue 3).

Covers:
* `core.interrupt_bus.InterruptBus` — scopes, subscribers, generation counter,
  subscriber exception isolation.
* `core.dialog_state.DialogState.reset_pending` — clears every pending-* field.
* `WorkflowOrchestrator.continue_active` cancel path — fires the bus signal.
* End-to-end: a bus signal resets a DialogState that has all four pending
  fields populated.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.assistant_context import AssistantContext
from core.context_store import ContextStore
from core.dialog_state import DialogState, PendingClarification, PendingFileRequest
from core.interrupt_bus import (
    InterruptBus,
    InterruptSignal,
    get_interrupt_bus,
)
from core.router import CommandRouter
from core.workflow_orchestrator import WorkflowOrchestrator
import modules.task_manager.plugin as task_manager_plugin
from modules.task_manager.plugin import TaskManagerPlugin


# ---------------------------------------------------------------------------
# InterruptBus
# ---------------------------------------------------------------------------


class TestInterruptBus:
    def setup_method(self):
        # Each test gets a fresh local bus so subscribers from earlier tests
        # don't leak. Production code uses get_interrupt_bus() singleton.
        self.bus = InterruptBus()

    def test_signal_increments_generation(self):
        assert self.bus.generation == 0
        self.bus.signal("a")
        assert self.bus.generation == 1
        self.bus.signal("b")
        assert self.bus.generation == 2

    def test_subscriber_receives_matching_scope(self):
        received: list[InterruptSignal] = []
        self.bus.subscribe("tts", received.append)
        self.bus.signal("flush", scope="tts")
        assert len(received) == 1
        assert received[0].scope == "tts"
        assert received[0].reason == "flush"

    def test_all_subscriber_receives_every_signal(self):
        received: list[InterruptSignal] = []
        self.bus.subscribe("all", received.append)
        self.bus.signal("a", scope="tts")
        self.bus.signal("b", scope="workflow")
        self.bus.signal("c", scope="all")
        assert [s.reason for s in received] == ["a", "b", "c"]

    def test_scoped_subscriber_skipped_for_other_scopes(self):
        received: list[InterruptSignal] = []
        self.bus.subscribe("tts", received.append)
        self.bus.signal("workflow_cancel", scope="workflow")
        assert received == []

    def test_all_signal_reaches_every_subscriber(self):
        # When scope="all" is emitted, every subscriber regardless of their
        # registered scope must fire — that's the contract STT relies on.
        tts_hits: list[InterruptSignal] = []
        workflow_hits: list[InterruptSignal] = []
        all_hits: list[InterruptSignal] = []
        self.bus.subscribe("tts", tts_hits.append)
        self.bus.subscribe("workflow", workflow_hits.append)
        self.bus.subscribe("all", all_hits.append)
        self.bus.signal("user_stop", scope="all")
        assert len(tts_hits) == 1
        assert len(workflow_hits) == 1
        assert len(all_hits) == 1

    def test_unsubscribe_stops_future_signals(self):
        received: list[InterruptSignal] = []
        unsubscribe = self.bus.subscribe("all", received.append)
        self.bus.signal("first")
        unsubscribe()
        self.bus.signal("second")
        assert len(received) == 1

    def test_subscriber_exception_does_not_stop_others(self):
        good: list[InterruptSignal] = []

        def angry(_sig):
            raise RuntimeError("boom")

        self.bus.subscribe("all", angry)
        self.bus.subscribe("all", good.append)
        self.bus.signal("oops")
        assert len(good) == 1

    def test_signaled_since_detects_new_signal(self):
        starting = self.bus.generation
        assert self.bus.signaled_since(starting) is False
        self.bus.signal("user_stop")
        assert self.bus.signaled_since(starting) is True

    def test_invalid_scope_raises(self):
        with pytest.raises(ValueError):
            self.bus.signal("oops", scope="garbage")  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            self.bus.subscribe("garbage", lambda _: None)  # type: ignore[arg-type]

    def test_singleton_accessor_returns_same_instance(self):
        assert get_interrupt_bus() is get_interrupt_bus()


# ---------------------------------------------------------------------------
# DialogState.reset_pending
# ---------------------------------------------------------------------------


class TestDialogStateReset:
    def test_reset_clears_every_pending_field(self):
        ds = DialogState()
        ds.pending_file_request = PendingFileRequest(candidates=["a.txt"])
        ds.pending_clarification = PendingClarification(action_text="confirm")
        ds.pending_file_name_request = "open"
        ds.pending_folder_request = "list"

        ds.reset_pending("user_stop")

        assert ds.pending_file_request is None
        assert ds.pending_clarification is None
        assert ds.pending_file_name_request is None
        assert ds.pending_folder_request is None

    def test_reset_is_safe_when_nothing_pending(self):
        ds = DialogState()
        # No exception, no side effect on non-pending fields.
        ds.current_folder = "/tmp/foo"
        ds.reset_pending()
        assert ds.current_folder == "/tmp/foo"


# ---------------------------------------------------------------------------
# End-to-end — bus signal triggers DialogState reset via subscription
# ---------------------------------------------------------------------------


class TestBusToDialogStateWiring:
    def test_subscribed_reset_fires_on_signal(self):
        bus = InterruptBus()
        ds = DialogState()
        ds.pending_clarification = PendingClarification(action_text="open file?")
        ds.pending_file_name_request = "open"

        bus.subscribe("all", lambda sig: ds.reset_pending(sig.reason))
        bus.signal("user_barge_in", scope="all")

        assert ds.pending_clarification is None
        assert ds.pending_file_name_request is None


# ---------------------------------------------------------------------------
# Workflow cancel fires bus
# ---------------------------------------------------------------------------


def _build_app(tmp_path):
    app = SimpleNamespace()
    app.config = SimpleNamespace(get=lambda k, d=None: d)
    app.event_bus = MagicMock()
    app.dialog_state = DialogState()
    app.assistant_context = AssistantContext()
    app.context_store = ContextStore(
        db_path=str(tmp_path / "friday.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    app.session_id = app.context_store.start_session({"source": "tests"})
    app.assistant_context.bind_context_store(app.context_store, app.session_id)
    app.router = CommandRouter(MagicMock())
    app.router.dialog_state = app.dialog_state
    app.router.assistant_context = app.assistant_context
    app.router.context_store = app.context_store
    app.router.session_id = app.session_id
    app.workflow_orchestrator = WorkflowOrchestrator(app)
    app.router.workflow_orchestrator = app.workflow_orchestrator
    app.memory_service = app.context_store
    app.emit_assistant_message = MagicMock()
    return app


def test_workflow_cancel_fires_bus(monkeypatch, tmp_path):
    """Saying "cancel" mid-workflow must emit a bus signal so DialogState
    pending-* fields reset alongside the workflow state.
    """
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    app = _build_app(tmp_path)
    TaskManagerPlugin(app)

    # Subscribe to the production singleton (the workflow orchestrator
    # imports it directly, so we can't pass a local instance).
    bus = get_interrupt_bus()
    received: list[InterruptSignal] = []
    unsubscribe = bus.subscribe("all", received.append)
    try:
        # Start a reminder workflow which will leave it active waiting on time.
        app.router.process_text("remind me to drink water")
        # Now cancel.
        result = app.router.process_text("cancel")
    finally:
        unsubscribe()

    assert "cancelled" in result.lower()
    # At least one of the captured signals must be the workflow_cancel emission.
    reasons = [sig.reason for sig in received]
    assert "workflow_cancel" in reasons
