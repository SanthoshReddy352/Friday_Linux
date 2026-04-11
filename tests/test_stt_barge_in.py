import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock

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
