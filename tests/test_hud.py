import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gui.hud import format_hud_message, format_voice_mode_label, format_voice_runtime_status


def test_format_hud_message_prefixes_user_text():
    formatted = format_hud_message("user", "open the coffee file")

    assert formatted == "USER: open the coffee file"


def test_format_hud_message_truncates_long_replies():
    text = " ".join(f"line{i}" for i in range(100))

    formatted = format_hud_message("assistant", text, max_chars=80, max_lines=3)

    assert formatted.startswith("FRIDAY: ")
    assert formatted.endswith("...")
    assert formatted.count("\n") <= 3


def test_format_voice_mode_label_handles_all_runtime_modes():
    assert format_voice_mode_label("persistent") == "PERSISTENT"
    assert format_voice_mode_label("wake-word") == "WAKE-WORD"
    assert format_voice_mode_label("on_demand") == "ON-DEMAND"
    assert format_voice_mode_label("manual") == "MANUAL"


def test_format_voice_runtime_status_exposes_gate_device_and_rejection():
    formatted = format_voice_runtime_status({
        "ui_state": "armed",
        "actively_transcribing": False,
        "wake_armed": True,
        "device_label": "Built-in Audio Analog Stereo",
        "last_rejected_reason": "wake model missing",
    })

    assert formatted == {
        "state": "ARMED",
        "gate": "ARMED",
        "device": "Built-in Audio Analog Stereo",
        "rejected": "wake model missing",
        "wake_strategy": "Wake model",
    }


def test_format_voice_runtime_status_exposes_transcript_wake_fallback():
    formatted = format_voice_runtime_status({
        "ui_state": "armed",
        "actively_transcribing": True,
        "wake_armed": True,
        "wake_transcript_fallback": True,
        "wake_strategy": "Transcript fallback",
        "last_rejected_reason": "waiting for wake word",
    })

    assert formatted["gate"] == "TRANSCRIPT WAKE"
    assert formatted["wake_strategy"] == "Transcript fallback"
    assert formatted["rejected"] == "None"
