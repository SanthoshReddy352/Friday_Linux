import os
import sys
import threading
import time
from unittest.mock import MagicMock, mock_open, patch

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.voice_io.clap_detector import (
    ClapDetectorEngine,
    ClapDetectorService,
    DoubleClapStateMachine,
    MAIN_PY,
    VENV_PYTHON,
    _detector_process_matches,
    launch_friday,
)


def test_double_clap_state_machine_confirms_pair_within_gap():
    detector = DoubleClapStateMachine(min_gap=0.1, max_gap=1.0, cooldown=2.5)

    assert detector.note_spike(1.0) == "first"
    assert detector.note_spike(1.3) == "double"
    assert detector.waiting_for_second is False
    assert detector.cooldown_until == 3.8


def test_double_clap_state_machine_ignores_spike_inside_min_gap():
    detector = DoubleClapStateMachine(min_gap=0.1, max_gap=1.0, cooldown=2.5)

    assert detector.note_spike(1.0) == "first"
    assert detector.note_spike(1.05) is None
    assert detector.note_spike(1.35) == "double"


def test_double_clap_state_machine_restarts_after_long_gap():
    detector = DoubleClapStateMachine(min_gap=0.1, max_gap=1.0, cooldown=2.5)

    assert detector.note_spike(1.0) == "first"
    assert detector.note_spike(2.5) == "first"


def test_launch_friday_uses_project_venv_and_main_entrypoint():
    fake_process = MagicMock(pid=4242)

    with patch("modules.voice_io.clap_detector.os.path.exists", return_value=True), \
         patch("builtins.open", mock_open()), \
         patch("modules.voice_io.clap_detector.subprocess.Popen", return_value=fake_process) as popen:
        launch_friday()

    popen.assert_called_once()
    args, kwargs = popen.call_args
    assert args[0] == [VENV_PYTHON, MAIN_PY]
    assert kwargs["cwd"].endswith("Friday_Linux")
    assert kwargs["start_new_session"] is True


def test_launch_worker_skips_launch_when_friday_is_already_running():
    """_launch_worker must not call launch_friday when FRIDAY is already up."""
    service = ClapDetectorService()

    with patch("modules.voice_io.clap_detector.is_friday_running", return_value=True), \
         patch("modules.voice_io.clap_detector.launch_friday") as launch:
        service.events.put("double_clap")
        # _launch_worker is an infinite daemon loop — run it in a background thread.
        worker = threading.Thread(target=service._launch_worker, daemon=True)
        worker.start()
        # Give the worker enough time to consume the queued event.
        time.sleep(0.2)

    launch.assert_not_called()


def test_detector_process_match_ignores_shell_wrappers():
    command = "python3 -c import subprocess; subprocess.Popen(['/home/tricky/Friday_Linux/modules/voice_io/clap_detector.py'])"

    assert _detector_process_matches(command) is False


def test_detector_process_match_accepts_real_script_invocation():
    command = "/usr/bin/python3 /home/tricky/Friday_Linux/modules/voice_io/clap_detector.py --start"

    assert _detector_process_matches(command) is True


def test_clap_detector_engine_accepts_slightly_softer_second_clap():
    engine = ClapDetectorEngine(
        min_threshold=0.08,
        min_gap=0.1,
        max_gap=1.35,
        cooldown=2.5,
        warmup_seconds=0.0,
        status_log_interval_s=9999.0,
    )

    engine.warmup_until = 0.0

    quiet = np.zeros(32, dtype=np.float32)
    first = np.concatenate([np.array([0.60], dtype=np.float32), np.zeros(31, dtype=np.float32)])
    second = np.concatenate([np.array([0.40], dtype=np.float32), np.zeros(31, dtype=np.float32)])

    assert engine.process_frame(quiet, now=0.00) is None
    assert engine.process_frame(first, now=1.00) == "first"
    assert engine.process_frame(quiet, now=1.05) is None
    assert engine.process_frame(second, now=1.45) == "double"


def test_clap_detector_engine_accepts_more_natural_double_clap():
    engine = ClapDetectorEngine(
        min_threshold=0.065,
        min_gap=0.06,
        max_gap=1.75,
        cooldown=2.5,
        warmup_seconds=0.0,
        status_log_interval_s=9999.0,
    )

    engine.warmup_until = 0.0

    quiet = np.zeros(32, dtype=np.float32)
    first = np.concatenate([np.array([0.42], dtype=np.float32), np.zeros(31, dtype=np.float32)])
    second = np.concatenate([np.array([0.28], dtype=np.float32), np.zeros(31, dtype=np.float32)])

    assert engine.process_frame(quiet, now=0.00) is None
    assert engine.process_frame(first, now=1.00) == "first"
    assert engine.process_frame(quiet, now=1.03) is None
    assert engine.process_frame(second, now=1.82) == "double"


def test_clap_detector_engine_restarts_when_second_clap_is_too_late():
    engine = ClapDetectorEngine(
        min_threshold=0.08,
        min_gap=0.1,
        max_gap=1.35,
        cooldown=2.5,
        warmup_seconds=0.0,
        status_log_interval_s=9999.0,
    )

    engine.warmup_until = 0.0

    first = np.concatenate([np.array([0.60], dtype=np.float32), np.zeros(31, dtype=np.float32)])
    quiet = np.zeros(32, dtype=np.float32)

    assert engine.process_frame(first, now=1.00) == "first"
    assert engine.process_frame(quiet, now=1.05) is None
    assert engine.process_frame(first, now=2.60) == "first"


def test_clap_detector_engine_downmixes_multichannel_audio():
    engine = ClapDetectorEngine(
        min_threshold=0.065,
        min_gap=0.06,
        max_gap=1.75,
        cooldown=2.5,
        warmup_seconds=0.0,
        status_log_interval_s=9999.0,
    )

    engine.warmup_until = 0.0

    quiet = np.zeros((32, 2), dtype=np.float32)
    first = np.zeros((32, 2), dtype=np.float32)
    second = np.zeros((32, 2), dtype=np.float32)
    first[0, :] = 0.42
    second[0, :] = 0.28

    assert engine.process_frame(quiet, now=0.00) is None
    assert engine.process_frame(first, now=1.00) == "first"

    assert engine.process_frame(quiet, now=1.03) is None
    assert engine.process_frame(second, now=1.82) == "double"
