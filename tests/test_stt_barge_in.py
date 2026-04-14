import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, patch
import numpy as np

from core.assistant_context import AssistantContext
from modules.voice_io.stt import STTEngine


def test_stop_friday_does_not_forward_empty_command():
    app = MagicMock()
    app.is_speaking = True
    app.tts = MagicMock()

    stt = STTEngine(app)
    stt._process_voice_text("Stop Friday.")

    app.tts.stop.assert_called_once()
    app.process_input.assert_not_called()


def test_barge_in_processes_followup_command():
    app = MagicMock()
    app.is_speaking = True
    app.tts = MagicMock()

    stt = STTEngine(app)
    stt._process_voice_text("Friday stop open calculator")

    app.tts.stop.assert_called_once()
    app.process_input.assert_called_once_with("open calculator", source="voice")


def test_new_question_interrupts_active_tts_without_stop_keyword():
    app = MagicMock()
    app.is_speaking = True
    app.tts = MagicMock()
    app.tts.current_sentence = "Here is what I can do for you today"
    app.tts.current_text = "Here is what I can do for you today. I can launch apps and answer questions."

    stt = STTEngine(app)
    stt._process_voice_text("what is the cpu usage")

    app.tts.stop.assert_called_once()
    app.process_input.assert_called_once_with("what is the cpu usage", source="voice")


def test_echo_like_text_does_not_interrupt_active_tts():
    app = MagicMock()
    app.is_speaking = True
    app.tts = MagicMock()
    app.tts.current_sentence = "Here is what I can do for you today"
    app.tts.current_text = "Here is what I can do for you today. I can launch apps and answer questions."

    stt = STTEngine(app)
    stt._process_voice_text("here is what i can do for you today")

    app.tts.stop.assert_not_called()
    app.process_input.assert_not_called()


def test_polite_voice_command_is_cleaned_before_processing():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()

    stt = STTEngine(app)
    stt._process_voice_text("Friday, could you please open calculator for me?")

    app.process_input.assert_called_once_with("open calculator", source="voice")


def test_live_voice_activity_interrupts_tts_before_transcription():
    app = MagicMock()
    app.is_speaking = True
    app.tts = MagicMock()
    app.tts.speaking_started_at = 0.0

    stt = STTEngine(app)
    stt.is_listening = True
    stt.barge_in_rms_threshold = 0.02
    stt.barge_in_trigger_frames = 2
    stt.barge_in_grace_period_s = 0.0

    frame = np.full((800, 1), 0.05, dtype=np.float32)

    stt.audio_callback(frame, 800, None, None)
    app.tts.stop.assert_not_called()

    stt.audio_callback(frame, 800, None, None)
    app.tts.stop.assert_called_once()
    assert stt.q.empty()


def test_low_voice_activity_does_not_interrupt_tts():
    app = MagicMock()
    app.is_speaking = True
    app.tts = MagicMock()
    app.tts.speaking_started_at = 0.0

    stt = STTEngine(app)
    stt.is_listening = True
    stt.barge_in_rms_threshold = 0.02
    stt.barge_in_trigger_frames = 2
    stt.barge_in_grace_period_s = 0.0

    frame = np.full((800, 1), 0.005, dtype=np.float32)

    stt.audio_callback(frame, 800, None, None)
    stt.audio_callback(frame, 800, None, None)

    app.tts.stop.assert_not_called()
    assert stt.q.empty()


def test_live_barge_in_grace_period_ignores_initial_tts_echo():
    app = MagicMock()
    app.is_speaking = True
    app.tts = MagicMock()
    app.tts.speaking_started_at = 10.0

    stt = STTEngine(app)
    stt.is_listening = True
    stt.barge_in_rms_threshold = 0.02
    stt.barge_in_trigger_frames = 2
    stt.barge_in_grace_period_s = 1.0

    frame = np.full((800, 1), 0.05, dtype=np.float32)

    with patch("modules.voice_io.stt.time.monotonic", return_value=10.3):
        stt.audio_callback(frame, 800, None, None)
        stt.audio_callback(frame, 800, None, None)

    app.tts.stop.assert_not_called()
    assert stt.q.empty()
