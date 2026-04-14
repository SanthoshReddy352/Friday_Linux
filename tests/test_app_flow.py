import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock

from core.app import FridayApp


def test_process_input_emits_user_and_assistant_messages():
    app = FridayApp()
    app.router.process_text = MagicMock(return_value="Hi from FRIDAY")
    callback = MagicMock()
    app.set_gui_callback(callback)

    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    result = app.process_input("Hello there", source="voice")

    assert result == "Hi from FRIDAY"
    assert callback.call_args_list[0].args[0] == {
        "role": "user",
        "text": "Hello there",
        "source": "voice",
    }
    assert callback.call_args_list[1].args[0] == {
        "role": "assistant",
        "text": "Hi from FRIDAY",
        "source": "friday",
    }
    assert spoken == ["Hi from FRIDAY"]


def test_process_input_normalizes_typed_commands_before_routing():
    app = FridayApp()
    app.router.process_text = MagicMock(return_value="Opening calculator.")

    app.process_input("Could you please open calculator for me?", source="cli")

    app.router.process_text.assert_called_once_with("open calculator")


def test_typed_input_interrupts_active_speech_before_processing():
    app = FridayApp()
    app.router.process_text = MagicMock(return_value="Opening chrome.")
    app.tts = MagicMock()
    app.is_speaking = True

    app.process_input("open chrome", source="cli")

    app.tts.stop.assert_called_once()
    app.router.process_text.assert_called_once_with("open chrome")


def test_voice_input_does_not_auto_stop_tts_in_process_input():
    app = FridayApp()
    app.router.process_text = MagicMock(return_value="On it.")
    app.tts = MagicMock()
    app.is_speaking = True

    app.process_input("open calculator", source="voice")

    app.tts.stop.assert_not_called()
    app.router.process_text.assert_called_once_with("open calculator")
