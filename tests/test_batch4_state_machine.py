"""Tests for Batch 4 — Multi-turn state machines (Issues 4, 5, 6, 7, 10).

Covers:
* WorkingArtifact scope (Issue 10): explicit-scope holds against auto-scope
  overwrites; clear_artifact() removes the slot.
* Dictation post-save artifact (Issue 7): stop() populates the working
  artifact with the memo path so "read it" resolves correctly.
* File creation flow (Issue 4): write-confirmation prompt + yes-path
  transitions to dictate-or-generate; no-path exits cleanly; non-yes/no
  releases the workflow so fresh commands route normally.
* FileWorkflow target switch on new explicit filename (Issue 10).
* save_note routes when dictation end_dictation would have stolen it (Issue 6).
* Append no longer auto-generates from a topic-phrase (Issue 5).
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.assistant_context import AssistantContext
from core.context_store import ContextStore, WorkingArtifact
from core.dialog_state import DialogState
from core.router import CommandRouter
from core.workflow_orchestrator import FileWorkflow, WorkflowOrchestrator
import modules.task_manager.plugin as task_manager_plugin
from modules.task_manager.plugin import TaskManagerPlugin
from modules.system_control.plugin import SystemControlPlugin
from modules.dictation.service import DictationService


# ---------------------------------------------------------------------------
# WorkingArtifact scope (Issue 10)
# ---------------------------------------------------------------------------


def _store(tmp_path):
    return ContextStore(
        db_path=str(tmp_path / "ctx.db"),
        vector_path=str(tmp_path / "chroma"),
    )


class TestArtifactScope:
    def test_explicit_artifact_survives_auto_overwrite(self, tmp_path):
        store = _store(tmp_path)
        sid = store.start_session({"source": "tests"})

        store.save_artifact(sid, WorkingArtifact(
            content="memo body", source_path="/tmp/memo.md",
            capability_name="dictation", scope="explicit",
        ))
        # Auto-scope side effect tries to clobber the explicit pointer.
        store.save_artifact(sid, WorkingArtifact(
            content="rag chunk", source_path="/tmp/other.pdf",
            capability_name="document_intel", scope="auto",
        ))

        artifact = store.get_artifact(sid)
        assert artifact is not None
        assert artifact.scope == "explicit"
        assert artifact.source_path == "/tmp/memo.md"

    def test_explicit_replaces_explicit(self, tmp_path):
        store = _store(tmp_path)
        sid = store.start_session({"source": "tests"})

        store.save_artifact(sid, WorkingArtifact(
            content="first", source_path="/tmp/a.md", scope="explicit",
        ))
        store.save_artifact(sid, WorkingArtifact(
            content="second", source_path="/tmp/b.md", scope="explicit",
        ))
        artifact = store.get_artifact(sid)
        assert artifact.source_path == "/tmp/b.md"

    def test_clear_artifact_removes_slot(self, tmp_path):
        store = _store(tmp_path)
        sid = store.start_session({"source": "tests"})
        store.save_artifact(sid, WorkingArtifact(content="x", scope="explicit"))
        store.clear_artifact(sid)
        assert store.get_artifact(sid) is None

    def test_created_at_is_populated(self, tmp_path):
        store = _store(tmp_path)
        sid = store.start_session({"source": "tests"})
        store.save_artifact(sid, WorkingArtifact(content="x"))
        artifact = store.get_artifact(sid)
        assert artifact is not None
        assert artifact.created_at  # ISO timestamp set by save_artifact


# ---------------------------------------------------------------------------
# Dictation post-save artifact (Issue 7)
# ---------------------------------------------------------------------------


class TestDictationArtifact:
    def test_stop_publishes_explicit_artifact(self, tmp_path, monkeypatch):
        store = _store(tmp_path)
        sid = store.start_session({"source": "tests"})
        app = SimpleNamespace(
            session_id=sid,
            context_store=store,
            memory_service=store,
            dialog_state=DialogState(),
        )
        # Redirect DEFAULT_DIR to tmp_path so we don't touch ~/Documents.
        monkeypatch.setattr(DictationService, "DEFAULT_DIR", str(tmp_path / "memos"))
        svc = DictationService(app)
        ok, _ = svc.start(label="grocery list")
        assert ok
        svc.append("milk eggs bread")
        ok, message = svc.stop()
        assert ok
        artifact = store.get_artifact(sid)
        assert artifact is not None
        assert artifact.scope == "explicit"
        assert artifact.capability_name == "dictation"
        # source_path points at the just-saved memo.
        assert artifact.source_path.endswith(".md")
        assert os.path.exists(artifact.source_path)


# ---------------------------------------------------------------------------
# FileWorkflow new-filename detection (Issue 10)
# ---------------------------------------------------------------------------


class TestFileWorkflowTargetSwitch:
    def setup_method(self):
        self.wf = FileWorkflow(SimpleNamespace())

    def test_new_filename_in_save_that_releases_workflow(self):
        # Workflow has ideas.md as the active target; user names reverse.py.
        active_state = {
            "pending_slots": ["content"],
            "target": {"filename": "ideas.md", "path": "/tmp/ideas.md"},
        }
        assert self.wf.can_continue("save that to a file called reverse.py", active_state) is False

    def test_same_filename_keeps_workflow(self):
        active_state = {
            "pending_slots": ["content"],
            "target": {"filename": "ideas.md", "path": "/tmp/ideas.md"},
        }
        # Same file → workflow continues.
        assert self.wf.can_continue("save that to ideas.md", active_state) is True

    def test_no_filename_in_text_keeps_workflow(self):
        active_state = {
            "pending_slots": ["content"],
            "target": {"filename": "ideas.md", "path": "/tmp/ideas.md"},
        }
        # User says "save that" with no explicit name — continue normally.
        assert self.wf.can_continue("save that", active_state) is True


# ---------------------------------------------------------------------------
# End-to-end file creation flow (Issue 4)
# ---------------------------------------------------------------------------


def _build_full_app(tmp_path):
    event_bus = MagicMock()
    app = SimpleNamespace()
    class _Cfg:
        def get(self, key, default=None):
            return default
    app.config = _Cfg()
    app.event_bus = event_bus
    app.dialog_state = DialogState()
    app.assistant_context = AssistantContext()
    app.context_store = ContextStore(
        db_path=str(tmp_path / "friday.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    app.session_id = app.context_store.start_session({"source": "tests"})
    app.assistant_context.bind_context_store(app.context_store, app.session_id)
    app.router = CommandRouter(event_bus)
    app.router.dialog_state = app.dialog_state
    app.router.assistant_context = app.assistant_context
    app.router.context_store = app.context_store
    app.router.session_id = app.session_id
    app.workflow_orchestrator = WorkflowOrchestrator(app)
    app.router.workflow_orchestrator = app.workflow_orchestrator
    app.emit_assistant_message = MagicMock()
    return app


class TestCreateFlow:
    def test_create_prompts_for_write_then_no_exits(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "Desktop").mkdir()
        app = _build_full_app(tmp_path)
        SystemControlPlugin(app)

        created = app.router.process_text("create a file named notes.md")
        assert "Would you like me to write anything in it?" in created

        done = app.router.process_text("no")
        assert "Okay" in done
        # Workflow cleared.
        active = app.context_store.get_active_workflow(app.session_id, workflow_name="file_workflow")
        assert not active

    def test_create_then_yes_prompts_for_dictate_or_generate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "Desktop").mkdir()
        app = _build_full_app(tmp_path)
        SystemControlPlugin(app)

        app.router.process_text("create a file named notes.md")
        choice_prompt = app.router.process_text("yes")
        assert "dictate" in choice_prompt.lower() and "generate" in choice_prompt.lower()
        state = app.context_store.get_active_workflow(app.session_id, workflow_name="file_workflow")
        assert state["pending_slots"] == ["content_source"]

    def test_generate_branch_asks_for_topic(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "Desktop").mkdir()
        app = _build_full_app(tmp_path)
        SystemControlPlugin(app)

        app.router.process_text("create a file named notes.md")
        app.router.process_text("yes")
        topic_prompt = app.router.process_text("generate")
        assert "topic" in topic_prompt.lower()

    def test_create_then_fresh_command_releases_workflow(self, tmp_path, monkeypatch):
        # Issue 4 release rule: a non-yes/no reply after the write-
        # confirmation prompt drops the workflow so the new command can
        # route normally — without it, "what time is it?" would be stuck
        # echoing the yes/no prompt.
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / "Desktop").mkdir()
        app = _build_full_app(tmp_path)
        SystemControlPlugin(app)
        TaskManagerPlugin(app)
        monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "tm.db"))

        app.router.process_text("create a file named notes.md")
        reply = app.router.process_text("what time is it")
        # Should be a time response, not the yes/no prompt.
        assert "would you like me to write" not in reply.lower()


# ---------------------------------------------------------------------------
# Append behavior (Issue 5)
# ---------------------------------------------------------------------------


class TestAppendLiteral:
    def test_append_short_phrase_writes_literal(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        desktop = tmp_path / "Desktop"
        desktop.mkdir()
        app = _build_full_app(tmp_path)
        SystemControlPlugin(app)

        # Set up a file first.
        target = desktop / "scratch.md"
        target.write_text("first line\n", encoding="utf-8")
        app.dialog_state.remember_file(str(target))

        result = app.router.process_text("append second line to scratch.md")
        # Should not generate an article about "second line"; the literal
        # "second line" must be present in the file.
        contents = target.read_text(encoding="utf-8")
        assert "second line" in contents.lower()
        # And the file is much shorter than a generated article would be
        # (the old heuristic produced 200+ words).
        assert len(contents.split()) < 30


# ---------------------------------------------------------------------------
# save_note routing under dictation cross-talk (Issue 6)
# ---------------------------------------------------------------------------


class TestSaveNoteFallback:
    def test_end_dictation_with_no_session_redirects_save_note(self, tmp_path, monkeypatch):
        from modules.dictation.plugin import DictationPlugin
        monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "tm.db"))
        app = _build_full_app(tmp_path)
        TaskManagerPlugin(app)
        DictationPlugin(app)
        # No active dictation; user says "save note: milk and eggs".
        plugin = app.dictation_service  # type: ignore[attr-defined]
        assert not plugin.is_active()
        # Look up the end_dictation handler and call it directly with a
        # save-note phrasing — used to surface "I'm not in a dictation
        # session right now"; now it redirects to save_note.
        end_handler = app.router._tools_by_name["end_dictation"]["callback"]
        reply = end_handler("save note: milk and eggs", {})
        assert "i'm not in a dictation session" not in reply.lower()
        assert "milk and eggs" in reply.lower() or "saved" in reply.lower()
