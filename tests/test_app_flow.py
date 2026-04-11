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
