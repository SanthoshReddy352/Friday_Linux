import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gui.hud import (
    format_calendar_event_item,
    format_hud_message,
    format_voice_mode_label,
    format_voice_runtime_status,
    format_weather_status,
)


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


def test_format_weather_status_formats_nellore_panel_metrics():
    formatted = format_weather_status({
        "status": "success",
        "temperature_c": 31.24,
        "feels_like_c": 34.8,
        "humidity": 62,
        "wind_kmh": 11.9,
        "condition": "Partly cloudy",
    })

    assert formatted == {
        "temperature": "31.2 C",
        "condition": "Partly cloudy",
        "details": "Feels 34.8 C  |  Humidity 62%  |  Wind 12 km/h",
    }


def test_format_calendar_event_item_formats_reminder_row():
    formatted = format_calendar_event_item({
        "title": "purchase a gift",
        "remind_at": "2026-04-28T16:10:00",
    })

    assert formatted == "28 Apr 04:10 PM  purchase a gift"
