"""Tests for first-run onboarding flow and update_user_profile capability.

Covers:
  - Five-step happy path (name → role → location → preferences → comm_style)
  - "skip" answers record empty strings and advance the workflow
  - Workflow-level cancel mid-flow clears state cleanly
  - update_user_profile capability writes the correct namespace and field
  - read_profile / is_completed helpers behave correctly
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.assistant_context import AssistantContext
from core.context_store import ContextStore
from core.dialog_state import DialogState
from core.workflow_orchestrator import WorkflowOrchestrator
from modules.onboarding.extension import (
    PROFILE_FIELDS,
    PROFILE_NAMESPACE,
    OnboardingExtension,
    is_completed,
    read_profile,
    write_profile_field,
)
from modules.onboarding.workflow import (
    WORKFLOW_NAME,
    OnboardingWorkflow,
    first_question,
    initial_state,
)


def build_test_app(tmp_path):
    app = SimpleNamespace()
    app.event_bus = MagicMock()
    app.dialog_state = DialogState()
    app.assistant_context = AssistantContext()
    app.context_store = ContextStore(
        db_path=str(tmp_path / "friday.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    app.session_id = app.context_store.start_session({"source": "onboarding-tests"})
    app.assistant_context.bind_context_store(app.context_store, app.session_id)
    # Workflow orchestrator looks for `memory_service` first; for unit tests we
    # let it fall back to the raw ContextStore.
    app.memory_service = None
    app.workflow_orchestrator = WorkflowOrchestrator(app)
    return app


def _seed_initial_workflow(app):
    app.context_store.save_workflow_state(app.session_id, WORKFLOW_NAME, initial_state())


def _run_continue(app, user_text: str):
    return app.workflow_orchestrator.continue_active(user_text, app.session_id)


# ----------------------------------------------------------------------
# Workflow happy path
# ----------------------------------------------------------------------

def test_first_question_is_name_prompt():
    assert "what should i call you" in first_question().lower()


def test_onboarding_workflow_is_registered(tmp_path):
    app = build_test_app(tmp_path)
    assert WORKFLOW_NAME in app.workflow_orchestrator.workflows
    wf = app.workflow_orchestrator.workflows[WORKFLOW_NAME]
    assert isinstance(wf, OnboardingWorkflow)


def test_happy_path_captures_all_five_fields(tmp_path):
    app = build_test_app(tmp_path)
    _seed_initial_workflow(app)

    # Step 1: name
    r1 = _run_continue(app, "Tricky")
    assert r1.handled
    assert "what do you do" in r1.response.lower()
    assert "tricky" in r1.response.lower()

    # Step 2: role
    r2 = _run_continue(app, "I'm building a personal AI assistant")
    assert r2.handled
    assert "where are you based" in r2.response.lower()

    # Step 3: location
    r3 = _run_continue(app, "Mumbai")
    assert r3.handled
    assert "tools or topics" in r3.response.lower()

    # Step 4: preferences
    r4 = _run_continue(app, "Python and local LLMs")
    assert r4.handled
    assert "talk to you" in r4.response.lower()

    # Step 5: comm_style — final
    r5 = _run_continue(app, "Concise")
    assert r5.handled
    assert "tricky" in r5.response.lower()
    assert "glad to meet you" in r5.response.lower()

    # Workflow state was cleared, profile facts written, completion marked.
    assert app.context_store.get_active_workflow(app.session_id, workflow_name=WORKFLOW_NAME) in (None, {})
    profile = read_profile(app.context_store)
    assert profile["name"] == "Tricky"
    assert profile["role"].lower().startswith("i'm building")
    assert profile["location"] == "Mumbai"
    assert profile["preferences"] == "Python and local LLMs"
    assert profile["comm_style"] == "Concise"
    assert is_completed(app.context_store) is True


def test_skip_answers_record_empty_and_advance(tmp_path):
    app = build_test_app(tmp_path)
    _seed_initial_workflow(app)

    r1 = _run_continue(app, "skip")
    assert r1.handled
    # Even with empty name, advances to role question
    assert "what do you do" in r1.response.lower()

    # Skip everything else too
    _run_continue(app, "later")    # role
    _run_continue(app, "no")       # location
    _run_continue(app, "skip")     # preferences
    final = _run_continue(app, "skip")  # comm_style → final

    assert final.handled
    # Without a name, completion message falls back to no-name variant
    assert "glad to meet you" in final.response.lower()

    profile = read_profile(app.context_store)
    # Skipped answers are not surfaced (read_profile filters empty)
    assert profile == {}
    # But onboarding is still marked complete so we don't re-prompt
    assert is_completed(app.context_store) is True


def test_workflow_cancel_clears_state_and_exits(tmp_path):
    app = build_test_app(tmp_path)
    _seed_initial_workflow(app)

    # Answer first question normally
    _run_continue(app, "Tricky")

    # Now cancel mid-workflow — orchestrator should handle this and clear state.
    cancel_result = _run_continue(app, "cancel")
    assert cancel_result.handled
    assert "cancel" in cancel_result.response.lower()
    assert app.context_store.get_active_workflow(app.session_id, workflow_name=WORKFLOW_NAME) in (None, {})

    # The name we captured before cancelling stays persisted.
    profile = read_profile(app.context_store)
    assert profile.get("name") == "Tricky"


def test_extract_name_from_phrases(tmp_path):
    app = build_test_app(tmp_path)
    _seed_initial_workflow(app)

    r = _run_continue(app, "My name is Cody Reddy")
    assert r.handled
    profile = read_profile(app.context_store)
    assert profile["name"] == "Cody Reddy"


# ----------------------------------------------------------------------
# update_user_profile capability
# ----------------------------------------------------------------------

class _StubCtx:
    """Minimal ExtensionContext stand-in for handler unit tests."""
    def __init__(self, store):
        self._store = store
        self.registry = MagicMock()
        self.events = MagicMock()
        self.consent = MagicMock()

    def get_service(self, name):
        return self._store if name == "context_store" else None

    def register_capability(self, *args, **kwargs):
        pass


def test_update_user_profile_writes_correct_namespace(tmp_path):
    store = ContextStore(
        db_path=str(tmp_path / "f.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    store.start_session({"source": "tests"})
    ext = OnboardingExtension()
    ext.load(_StubCtx(store))

    ack = ext._handle_update_profile("", {"field": "name", "value": "Cody"})
    assert "cody" in ack.lower()
    assert read_profile(store)["name"] == "Cody"

    ack2 = ext._handle_update_profile("", {"field": "location", "value": "Mumbai"})
    assert "mumbai" in ack2.lower()
    assert read_profile(store)["location"] == "Mumbai"


def test_update_user_profile_rejects_unknown_field(tmp_path):
    store = ContextStore(
        db_path=str(tmp_path / "f.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    store.start_session({"source": "tests"})
    ext = OnboardingExtension()
    ext.load(_StubCtx(store))

    ack = ext._handle_update_profile("", {"field": "favourite_color", "value": "blue"})
    assert "only remember" in ack.lower() or "which one" in ack.lower()
    # Nothing was written.
    assert read_profile(store) == {}


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def test_write_profile_field_ignores_unknown_field(tmp_path):
    store = ContextStore(
        db_path=str(tmp_path / "f.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    store.start_session({"source": "tests"})
    write_profile_field(store, "not_a_field", "nope")
    assert read_profile(store) == {}


def test_profile_fields_constant_matches_workflow_steps():
    from modules.onboarding.workflow import _STEPS
    assert tuple(_STEPS) == PROFILE_FIELDS
