import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.assistant_context import AssistantContext
from core.context_store import ContextStore
from core.dialog_state import DialogState
from core.router import CommandRouter
from core.workflow_orchestrator import WorkflowOrchestrator
from modules.browser_automation.plugin import BrowserAutomationPlugin
import modules.system_control.file_workspace as file_workspace
from modules.system_control.plugin import SystemControlPlugin


class DummyConfig:
    def get(self, key, default=None):
        values = {
            "browser_automation.enabled": True,
            "browser_automation.allow_online": True,
        }
        return values.get(key, default)


def build_test_app(tmp_path):
    event_bus = MagicMock()
    app = SimpleNamespace()
    app.config = DummyConfig()
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


def test_create_file_continues_with_filename_follow_up(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    first = app.router.process_text("create a file")
    second = app.router.process_text("coffee")

    assert first == "What should I name the file?"
    assert second == "Created coffee."
    assert (desktop / "coffee").exists()
    state = app.context_store.get_active_workflow(app.session_id, workflow_name="file_workflow")
    assert state["target"]["filename"] == "coffee"
    assert state["status"] == "active"


def test_write_request_without_content_prompts_and_then_saves(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    assert app.router.process_text("create a file named coffee") == "Created coffee."
    prompt = app.router.process_text("write some content into the coffee file")
    saved = app.router.process_text("Arabica and Robusta are common coffee types.")

    assert prompt == "What would you like me to write in coffee?"
    assert saved == "Saved coffee."
    assert (desktop / "coffee").read_text(encoding="utf-8") == "Arabica and Robusta are common coffee types."


def test_save_that_uses_latest_assistant_response_for_active_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    assert app.router.process_text("create a file named coffee") == "Created coffee."
    app.assistant_context.record_message("assistant", "Espresso, drip coffee, and cold brew.")

    saved = app.router.process_text("save that")

    assert saved == "Saved coffee."
    assert (desktop / "coffee").read_text(encoding="utf-8") == "Espresso, drip coffee, and cold brew."


def test_browser_workflow_routes_open_and_pause(monkeypatch, tmp_path):
    app = build_test_app(tmp_path)
    BrowserAutomationPlugin(app)
    plugin = next(
        route["callback"].__self__
        for route in app.router.tools
        if route["spec"]["name"] == "open_browser_url"
    )
    plugin.service.open_browser_url = lambda url, browser_name="chrome", platform="browser": (
        f"Opening {platform.replace('_', ' ')} in {browser_name}."
    )
    plugin.service.browser_media_control = lambda action, platform=None, query="": (
        f"{action}:{platform or 'youtube'}"
    )

    opened = app.router.process_text("open youtube in chrome")
    paused = app.router.process_text("pause")

    assert opened == "Opening youtube in chrome."
    assert paused == "pause:youtube"


def test_browser_workflow_reuses_query_for_youtube_music_switch(monkeypatch, tmp_path):
    app = build_test_app(tmp_path)
    BrowserAutomationPlugin(app)
    plugin = next(
        route["callback"].__self__
        for route in app.router.tools
        if route["spec"]["name"] == "play_youtube_music"
    )
    plugin.service.play_youtube_music = lambda query, browser_name="chrome": (
        f"Playing {query} on youtube music in {browser_name}."
    )
    plugin.service.play_youtube = lambda query, browser_name="chrome": (
        f"Playing {query} on youtube in {browser_name}."
    )

    music = app.router.process_text("play sahiba in youtube music")
    switched = app.router.process_text("play it in youtube instead")

    assert music == "Playing sahiba on youtube music in chrome."
    assert switched == "Playing sahiba on youtube in chrome."


def test_browser_intent_parses_open_youtube_and_play_query(tmp_path):
    app = build_test_app(tmp_path)
    BrowserAutomationPlugin(app)

    plan = app.router.intent_recognizer.plan("open youtube and play sahiba", context={})

    assert [action["tool"] for action in plan] == ["play_youtube"]
    assert plan[0]["args"]["query"] == "sahiba"


def test_browser_intent_parses_play_on_youtube_variants(tmp_path):
    app = build_test_app(tmp_path)
    BrowserAutomationPlugin(app)

    youtube_plan = app.router.intent_recognizer.plan("play sahiba on youtube", context={})
    music_plan = app.router.intent_recognizer.plan("play sahiba on youtube music", context={})
    bare_music_plan = app.router.intent_recognizer.plan("play sahiba song", context={})

    assert [action["tool"] for action in youtube_plan] == ["play_youtube"]
    assert [action["tool"] for action in music_plan] == ["play_youtube_music"]
    assert [action["tool"] for action in bare_music_plan] == ["play_youtube_music"]
    assert bare_music_plan[0]["args"]["query"] == "sahiba song"


def test_context_store_provides_recall_without_overwriting_active_workflow(tmp_path):
    store = ContextStore(
        db_path=str(tmp_path / "friday.db"),
        vector_path=str(tmp_path / "chroma"),
    )
    session_id = store.start_session({"source": "tests"})
    store.append_turn(session_id, "assistant", "Arabica is smooth and balanced.", source="assistant")
    store.save_workflow_state(
        session_id,
        "file_workflow",
        {
            "status": "pending",
            "pending_slots": ["filename"],
            "last_action": "create",
            "target": {},
            "result_summary": "Waiting for a file name.",
        },
    )

    recall = store.semantic_recall("arabica", session_id, limit=2)
    active = store.get_active_workflow(session_id, workflow_name="file_workflow")

    assert recall
    assert active["pending_slots"] == ["filename"]
    assert active["last_action"] == "create"


def test_open_named_active_file_prefers_file_over_app(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    assert app.router.process_text("create a file named coffee") == "Created coffee."
    response = app.router.process_text("open coffee")

    assert response == "Opening coffee..."


def test_open_file_and_read_it_out_splits_into_file_actions(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    target = desktop / "coffee"
    target.write_text("Arabica", encoding="utf-8")
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    response = app.router.process_text("open the file coffee and read it out")

    assert "Opening coffee..." in response
    assert "Arabica" in response


def test_open_the_coffee_file_and_read_it_splits_into_file_actions(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    target = desktop / "coffee"
    target.write_text("Arabica", encoding="utf-8")
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    response = app.router.process_text("open the coffee file and read it")

    assert "Opening coffee..." in response
    assert "Arabica" in response


def test_file_context_recovers_filename_like_follow_up(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    (desktop / "coffee.txt").write_text("Arabica", encoding="utf-8")
    target = desktop / "design build final report.txt"
    target.write_text("Report body", encoding="utf-8")
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    monkeypatch.setattr(file_workspace, "open_file", lambda path: f"Opening {os.path.basename(path)}...")

    first = app.router.process_text("open the file coffee")
    second = app.router.process_text("file design build final report")

    assert first == "Opening coffee.txt..."
    assert "design build final report.txt" in second
    assert "Would you like me to open" in second


def test_confirm_yes_replays_pending_clarification_action(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    target = desktop / "design build final report.txt"
    target.write_text("Report body", encoding="utf-8")
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    app.dialog_state.set_pending_clarification("find the file design build final report")

    response = app.router.process_text("yes")

    assert "design build final report.txt" in response
    assert not app.dialog_state.has_pending_clarification()


def test_confirm_no_clears_pending_clarification(tmp_path):
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)
    app.dialog_state.set_pending_clarification(
        "find the file design build final report",
        cancel_message="Okay. Please say it again in a different way.",
    )

    response = app.router.process_text("no")

    assert response == "Okay. Please say it again in a different way."
    assert not app.dialog_state.has_pending_clarification()


def test_unrelated_command_clears_pending_clarification(monkeypatch, tmp_path):
    app = build_test_app(tmp_path)
    BrowserAutomationPlugin(app)
    SystemControlPlugin(app)
    app.dialog_state.set_pending_clarification("find the file design build final report")

    plugin = next(
        route["callback"].__self__
        for route in app.router.tools
        if route["spec"]["name"] == "open_browser_url"
    )
    plugin.service.open_browser_url = lambda url, browser_name="chrome", platform="browser": (
        f"Opening {platform.replace('_', ' ')} in {browser_name}."
    )

    response = app.router.process_text("open youtube in chrome")

    assert response == "Opening youtube in chrome."
    assert not app.dialog_state.has_pending_clarification()


def test_browser_open_falls_back_when_playwright_driver_is_unavailable(tmp_path):
    app = build_test_app(tmp_path)
    BrowserAutomationPlugin(app)
    plugin = next(
        route["callback"].__self__
        for route in app.router.tools
        if route["spec"]["name"] == "open_browser_url"
    )

    plugin.service._get_page = lambda **kwargs: (
        "Browser automation is installed but the Playwright driver is not set up correctly."
    )
    plugin.service._resolve_browser_path = lambda browser_name: "/usr/bin/google-chrome"

    import subprocess

    original_popen = subprocess.Popen
    subprocess.Popen = lambda *args, **kwargs: SimpleNamespace()
    try:
        response = app.router.process_text("open youtube in chrome")
    finally:
        subprocess.Popen = original_popen

    assert response == "Opening youtube in chrome. Browser automation is unavailable, so I opened the page directly."


def test_browser_play_falls_back_to_search_results_when_playwright_is_unavailable(tmp_path):
    app = build_test_app(tmp_path)
    BrowserAutomationPlugin(app)
    plugin = next(
        route["callback"].__self__
        for route in app.router.tools
        if route["spec"]["name"] == "play_youtube_music"
    )

    plugin.service._get_page = lambda **kwargs: (
        "Browser automation is installed but the Playwright driver is not set up correctly."
    )
    plugin.service._resolve_browser_path = lambda browser_name: "/usr/bin/google-chrome"

    import subprocess

    original_popen = subprocess.Popen
    subprocess.Popen = lambda *args, **kwargs: SimpleNamespace()
    try:
        response = app.router.process_text("play sahiba song in youtube music")
    finally:
        subprocess.Popen = original_popen

    assert response == (
        "Opening search results for sahiba song on youtube music. "
        "Browser automation is unavailable, so I opened the page directly."
    )
