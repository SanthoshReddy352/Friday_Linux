import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock

from core.app import FridayApp
from core.config import ConfigManager


def _wait_voice_turn(app, timeout=5.0):
    """Block until the TaskRunner finishes the current voice turn."""
    t = app.task_runner._thread
    if t and t.is_alive():
        t.join(timeout=timeout)


def test_process_input_emits_user_and_assistant_messages():
    app = FridayApp()
    app.router.process_text = MagicMock(return_value="Hi from FRIDAY")
    callback = MagicMock()
    app.set_gui_callback(callback)

    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    # Voice dispatch is async — process_input returns "" immediately
    result = app.process_input("Hello there", source="voice")
    assert result == ""
    _wait_voice_turn(app)

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
    # TTS.stop must not be called synchronously in process_input for voice
    app.tts.stop.assert_not_called()
    _wait_voice_turn(app)
    app.router.process_text.assert_called_once_with("open calculator")


def test_on_demand_voice_mode_mutes_after_voice_turn():
    app = FridayApp()
    app.config.config = {"conversation": {"listening_mode": "on_demand"}}
    app.turn_manager.handle_turn = MagicMock(return_value="Done.")

    mic_events = []
    app.event_bus.subscribe("gui_toggle_mic", mic_events.append)

    app.process_input("open calculator", source="voice")
    _wait_voice_turn(app)

    assert mic_events == [False, False]


def test_persistent_voice_mode_resumes_after_voice_turn():
    app = FridayApp()
    app.config.config = {"conversation": {"listening_mode": "persistent"}}
    app.turn_manager.handle_turn = MagicMock(return_value="Done.")

    mic_events = []
    app.event_bus.subscribe("gui_toggle_mic", mic_events.append)

    app.process_input("open calculator", source="voice")
    _wait_voice_turn(app)

    assert mic_events == [False, True]


def test_wake_word_voice_mode_rearms_after_voice_turn():
    app = FridayApp()
    app.config.config = {"conversation": {"listening_mode": "wake_word"}}
    app.turn_manager.handle_turn = MagicMock(return_value="Done.")

    mic_events = []
    app.event_bus.subscribe("gui_toggle_mic", mic_events.append)

    app.process_input("open calculator", source="voice")
    _wait_voice_turn(app)

    assert mic_events == [False, True]


def test_manual_voice_mode_does_not_auto_start_or_resume():
    app = FridayApp()
    app.config.config = {"conversation": {"listening_mode": "manual"}}
    app.turn_manager.handle_turn = MagicMock(return_value="Done.")

    mic_events = []
    app.event_bus.subscribe("gui_toggle_mic", mic_events.append)

    assert app.should_auto_start_voice() is False
    app.process_input("open calculator", source="voice")
    _wait_voice_turn(app)

    assert mic_events == [False, False]


def test_set_listening_mode_accepts_wake_word_and_persists(tmp_path):
    app = FridayApp()
    config_path = tmp_path / "config.yaml"
    app.config = ConfigManager(str(config_path))
    app.config.config = {"conversation": {"listening_mode": "on_demand"}}

    mic_events = []
    app.event_bus.subscribe("gui_toggle_mic", mic_events.append)

    mode = app.set_listening_mode("wake-word")

    reloaded = ConfigManager(str(config_path))
    reloaded.load()
    assert mode == "wake_word"
    assert reloaded.get("conversation.listening_mode") == "wake_word"
    assert mic_events == [True]


def test_process_input_resets_stale_voice_spoken_flag():
    app = FridayApp()
    app.turn_manager.handle_turn = MagicMock(return_value="Opening calculator.")
    app.capability_registry.register_tool({"name": "dummy", "description": "dummy", "parameters": {}}, lambda *_: "ok")
    app.router._voice_already_spoken = True

    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    app.process_input("open calculator", source="voice")
    _wait_voice_turn(app)

    assert spoken == ["Opening calculator."]
    assert app.router._voice_already_spoken is False


def test_emit_assistant_message_clears_per_turn_speech_flag():
    app = FridayApp()
    app.router._voice_already_spoken = True

    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    app.emit_assistant_message("Already spoken once.", speak=True)
    app.emit_assistant_message("Speak this one.", speak=True)

    assert spoken == ["Speak this one."]
    assert app.router._voice_already_spoken is False
