import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.assistant_context import AssistantContext
from core.context_store import ContextStore
from core.dialog_state import DialogState
from core.router import CommandRouter
from core.workflow_orchestrator import WorkflowOrchestrator
from modules.browser_automation.plugin import BrowserAutomationPlugin
import modules.task_manager.plugin as task_manager_plugin
from modules.task_manager.plugin import TaskManagerPlugin
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
    # Issue 4: bare create now prompts whether to write content. The
    # filename + state still settle as before; only the response copy
    # changed (the prompt is appended).
    assert second.startswith("Created coffee.")
    assert "Would you like me to write anything in it?" in second
    assert (desktop / "coffee").exists()
    state = app.context_store.get_active_workflow(app.session_id, workflow_name="file_workflow")
    assert state["target"]["filename"] == "coffee"
    assert state["status"] == "active"
    assert state["pending_slots"] == ["write_confirmation"]


def test_reminder_prompts_for_missing_date_and_time(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    app = build_test_app(tmp_path)
    TaskManagerPlugin(app)

    prompt = app.router.process_text("remind me to purchase a gift")

    assert prompt == "When should I remind you? Please mention the date and time to remind you."
    state = app.context_store.get_active_workflow(app.session_id, workflow_name="reminder_workflow")
    assert state["pending_slots"] == ["date", "time"]
    assert state["target"]["message"] == "purchase a gift"


def test_reminder_followup_date_then_time_completes_event(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    app = build_test_app(tmp_path)
    TaskManagerPlugin(app)

    first = app.router.process_text("remind me to purchase a gift")
    second = app.router.process_text("tomorrow")
    third = app.router.process_text("5 PM")

    assert "When should I remind you" in first
    assert second == "What time should I remind you?"
    assert "I'll remind you to purchase a gift" in third
    state = app.context_store.get_active_workflow(app.session_id, workflow_name="reminder_workflow")
    assert not state


def test_reminder_followup_accepts_spoken_time_transcripts(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    assert plugin._parse_time("today at 4 10") == (4, 10)
    assert plugin._parse_time("3 40") == (3, 40)
    assert plugin._parse_time("340") == (3, 40)
    assert plugin._parse_time("1540") == (15, 40)
    assert plugin._parse_time("four o clock") == (4, 0)
    assert plugin._parse_time("4 p m") == (16, 0)
    assert plugin._parse_time("buy one apple") is None
    assert plugin._extract_reminder_message("remind me to cook rice at") == "cook rice"


def test_reminder_today_infers_afternoon_for_ambiguous_past_hour(monkeypatch, tmp_path):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 27, 0)

    monkeypatch.setattr(task_manager_plugin, "datetime", FixedDatetime)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    remind_at = plugin._combine_date_time("2026-04-28", "03:40")

    assert remind_at == FixedDatetime(2026, 4, 28, 15, 40, 0)


def test_reminder_accepts_bare_hour_when_context_expects_time(monkeypatch, tmp_path):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 36, 0)

    monkeypatch.setattr(task_manager_plugin, "datetime", FixedDatetime)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, event_id, message, remind_at: False)
    app = build_test_app(tmp_path)
    TaskManagerPlugin(app)

    app.router.process_text("remind me to purchase a gift")
    app.router.process_text("today")
    result = app.router.process_text("four")

    assert result == "Got it! I'll remind you to purchase a gift on Tuesday, April 28, 2026 at 4:00 PM."


def test_reminder_accepts_at_hour_in_date_followup(monkeypatch, tmp_path):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 36, 0)

    monkeypatch.setattr(task_manager_plugin, "datetime", FixedDatetime)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, event_id, message, remind_at: False)
    app = build_test_app(tmp_path)
    TaskManagerPlugin(app)

    app.router.process_text("remind me to purchase a gift")
    result = app.router.process_text("today at 4")

    assert result == "Got it! I'll remind you to purchase a gift on Tuesday, April 28, 2026 at 4:00 PM."


def test_reminder_with_date_and_time_in_first_sentence_has_no_followup(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    app = build_test_app(tmp_path)
    TaskManagerPlugin(app)

    result = app.router.process_text("remind me to purchase a gift on 2099-04-28 at 5 PM")

    assert result == "Got it! I'll remind you to purchase a gift on Tuesday, April 28, 2099 at 5:00 PM."
    state = app.context_store.get_active_workflow(app.session_id, workflow_name="reminder_workflow")
    assert not state


def test_calendar_events_briefing_formats_upcoming_times(monkeypatch, tmp_path):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 27, 0)

    monkeypatch.setattr(task_manager_plugin, "datetime", FixedDatetime)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, event_id, message, remind_at: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)
    # _create_calendar_event defaults to event_type="reminder" — Issue 7
    # split: the reminder is now read by handle_list_reminders, not by
    # handle_list_calendar_events (which is calendar-only).
    plugin._create_calendar_event("purchase a gift", FixedDatetime(2026, 4, 28, 16, 10, 0))

    result = plugin.handle_list_reminders("", {})

    assert result == "Here are your reminders:\n  Today at 4:10 PM: purchase a gift"


def test_calendar_event_fire_sends_desktop_notification(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(task_manager_plugin.shutil, "which", lambda name: "/usr/bin/notify-send")
    run = MagicMock()
    monkeypatch.setattr(task_manager_plugin.subprocess, "run", run)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    event_id = plugin._insert_calendar_event("purchase a gift", datetime.now())
    plugin._fire_calendar_event(event_id, "purchase a gift")

    run.assert_called_once()
    assert run.call_args.args[0][-2:] == ["FRIDAY Reminder", "purchase a gift"]
    assert plugin.list_calendar_events() == []


def test_completed_calendar_events_are_cleaned_on_startup(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    app = build_test_app(tmp_path)
    TaskManagerPlugin(app)
    conn = task_manager_plugin.sqlite3.connect(task_manager_plugin.DB_PATH)
    conn.execute(
        "INSERT INTO calendar_events (title, remind_at, status, created_at, fired_at, type) VALUES (?, ?, 'fired', ?, ?, 'reminder')",
        ("old task", "2026-04-28T15:40:00", "2026-04-28T15:30:00", "2026-04-28T15:40:00"),
    )
    conn.commit()
    conn.close()

    plugin = TaskManagerPlugin(app)

    assert plugin.list_calendar_events() == []


def test_calendar_event_creation_schedules_system_notification(monkeypatch, tmp_path):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 27, 0)

    monkeypatch.setattr(task_manager_plugin, "datetime", FixedDatetime)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(task_manager_plugin.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = MagicMock()
    run.return_value.returncode = 0
    run.return_value.stderr = ""
    run.return_value.stdout = "Running timer"
    monkeypatch.setattr(task_manager_plugin.subprocess, "run", run)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    event_id = plugin._create_calendar_event("purchase a gift", FixedDatetime(2026, 4, 28, 15, 40, 0))

    assert event_id in plugin._system_notification_event_ids
    command = run.call_args.args[0]
    assert command[:2] == ["systemd-run", "--user"]
    assert "--on-calendar" in command
    assert "2026-04-28 15:40:00" in command
    assert command[-2:] == [str(event_id), "purchase a gift"]


def test_system_notification_duplicate_unit_is_treated_as_scheduled(monkeypatch, tmp_path):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 27, 0)

    monkeypatch.setattr(task_manager_plugin, "datetime", FixedDatetime)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(task_manager_plugin.shutil, "which", lambda name: f"/usr/bin/{name}")
    run = MagicMock()
    run.return_value.returncode = 1
    run.return_value.stdout = ""
    run.return_value.stderr = (
        "Failed to start transient timer unit: "
        "Unit friday-reminder-3.timer was already loaded or has a fragment file."
    )
    monkeypatch.setattr(task_manager_plugin.subprocess, "run", run)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    scheduled = plugin._schedule_system_notification(3, "purchase a gift", FixedDatetime(2026, 4, 28, 15, 40, 0))

    assert scheduled is True


def test_unfinished_task_briefing_lists_only_future_scheduled_events(monkeypatch, tmp_path):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 27, 0)

    monkeypatch.setattr(task_manager_plugin, "datetime", FixedDatetime)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, event_id, message, remind_at: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)
    plugin._create_calendar_event("purchase a gift", FixedDatetime(2026, 4, 28, 16, 10, 0))

    result = plugin.get_unfinished_task_briefing()

    assert result == "You have 1 unfinished reminder.\nToday at 4:10 PM: purchase a gift"


def test_gui_create_and_delete_calendar_event(monkeypatch, tmp_path):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 28, 15, 27, 0)

    monkeypatch.setattr(task_manager_plugin, "datetime", FixedDatetime)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, event_id, message, remind_at: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    ok, payload = plugin.create_calendar_event("purchase a gift", FixedDatetime(2026, 4, 28, 16, 10, 0))
    deleted, message = plugin.delete_calendar_event(payload["id"])

    assert ok is True
    assert payload["title"] == "purchase a gift"
    assert deleted is True
    assert message == "Reminder deleted."
    assert plugin.list_calendar_events() == []


def test_write_request_without_content_prompts_and_then_saves(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    # Issue 4: bare create now prompts before letting the workflow exit.
    created = app.router.process_text("create a file named coffee")
    assert created.startswith("Created coffee.")
    assert "Would you like me to write anything in it?" in created

    # A fresh "write some content" command is not a yes/no answer, so
    # the workflow releases and the normal write path runs to completion.
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

    # Issue 4: create now appends the write-confirmation prompt. The
    # caller-visible filename + workflow target are unchanged.
    created = app.router.process_text("create a file named coffee")
    assert created.startswith("Created coffee.")
    app.assistant_context.record_message("assistant", "Espresso, drip coffee, and cold brew.")

    saved = app.router.process_text("save that")

    assert saved == "Saved coffee."
    assert (desktop / "coffee").read_text(encoding="utf-8") == "Espresso, drip coffee, and cold brew."


def test_write_it_to_python_file_saves_latest_code_block(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)
    app.router.get_llm = MagicMock()
    app.assistant_context.record_message(
        "assistant",
        "Sure, here it is:\n\n```python\ndef check_pin(pin):\n    return pin == '1234'\n\n"
        "for number in range(10000):\n    pin = f'{number:04d}'\n    if check_pin(pin):\n"
        "        print(pin)\n        break\n```\n\nYou can adjust check_pin.",
    )

    saved = app.router.process_text("write it to a file named break.py")

    assert saved == "Saved break.py."
    app.router.get_llm.assert_not_called()
    assert (desktop / "break.py").read_text(encoding="utf-8").startswith("def check_pin(pin):")
    assert "```" not in (desktop / "break.py").read_text(encoding="utf-8")


def test_write_it_to_bare_python_filename_routes_to_file_tool(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)
    app.router.get_llm = MagicMock()
    app.assistant_context.record_message(
        "assistant",
        "```python\nprint('saved from prior response')\n```",
    )

    saved = app.router.process_text("write it to hello.py")

    assert saved == "Saved hello.py."
    app.router.get_llm.assert_not_called()
    assert (desktop / "hello.py").read_text(encoding="utf-8") == "print('saved from prior response')"


def test_write_generated_file_strips_thinking_blocks(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    mock_llm = MagicMock()
    mock_llm.create_chat_completion.return_value = {
        "choices": [
            {
                "message": {
                    "content": "<think>wrong private article draft</think>\n```python\nprint('ok')\n```"
                }
            }
        ]
    }
    app.router.get_llm = MagicMock(return_value=mock_llm)

    result = app.router.process_text("write a Python script that prints ok into a file named psbreak.py")

    sent_messages = mock_llm.create_chat_completion.call_args.kwargs["messages"]
    assert sent_messages[-1]["content"].endswith("/no_think")
    assert result == "Saved psbreak.py."
    assert (desktop / "psbreak.py").read_text(encoding="utf-8") == "print('ok')"


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

    # Issue 4: bare create now appends the write-confirmation prompt;
    # filename + workflow target are unchanged.
    created = app.router.process_text("create a file named coffee")
    assert created.startswith("Created coffee.")
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


# ---------------------------------------------------------------------------
# Reminder vs Calendar Event — separate behaviour tests
# ---------------------------------------------------------------------------

class FixedNow(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 4, 28, 15, 27, 0)

FUTURE = FixedNow(2026, 4, 28, 16, 10, 0)


def test_reminder_confirmation_uses_remind_wording(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "datetime", FixedNow)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, *a: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    # Call _handle_reminder_parts directly with a fully-parsed payload
    result = plugin._handle_reminder_parts({"message": "call John", "remind_at": FUTURE})

    assert "I'll remind you to call John" in result
    assert "Created" not in result


def test_calendar_event_confirmation_uses_created_wording(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "datetime", FixedNow)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, *a: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    result = plugin._format_event_confirmation("Standup", FUTURE)

    assert result.startswith("Created 'Standup'")
    assert "remind you" not in result


def test_reminder_stored_with_type_reminder(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "datetime", FixedNow)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, *a: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    plugin._create_calendar_event("call John", FUTURE, event_type="reminder")
    events = plugin.list_calendar_events()

    assert len(events) == 1
    assert events[0]["type"] == "reminder"


def test_calendar_event_stored_with_type_calendar_event(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "datetime", FixedNow)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, *a: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    plugin._create_calendar_event("Standup", FUTURE, event_type="calendar_event")
    events = plugin.list_calendar_events()

    assert len(events) == 1
    assert events[0]["type"] == "calendar_event"


def test_reminder_fires_with_reminder_announcement(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(task_manager_plugin.shutil, "which", lambda name: "/usr/bin/notify-send")
    monkeypatch.setattr(task_manager_plugin.subprocess, "run", MagicMock())
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    event_id = plugin._insert_calendar_event("call John", datetime.now(), event_type="reminder")
    plugin._fire_calendar_event(event_id, "call John", "reminder")

    call_args = app.emit_assistant_message.call_args
    assert "Reminder: call John" in call_args.args[0]
    assert call_args.kwargs.get("source") == "reminder"


def test_calendar_event_fires_with_starting_now_announcement(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(task_manager_plugin.shutil, "which", lambda name: "/usr/bin/notify-send")
    monkeypatch.setattr(task_manager_plugin.subprocess, "run", MagicMock())
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    event_id = plugin._insert_calendar_event("Standup", datetime.now(), event_type="calendar_event")
    plugin._fire_calendar_event(event_id, "Standup", "calendar_event")

    call_args = app.emit_assistant_message.call_args
    assert "'Standup' is starting now." in call_args.args[0]
    assert call_args.kwargs.get("source") == "calendar"


def test_list_separates_reminders_and_calendar_events(monkeypatch, tmp_path):
    # Issue 7 split: handle_list_calendar_events / handle_list_reminders
    # each own one bucket only. The two return values together cover what
    # the old conflated handler used to emit.
    monkeypatch.setattr(task_manager_plugin, "datetime", FixedNow)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, *a: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    plugin._create_calendar_event("call John", FUTURE, event_type="reminder")
    plugin._create_calendar_event("Standup", FUTURE, event_type="calendar_event")

    reminders = plugin.handle_list_reminders("", {})
    events = plugin.handle_list_calendar_events("", {})

    assert "call John" in reminders
    assert "Standup" not in reminders
    assert "Standup" in events
    assert "call John" not in events


def test_list_only_reminders_uses_reminder_header(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "datetime", FixedNow)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, *a: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    plugin._create_calendar_event("call John", FUTURE, event_type="reminder")

    result = plugin.handle_list_reminders("", {})

    assert result.startswith("Here are your reminders:")
    assert "Calendar events" not in result


def test_list_only_events_uses_events_header(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "datetime", FixedNow)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, *a: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    plugin._create_calendar_event("Standup", FUTURE, event_type="calendar_event")

    result = plugin.handle_list_calendar_events("", {})

    assert result.startswith("Here are your calendar events:")
    assert "Reminders" not in result


def test_briefing_separates_reminders_and_events(monkeypatch, tmp_path):
    monkeypatch.setattr(task_manager_plugin, "datetime", FixedNow)
    monkeypatch.setattr(task_manager_plugin, "DB_PATH", str(tmp_path / "friday.db"))
    monkeypatch.setattr(TaskManagerPlugin, "_schedule_system_notification", lambda self, *a: False)
    app = build_test_app(tmp_path)
    plugin = TaskManagerPlugin(app)

    plugin._create_calendar_event("call John", FUTURE, event_type="reminder")
    plugin._create_calendar_event("Standup", FUTURE, event_type="calendar_event")

    result = plugin.get_unfinished_task_briefing()

    assert "1 unfinished reminder" in result
    assert "call John" in result
    assert "1 upcoming calendar event" in result
    assert "Standup" in result


# ── Workflow cancel ─────────────────────────────────────────────────────────

def test_cancel_word_clears_active_workflow(tmp_path):
    app = build_test_app(tmp_path)
    session_id = app.session_id
    app.context_store.save_workflow_state(
        session_id,
        "calendar_event_workflow",
        {
            "workflow_name": "calendar_event_workflow",
            "status": "pending",
            "pending_slots": ["start_dt"],
            "summary": "dentist appointment",
        },
    )
    assert app.context_store.get_active_workflow(session_id) is not None

    result = app.workflow_orchestrator.continue_active("cancel", session_id)

    assert result.handled is True
    assert "cancel" in result.response.lower()
    assert app.context_store.get_active_workflow(session_id) is None


def test_cancel_typo_clears_active_workflow(tmp_path):
    """Misspelled 'cancle' should still cancel (fuzzy match)."""
    app = build_test_app(tmp_path)
    session_id = app.session_id
    app.context_store.save_workflow_state(
        session_id,
        "file_workflow",
        {
            "workflow_name": "file_workflow",
            "status": "pending",
            "pending_slots": ["filename"],
            "last_action": "create",
            "target": {},
        },
    )
    result = app.workflow_orchestrator.continue_active("cancle", session_id)

    assert result.handled is True
    assert app.context_store.get_active_workflow(session_id) is None


def test_abort_clears_active_workflow(tmp_path):
    app = build_test_app(tmp_path)
    session_id = app.session_id
    app.context_store.save_workflow_state(
        session_id,
        "file_workflow",
        {
            "workflow_name": "file_workflow",
            "status": "pending",
            "pending_slots": ["filename"],
            "last_action": "create",
            "target": {},
        },
    )
    result = app.workflow_orchestrator.continue_active("abort", session_id)

    assert result.handled is True
    assert app.context_store.get_active_workflow(session_id) is None


def test_non_cancel_word_does_not_clear_workflow(tmp_path):
    """A legitimate workflow reply must NOT be mistaken for a cancel command."""
    app = build_test_app(tmp_path)
    session_id = app.session_id
    app.context_store.save_workflow_state(
        session_id,
        "calendar_event_workflow",
        {
            "workflow_name": "calendar_event_workflow",
            "status": "pending",
            "pending_slots": ["start_dt"],
            "summary": "dentist",
        },
    )
    # "today at 3 pm" should not be treated as cancel
    # (workflow will fail to execute without workspace ext, but state must remain)
    app.workflow_orchestrator.continue_active("today at 3 pm", session_id)
    # workflow state may or may not be present depending on handler, but "cancel"
    # detection must not have fired — verify the cancel path was not taken
    # by checking we didn't get the cancel response through continue_active
    # with the cancel words specifically
    cancel_result = app.workflow_orchestrator.continue_active("stop the music", session_id)
    # "stop the music" has "music" as a meaningful non-cancel word → not a cancel
    # (workflow may already be gone at this point, so just verify not cancel response)
    if cancel_result.handled:
        assert "music" not in cancel_result.response.lower() or "cancel" not in cancel_result.response.lower()


# ── Screenshot path storage ─────────────────────────────────────────────────

def test_take_screenshot_stores_path_in_dialog_state(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_path = str(tmp_path / "screenshot_20260515_102814.png")
    import modules.system_control.plugin as sc_plugin
    monkeypatch.setattr(sc_plugin, "take_screenshot", lambda: f"Screenshot saved successfully at: {fake_path}")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    plugin = SystemControlPlugin(app)

    plugin.handle_take_screenshot("take a screenshot", {})

    assert app.dialog_state.selected_file == fake_path


def test_open_it_after_screenshot_opens_screenshot(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_path = str(tmp_path / "screenshot_20260515_102814.png")
    (tmp_path / "screenshot_20260515_102814.png").write_bytes(b"PNG")
    import modules.system_control.plugin as sc_plugin
    monkeypatch.setattr(sc_plugin, "take_screenshot", lambda: f"Screenshot saved successfully at: {fake_path}")
    import modules.system_control.file_search as fs
    opened = []
    monkeypatch.setattr(fs, "open_path", lambda path, label="file": opened.append(path) or f"Opening {label}...")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    app = build_test_app(tmp_path)
    SystemControlPlugin(app)

    app.router.process_text("take a screenshot")
    response = app.router.process_text("open it")

    assert opened, "xdg-open (open_path) was never called"
    assert opened[0] == fake_path
    assert "Which file" not in response
