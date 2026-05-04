import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock
from unittest.mock import patch

from prompt_toolkit.document import Document

from cli.terminal_ui import FridayTerminalUI


def make_app():
    app = MagicMock()
    app.event_bus.subscribe = MagicMock()
    app.emit_message = MagicMock()
    app.stt = MagicMock()
    app.stt.is_listening = False
    app.router.llm_model_path = __file__
    app.tts = MagicMock()
    return app


def test_voice_slash_command_turns_microphone_on():
    ui = FridayTerminalUI(make_app())

    handled = ui._handle_slash_command("/voice on")

    assert handled is True
    ui.app_core.stt.start_listening.assert_called_once()
    ui.app_core.emit_message.assert_called_with(
        "assistant",
        "Voice listening enabled.",
        source="friday",
    )


def test_terminal_ui_uses_full_screen_application():
    app = make_app()

    with patch("cli.terminal_ui.Application") as application_cls:
        application_cls.return_value = MagicMock()

        FridayTerminalUI(app)

    assert application_cls.call_args.kwargs["full_screen"] is True


def test_exit_slash_command_stops_ui_loop():
    ui = FridayTerminalUI(make_app())

    handled = ui._handle_slash_command("/exit")

    assert handled is True
    assert ui._running is False
    ui.app_core.emit_message.assert_called_with(
        "assistant",
        "Bye.",
        source="friday",
    )


def test_startup_greeting_reports_ready_system():
    ui = FridayTerminalUI(make_app())

    message = ui._build_startup_greeting()

    assert "System check complete" in message
    assert "chat, voice input, and speech are online" in message


def test_voice_slash_command_handles_audio_errors_without_closing_ui():
    ui = FridayTerminalUI(make_app())
    ui.app_core.stt.start_listening.side_effect = RuntimeError("device busy")

    handled = ui._handle_slash_command("/voice on")

    assert handled is True
    assert ui._running is True
    ui.app_core.emit_message.assert_called_with(
        "assistant",
        "I couldn't change the microphone state: device busy",
        source="friday",
    )


def test_help_slash_command_is_rendered_as_friday_message():
    ui = FridayTerminalUI(make_app())

    handled = ui._handle_slash_command("/help")

    assert handled is True
    ui.app_core.emit_message.assert_called_with(
        "assistant",
        "Commands:\n"
        "/help show commands\n"
        "/clear clear the transcript\n"
        "/stop stop current speech\n"
        "/voice on|off|toggle control the microphone\n"
        "/gui remind me about the legacy desktop UI\n"
        "/exit quit the session",
        source="friday",
    )


def test_gui_slash_command_is_rendered_as_friday_message():
    ui = FridayTerminalUI(make_app())

    handled = ui._handle_slash_command("/gui")

    assert handled is True
    ui.app_core.emit_message.assert_called_with(
        "assistant",
        "Launch the legacy window with: python main.py --gui",
        source="friday",
    )


def test_multiline_transcript_text_is_aligned_under_label():
    ui = FridayTerminalUI(make_app())

    formatted = ui._format_transcript_entry("FRIDAY", "line one\nline two")

    assert formatted == "FRIDAY    line one\n          line two"


def test_clear_transcript_resets_buffer_contents():
    ui = FridayTerminalUI(make_app())
    ui._transcript_entries.append("FRIDAY    hello")
    ui.transcript_area.buffer.set_document(
        Document("FRIDAY    hello", cursor_position=14),
        bypass_readonly=True,
    )

    ui._clear_transcript()

    assert list(ui._transcript_entries) == []
    assert ui.transcript_area.buffer.text == ""
