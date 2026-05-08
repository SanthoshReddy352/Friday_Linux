import os
import sys
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.app import FridayApp
from modules.voice_io.stt import STTEngine


def test_deterministic_tool_plan_does_not_call_local_llm():
    app = FridayApp()
    calls = []
    app.router.get_tool_llm = MagicMock()
    app.router.get_llm = MagicMock()
    app.router.register_tool(
        {"name": "get_time", "description": "Tell the time.", "parameters": {}},
        lambda text, args: calls.append((text, args)) or "It is noon.",
    )

    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    result = app.process_input("what time is it", source="cli")

    assert result == "It is noon."
    assert calls == [("what time is it", {})]
    app.router.get_tool_llm.assert_not_called()
    app.router.get_llm.assert_not_called()
    assert spoken == ["It is noon."]


def test_chat_turn_speaks_progress_before_final_response_without_ack():
    app = FridayApp()
    app.config.config = {"conversation": {"progress_delays_s": [0.01]}}
    app.router.register_tool(
        {"name": "llm_chat", "description": "Chat.", "parameters": {"query": "string"}},
        lambda text, args: time.sleep(0.12) or "We are improving the architecture.",
        capability_meta={
            "connectivity": "local",
            "latency_class": "generative",
            "permission_mode": "always_ok",
            "side_effect_level": "read",
            "streaming": True,
        },
    )

    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    result = app.process_input("what are we doing", source="voice")
    # Voice dispatch is async — wait for the TaskRunner thread to finish
    assert result == ""
    t = app.task_runner._thread
    if t and t.is_alive():
        t.join(timeout=10.0)

    assert "I'm working on it." in spoken
    assert spoken[-1] == "We are improving the architecture."
    assert "Let me think that through." not in spoken


def test_streamed_chat_does_not_duplicate_final_speech():
    app = FridayApp()

    def streaming_chat(text, args):
        app.event_bus.publish("voice_response", "Streaming answer.")
        app.router._voice_already_spoken = True
        return "Streaming answer."

    app.router.register_tool(
        {"name": "llm_chat", "description": "Chat.", "parameters": {"query": "string"}},
        streaming_chat,
        capability_meta={"latency_class": "generative", "streaming": True},
    )

    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    result = app.process_input("hello there", source="cli")

    assert result == "Streaming answer."
    assert spoken.count("Streaming answer.") == 1


def test_long_media_transcript_does_not_trigger_media_control():
    app = MagicMock()
    app.is_speaking = False
    app.media_control_mode = True
    app.tts = None

    stt = STTEngine(app)
    stt.is_bluetooth_active = True
    stt.system_media_active = True

    stt._process_voice_text("we will see you in the next one bye")

    app.process_input.assert_not_called()
