import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, patch
import numpy as np

from core.assistant_context import AssistantContext
from core.event_bus import EventBus
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


def test_follow_up_question_is_allowed_inside_wake_session():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()

    stt = STTEngine(app)
    stt._process_voice_text("Friday open calculator")
    app.process_input.assert_called_once_with("open calculator", source="voice")

    app.process_input.reset_mock()
    stt._process_voice_text("what can you do for me")

    app.process_input.assert_called_once_with("what can you do", source="voice")


def test_recent_assistant_echo_is_dropped_after_speaking():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()
    app.assistant_context.record_message("assistant", "Always a pleasure to see you, sir. Ready for commands.")
    app.tts = MagicMock()
    app.tts.current_text = ""
    app.tts.current_sentence = ""
    app.tts.is_speaking = False
    app.tts.speaking_stopped_at = 10.0

    stt = STTEngine(app)
    with patch("modules.voice_io.stt.time.monotonic", return_value=10.5):
        stt._process_voice_text("It's a pleasure to see you, sir. Ready for commands.")

    app.process_input.assert_not_called()


def test_old_assistant_phrase_is_not_blocked_outside_echo_window():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()
    app.assistant_context.record_message("assistant", "What can I do for you today?")
    app.tts = MagicMock()
    app.tts.current_text = ""
    app.tts.current_sentence = ""
    app.tts.is_speaking = False
    app.tts.speaking_stopped_at = 10.0

    stt = STTEngine(app)
    with patch("modules.voice_io.stt.time.monotonic", return_value=13.0):
        stt._process_voice_text("what can you do for me")

    app.process_input.assert_called_once_with("what can you do", source="voice")


def test_low_signal_transcript_is_dropped():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()

    stt = STTEngine(app)
    stt._process_voice_text("you")

    app.process_input.assert_not_called()


def test_low_signal_transcript_is_dropped_before_voice_identified_log():
    app = MagicMock()
    app.is_speaking = False

    class Segment:
        text = " You."

    class FakeModel:
        def transcribe(self, *_args, **_kwargs):
            return [Segment()], None

    stt = STTEngine(app)
    stt.model = FakeModel()

    with patch("modules.voice_io.stt.logger.info") as info_log:
        stt._transcribe_buffer([np.zeros((800, 1), dtype=np.float32)])

    assert not any("[Voice Identified]" in str(call.args[0]) for call in info_log.call_args_list)
    app.process_input.assert_not_called()


def test_stt_defaults_to_base_en_for_fast_english_transcription():
    app = MagicMock()
    app.is_speaking = False
    app.config = None

    class Segment:
        text = " Namaste."

    class FakeModel:
        def __init__(self):
            self.kwargs = None

        def transcribe(self, *_args, **kwargs):
            self.kwargs = kwargs
            return [Segment()], None

    stt = STTEngine(app)
    stt.model = FakeModel()

    stt._transcribe_buffer([np.zeros((800, 1), dtype=np.float32)])

    assert stt.model_name == "base.en"
    assert stt.language == "en"
    assert stt.model.kwargs["language"] == "en"


def test_stt_language_can_be_pinned_from_config():
    class Config:
        def get(self, key, default=None):
            return {
                "voice.stt_model": "small",
                "voice.stt_compute_type": "int8",
                "voice.stt_language": "hi",
                "voice.stt_cpu_threads": 6,
            }.get(key, default)

    app = MagicMock()
    app.is_speaking = False
    app.config = Config()

    class Segment:
        text = " Namaste."

    class FakeModel:
        def __init__(self):
            self.kwargs = None

        def transcribe(self, *_args, **kwargs):
            self.kwargs = kwargs
            return [Segment()], None

    stt = STTEngine(app)
    stt.model = FakeModel()

    stt._transcribe_buffer([np.zeros((800, 1), dtype=np.float32)])

    assert stt.language == "hi"
    assert stt.cpu_threads == 6
    assert stt.model.kwargs["language"] == "hi"


def test_active_media_outro_phrase_is_dropped():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()

    stt = STTEngine(app)
    stt.system_media_active = True
    stt._process_voice_text("Thank you for watching!")

    app.process_input.assert_not_called()


def test_wake_up_survives_restricted_media_mode_after_wake_word_is_stripped():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()
    app.media_control_mode = True

    stt = STTEngine(app)
    stt.is_bluetooth_active = True
    stt.system_media_active = True

    stt._process_voice_text("Friday wake up")

    app.process_input.assert_called_once_with("wake up", source="voice")


def test_start_listening_waits_for_pending_tts_queue():
    app = MagicMock()
    app.is_speaking = False

    class PendingTTS:
        has_pending_speech = True
        is_speaking = False

    app.tts = PendingTTS()

    stt = STTEngine(app)
    stt.model = MagicMock()

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    def clear_pending(*_args):
        app.tts.has_pending_speech = False

    with patch("modules.voice_io.stt.threading.Thread", ImmediateThread), \
         patch("modules.voice_io.stt.time.sleep", side_effect=clear_pending):
        assert stt.start_listening() is True

    assert stt.is_listening is True


def test_start_listening_defers_model_initialization_without_blocking():
    app = MagicMock()
    app.is_speaking = False

    stt = STTEngine(app)
    started_threads = []

    class DeferredThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            started_threads.append((self.target, self.args))

    with patch("modules.voice_io.stt.threading.Thread", DeferredThread), \
         patch.object(stt, "initialize") as initialize:
        assert stt.start_listening() is True

    initialize.assert_not_called()
    assert stt.is_listening is False
    assert started_threads


def test_wake_word_mode_arms_without_transcribing_before_wake():
    app = MagicMock()
    app.is_speaking = False
    app.media_control_mode = False
    app.get_listening_mode.return_value = "wake_word"

    class FakeWakeDetector:
        unavailable_reason = ""

        def initialize(self):
            return True

        def process_frame(self, _frame):
            return False

    stt = STTEngine(app)
    stt.wake_detector = FakeWakeDetector()
    stt.model = MagicMock()
    stt.arm_wake_word()

    frame = np.full((800, 1), 0.05, dtype=np.float32)
    stt.audio_callback(frame, 800, None, None)

    assert stt.wake_armed is True
    assert stt.is_listening is False
    assert stt.q.empty()
    stt.model.transcribe.assert_not_called()


def test_wake_word_hit_opens_short_transcription_session():
    app = MagicMock()
    app.is_speaking = False
    app.media_control_mode = False
    app.get_listening_mode.return_value = "wake_word"
    app.event_bus = EventBus()

    class FakeWakeDetector:
        unavailable_reason = ""

        def initialize(self):
            return True

        def process_frame(self, _frame):
            return True

    stt = STTEngine(app)
    stt.wake_detector = FakeWakeDetector()
    stt.model = MagicMock()
    app.event_bus.subscribe("voice_activation_requested", lambda payload: stt.activate_for_invocation(payload["source"]))
    stt.arm_wake_word()

    frame = np.full((800, 1), 0.05, dtype=np.float32)
    stt.audio_callback(frame, 800, None, None)

    assert stt.wake_armed is False
    assert stt.is_listening is True
    assert stt._has_active_wake_session() is True


def test_missing_wake_model_uses_transcript_fallback():
    app = MagicMock()
    app.is_speaking = False
    app.media_control_mode = False
    app.get_listening_mode.return_value = "wake_word"

    stt = STTEngine(app)
    stt._start_hardware_stream = MagicMock()
    stt.wake_detector.model_path = "/tmp/friday-missing-wake-model.onnx"
    stt.model = MagicMock()

    stt.arm_wake_word()

    assert stt.last_rejected_reason == ""
    assert stt.wake_armed is True
    assert stt.is_listening is True
    assert stt.wake_transcript_fallback is True


def test_missing_wake_model_can_report_rejected_reason_when_fallback_disabled():
    app = MagicMock()
    app.is_speaking = False
    app.media_control_mode = False
    app.get_listening_mode.return_value = "wake_word"
    app.config.get.side_effect = lambda key, default=None: False if key == "voice.wake_transcript_fallback" else default

    stt = STTEngine(app)
    stt._start_hardware_stream = MagicMock()
    stt.wake_detector.model_path = "/tmp/friday-missing-wake-model.onnx"

    stt.arm_wake_word()

    assert stt.last_rejected_reason == "wake model missing"
    assert stt.wake_armed is False


def test_wake_word_mode_rejects_uninvoked_transcript():
    app = MagicMock()
    app.is_speaking = False
    app.media_control_mode = False
    app.assistant_context = AssistantContext()
    app.get_listening_mode.return_value = "wake_word"

    stt = STTEngine(app)

    stt._process_voice_text("open calculator right now")

    app.process_input.assert_not_called()
    assert stt.last_rejected_reason == "waiting for wake word"


def test_transcript_wake_word_opens_empty_wake_session_without_forwarding():
    app = MagicMock()
    app.is_speaking = False
    app.media_control_mode = False
    app.assistant_context = AssistantContext()
    app.get_listening_mode.return_value = "wake_word"
    app.event_bus = EventBus()

    stt = STTEngine(app)
    app.event_bus.subscribe("voice_activation_requested", lambda payload: stt.activate_for_invocation(payload["source"]))

    stt._process_voice_text("hey friday")

    app.process_input.assert_not_called()
    assert stt.last_rejected_reason == ""
    assert stt._has_active_wake_session() is True


def test_active_media_disables_rms_barge_in_even_on_bluetooth():
    app = MagicMock()
    app.is_speaking = False

    stt = STTEngine(app)
    stt.is_bluetooth_active = True
    stt.system_media_active = True

    stt._apply_adaptive_thresholds()

    assert stt.use_rms_barge_in is False


def test_media_session_rejects_uninvoked_transcript_with_reason():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()
    app.media_control_mode = True

    stt = STTEngine(app)
    stt.system_media_active = True

    stt._process_voice_text("we will see you in the next one bye")

    app.process_input.assert_not_called()
    assert stt.last_rejected_reason == "long transcript blocked during media"


def test_media_mode_does_not_trust_previous_wake_session_for_long_transcript():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()
    app.media_control_mode = True

    stt = STTEngine(app)
    stt.system_media_active = True
    stt._extend_wake_session()

    stt._process_voice_text("for the rest of the month all right thank you so much")

    app.process_input.assert_not_called()
    assert stt.last_rejected_reason == "long transcript blocked during media"


def test_media_mode_allows_short_media_command_during_wake_session():
    """During an active browser media session, a bare "play" should fast-path
    straight to the browser worker without going through the LLM router."""
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()
    app.media_control_mode = True

    stt = STTEngine(app)
    stt.system_media_active = True
    stt._extend_wake_session()

    stt._process_voice_text("play")

    # The new fast path dispatches to the browser worker on its own thread
    # and bypasses process_input entirely.
    app.process_input.assert_not_called()
    # Give the daemon thread a moment to call into the service.
    for _ in range(20):
        if app.browser_media_service.fast_media_command.called:
            break
        time.sleep(0.01)
    app.browser_media_service.fast_media_command.assert_called_once_with("resume")


def test_button_invocation_allows_media_session_transcript():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()
    app.media_control_mode = True
    app.get_listening_mode.return_value = "on_demand"

    stt = STTEngine(app)
    stt.system_media_active = True
    stt._explicit_activation_until = time.monotonic() + 5

    stt._process_voice_text("open calculator")

    app.process_input.assert_called_once_with("open calculator", source="voice")


def test_button_invocation_survives_slow_media_transcription():
    app = MagicMock()
    app.is_speaking = False
    app.assistant_context = AssistantContext()
    app.media_control_mode = True
    app.get_listening_mode.return_value = "on_demand"

    stt = STTEngine(app)
    stt.system_media_active = True
    stt._explicit_activation_until = time.monotonic() - 1
    stt._explicit_activation_pending = True

    stt._process_voice_text("give me a global intelligence brief")

    app.process_input.assert_called_once_with("give me a global intelligence brief", source="voice")
    assert stt._explicit_activation_pending is False


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


def test_start_listening_waits_until_speech_finishes():
    app = MagicMock()
    app.is_speaking = True

    stt = STTEngine(app)
    stt.model = MagicMock()
    real_thread = None

    class ImmediateThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    with patch("modules.voice_io.stt.threading.Thread", ImmediateThread), \
         patch("modules.voice_io.stt.time.sleep", side_effect=lambda *_: setattr(app, "is_speaking", False)):
        assert stt.start_listening() is True

    assert stt.is_listening is True


def test_start_listening_arms_gate_during_active_speech():
    app = MagicMock()
    app.is_speaking = True

    stt = STTEngine(app)
    stt.model = MagicMock()
    started_threads = []

    class DeferredThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            started_threads.append((self.target, self.args))

    with patch("modules.voice_io.stt.threading.Thread", DeferredThread):
        assert stt.start_listening() is True

    assert stt.is_listening is True
    assert started_threads


def test_start_listening_arms_gate_for_queued_speech():
    app = MagicMock()
    app.is_speaking = False

    class PendingTTS:
        has_pending_speech = True
        is_speaking = False

    app.tts = PendingTTS()

    stt = STTEngine(app)
    stt.model = MagicMock()
    started_threads = []

    class DeferredThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args

        def start(self):
            started_threads.append((self.target, self.args))

    with patch("modules.voice_io.stt.threading.Thread", DeferredThread):
        assert stt.start_listening() is True

    assert stt.is_listening is True
    assert started_threads


def test_complete_listen_waits_past_long_tts_response():
    app = MagicMock()
    app.is_speaking = True

    stt = STTEngine(app)
    request_id = stt._next_listen_request_id()
    ticks = {"sleep": 0, "time": 0.0}

    def fake_monotonic():
        ticks["time"] += 0.1
        return ticks["time"]

    def fake_sleep(*_args):
        ticks["sleep"] += 1
        if ticks["sleep"] >= 120:
            app.is_speaking = False

    with patch("modules.voice_io.stt.time.monotonic", side_effect=fake_monotonic), \
         patch("modules.voice_io.stt.time.sleep", side_effect=fake_sleep):
        stt._complete_listen_when_ready(request_id)

    assert ticks["sleep"] >= 120
    assert stt.is_listening is True
