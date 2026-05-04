import argparse
import logging
import os
import queue
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules.voice_io.audio_devices import (
    apply_input_device_selection,
    choose_startup_input_device,
    list_audio_input_devices,
)


MIN_THRESHOLD = float(os.getenv("FRIDAY_CLAP_MIN_THRESHOLD", "0.065"))
DYNAMIC_MULT = float(os.getenv("FRIDAY_CLAP_DYNAMIC_MULT", "1.6"))
CREST_FACTOR_MIN = float(os.getenv("FRIDAY_CLAP_CREST_FACTOR_MIN", "4.2"))
TARGET_SAMPLERATE = int(os.getenv("FRIDAY_CLAP_SAMPLERATE", "16000"))
SECOND_CLAP_THRESHOLD_MULT = float(os.getenv("FRIDAY_CLAP_SECOND_THRESHOLD_MULT", "0.65"))
SECOND_CLAP_CREST_MULT = float(os.getenv("FRIDAY_CLAP_SECOND_CREST_MULT", "0.75"))

MIN_GAP = float(os.getenv("FRIDAY_CLAP_MIN_GAP", "0.06"))
MAX_GAP = float(os.getenv("FRIDAY_CLAP_MAX_GAP", "1.75"))
TRIGGER_COOLDOWN = float(os.getenv("FRIDAY_CLAP_COOLDOWN", "2.50"))
FLOOR_MAX = float(os.getenv("FRIDAY_CLAP_FLOOR_MAX", "0.25"))
SIGNAL_NORM_TARGET = 1.0

STATUS_LOG_INTERVAL_S = float(os.getenv("FRIDAY_CLAP_STATUS_LOG_INTERVAL_S", "5.0"))
WARMUP_SECONDS = float(os.getenv("FRIDAY_CLAP_WARMUP_S", "1.5"))
STREAM_RETRY_DELAY_S = float(os.getenv("FRIDAY_CLAP_RETRY_DELAY_S", "2.0"))

LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
CLAP_LOG_PATH = os.path.join(LOGS_DIR, "clap_detector.log")
CLAP_LAUNCH_LOG_PATH = os.path.join(LOGS_DIR, "clap_launch.log")

VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
MAIN_PY = os.path.join(PROJECT_ROOT, "main.py")
THIS_SCRIPT = os.path.abspath(__file__)
DETECTOR_MODULE = "modules.voice_io.clap_detector"


def setup_logger():
    os.makedirs(LOGS_DIR, exist_ok=True)

    logger = logging.getLogger("FRIDAY.clap_detector")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = RotatingFileHandler(CLAP_LOG_PATH, maxBytes=1_000_000, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


LOGGER = setup_logger()


def _iter_processes():
    result = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"ps failed: {error}")

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pid_text, _, command = line.partition(" ")
        if not pid_text.isdigit():
            continue
        yield int(pid_text), command.strip()


def _command_matches_target(command, *needles):
    lowered = command.lower()
    return any(needle.lower() in lowered for needle in needles)


def is_friday_running():
    """Check whether FRIDAY is already active."""
    current_pid = os.getpid()
    for pid, command in _iter_processes():
        if pid == current_pid:
            continue
        if _command_matches_target(command, MAIN_PY, " main.py", " main.py "):
            return True
    return False


def launch_friday():
    """Start FRIDAY in the background and capture bootstrap output."""
    if not os.path.exists(VENV_PYTHON):
        raise RuntimeError(f"Virtual environment not found at {VENV_PYTHON}")

    LOGGER.info("Triggering FRIDAY launch from double clap.")
    os.makedirs(LOGS_DIR, exist_ok=True)

    with open(CLAP_LAUNCH_LOG_PATH, "a", encoding="utf-8") as launch_log:
        process = subprocess.Popen(
            [VENV_PYTHON, MAIN_PY],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=launch_log,
            stderr=launch_log,
            start_new_session=True,
        )
    LOGGER.info("FRIDAY launch requested with pid %s.", process.pid)


def _detector_process_matches(command):
    lowered = command.lower()

    # Ignore shell/python wrapper commands that merely mention the detector path.
    if re.search(r"\b(?:ba|z)?sh\s+-c\b", lowered):
        return False
    if re.search(r"\bpython(?:3(?:\.\d+)?)?\s+-c\b", lowered):
        return False

    if f"-m {DETECTOR_MODULE}" in lowered:
        return True

    return bool(
        THIS_SCRIPT.lower() in lowered
        or re.search(r"(^|\s)(?:\S+/)?clap_detector\.py(\s|$)", lowered)
        or re.search(r"(^|\s)(?:\S+/)?snap_detector\.py(\s|$)", lowered)
    )


def stop_existing():
    """Kill other clap detector instances, including older snap-detector names."""
    current_pid = os.getpid()
    stopped = 0
    try:
        for pid, command in _iter_processes():
            if pid == current_pid or not _detector_process_matches(command):
                continue
            os.kill(pid, signal.SIGTERM)
            stopped += 1
        return stopped
    except Exception as exc:
        LOGGER.error("Error stopping existing detector instances: %s", exc)
        return stopped


def get_status():
    """Check if another clap detector instance is running."""
    current_pid = os.getpid()
    try:
        for pid, command in _iter_processes():
            if pid != current_pid and _detector_process_matches(command):
                return True
        return False
    except Exception as exc:
        LOGGER.error("Error checking detector status: %s", exc)
        return False


@dataclass
class DoubleClapStateMachine:
    min_gap: float
    max_gap: float
    cooldown: float
    waiting_for_second: bool = False
    last_spike_at: float = 0.0
    cooldown_until: float = 0.0

    def expire(self, now):
        if self.waiting_for_second and (now - self.last_spike_at) > self.max_gap:
            self.waiting_for_second = False

    def note_spike(self, now):
        self.expire(now)

        if now < self.cooldown_until:
            return None

        if self.last_spike_at and (now - self.last_spike_at) < self.min_gap:
            return None

        if not self.waiting_for_second:
            self.last_spike_at = now
            self.waiting_for_second = True
            return "first"

        gap = now - self.last_spike_at
        self.last_spike_at = now
        if gap <= self.max_gap:
            self.waiting_for_second = False
            self.cooldown_until = now + self.cooldown
            return "double"

        self.waiting_for_second = True
        return "restart"


class ClapDetectorEngine:
    def __init__(
        self,
        min_threshold=MIN_THRESHOLD,
        dynamic_mult=DYNAMIC_MULT,
        crest_factor_min=CREST_FACTOR_MIN,
        second_clap_threshold_mult=SECOND_CLAP_THRESHOLD_MULT,
        second_clap_crest_mult=SECOND_CLAP_CREST_MULT,
        min_gap=MIN_GAP,
        max_gap=MAX_GAP,
        cooldown=TRIGGER_COOLDOWN,
        warmup_seconds=WARMUP_SECONDS,
        status_log_interval_s=STATUS_LOG_INTERVAL_S,
    ):
        self.min_threshold = min_threshold
        self.dynamic_mult = dynamic_mult
        self.crest_factor_min = crest_factor_min
        self.second_clap_threshold_mult = second_clap_threshold_mult
        self.second_clap_crest_mult = second_clap_crest_mult
        self.status_log_interval_s = status_log_interval_s
        self.state = DoubleClapStateMachine(min_gap=min_gap, max_gap=max_gap, cooldown=cooldown)
        self.background_rms = 0.01
        self.prev_data = np.zeros(0, dtype=np.float32)
        self.last_log_time = 0.0
        self.warmup_seconds = warmup_seconds
        self.warmup_until = time.monotonic() + warmup_seconds

    def begin_warmup(self):
        self.warmup_until = time.monotonic() + self.warmup_seconds
        self.state.waiting_for_second = False
        self.state.last_spike_at = 0.0
        self.state.cooldown_until = 0.0

    def process_frame(self, indata, now=None):
        now = time.monotonic() if now is None else now
        audio = np.asarray(indata, dtype=np.float32)
        if audio.ndim <= 1:
            samples = audio.reshape(-1)
        else:
            # Mix frames to mono instead of flattening interleaved channels.
            samples = np.mean(audio, axis=1, dtype=np.float32)
        if samples.size == 0:
            return None

        # Remove frame-level DC offset without smearing a clap impulse across the full block.
        transient_data = samples - float(np.mean(samples))
        self.prev_data = transient_data.copy()

        rms = float(np.sqrt(np.mean(transient_data**2)))
        peak = float(np.max(np.abs(transient_data)))

        # Handle non-normalized audio levels (e.g., if gain > 1.0 or driver glitch)
        if peak > 1.1:
            scale = SIGNAL_NORM_TARGET / (peak + 1e-6)
            transient_data *= scale
            rms *= scale
            peak *= scale

        capped_sample = min(rms, max(self.background_rms * 1.25, self.min_threshold * 0.5))
        self.background_rms = min(self.background_rms * 0.985 + capped_sample * 0.015, FLOOR_MAX)

        target_threshold = max(self.min_threshold, self.background_rms * self.dynamic_mult)
        if now - self.last_log_time >= self.status_log_interval_s:
            LOGGER.info(
                "Floor=%.4f RMS=%.4f Peak=%.4f Target=%.4f WaitingSecond=%s",
                self.background_rms,
                rms,
                peak,
                target_threshold,
                self.state.waiting_for_second,
            )
            self.last_log_time = now

        if now < self.warmup_until:
            return None

        if rms <= 0.0001:
            self.state.expire(now)
            return None

        crest = peak / rms
        required_rms = target_threshold
        required_crest = self.crest_factor_min
        if self.state.waiting_for_second:
            required_rms = max(self.min_threshold * self.second_clap_threshold_mult, target_threshold * self.second_clap_threshold_mult)
            required_crest = self.crest_factor_min * self.second_clap_crest_mult

        if rms <= required_rms or crest <= required_crest:
            self.state.expire(now)
            return None

        event = self.state.note_spike(now)
        if event == "first":
            LOGGER.info(
                "First clap candidate detected. RMS=%.3f Floor=%.3f Crest=%.2f",
                rms,
                self.background_rms,
                crest,
            )
        elif event == "restart":
            LOGGER.info("Clap gap exceeded %.2fs. Restarting double-clap window.", self.state.max_gap)
        elif event == "double":
            LOGGER.info(
                "Double clap confirmed. RMS=%.3f Floor=%.3f Crest=%.2f. Scheduling FRIDAY launch.",
                rms,
                self.background_rms,
                crest,
            )
        return event


class ClapDetectorService:
    def __init__(self):
        self.device_id = None
        self.device_label = "System default"
        self._startup_device_selected = False
        self.detector = ClapDetectorEngine()
        self.events = queue.Queue(maxsize=4)

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            LOGGER.warning("Audio callback status: %s", status)

        event = self.detector.process_frame(indata)
        if event != "double":
            return

        try:
            self.events.put_nowait("double_clap")
        except queue.Full:
            LOGGER.debug("Launch event queue already contains a pending trigger.")

    def handle_pending_events(self):
        handled = 0
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return handled

            handled += 1
            if event != "double_clap":
                continue

            if is_friday_running():
                LOGGER.info("FRIDAY is already running. Ignoring clap launch request.")
                continue

            try:
                launch_friday()
            except Exception as exc:
                LOGGER.exception("Failed to launch FRIDAY: %s", exc)

    def run(self):
        try:
            import sounddevice as sd
        except Exception as exc:
            LOGGER.exception("sounddevice is unavailable: %s", exc)
            raise

        LOGGER.info("====================================================")
        LOGGER.info("FRIDAY Double Clap Detector")
        LOGGER.info("Monitoring for clap pairs to launch FRIDAY.")
        LOGGER.info("====================================================")

        while True:
            try:
                self._ensure_startup_input_device()
                stream_settings = self._resolve_stream_settings(sd)
                self.detector.begin_warmup()

                LOGGER.info(
                    "Opening microphone on %s (%s Hz, %s channel%s, blocksize=%s).",
                    stream_settings["label"],
                    stream_settings["samplerate"],
                    stream_settings["channels"],
                    "" if stream_settings["channels"] == 1 else "s",
                    stream_settings["blocksize"],
                )

                with sd.InputStream(
                    samplerate=stream_settings["samplerate"],
                    blocksize=stream_settings["blocksize"],
                    device=stream_settings["device"],
                    dtype="float32",
                    channels=stream_settings["channels"],
                    callback=self.audio_callback,
                ):
                    LOGGER.info("Listener ACTIVE. Clap twice to launch FRIDAY.")
                    while True:
                        self.detector.state.expire(time.monotonic())
                        self.handle_pending_events()
                        time.sleep(0.25)
            except KeyboardInterrupt:
                LOGGER.info("Stopping clap detector.")
                return
            except Exception as exc:
                LOGGER.exception(
                    "Clap detector stream failed: %s. Retrying in %.1fs.",
                    exc,
                    STREAM_RETRY_DELAY_S,
                )
                time.sleep(STREAM_RETRY_DELAY_S)

    def _ensure_startup_input_device(self):
        if self._startup_device_selected or self.device_id is not None or self.device_label != "System default":
            return

        try:
            devices = list_audio_input_devices()
        except Exception as exc:
            LOGGER.warning("Could not inspect microphone devices: %s", exc)
            return

        if not devices:
            LOGGER.warning("No microphone devices detected yet; falling back to system default.")
            return

        preferred = choose_startup_input_device(devices) or devices[0]

        try:
            selection = apply_input_device_selection(preferred.target)
        except Exception as exc:
            LOGGER.warning("Could not select startup microphone '%s': %s", preferred.label, exc)
            return

        self.device_id = selection.get("device")
        self.device_label = selection.get("label", preferred.label)
        self._startup_device_selected = True
        LOGGER.info("Startup microphone selected: %s", self.device_label)

    def _resolve_stream_settings(self, sd):
        default_input = None
        try:
            default_input = sd.default.device[0]
        except Exception:
            pass

        candidates = []

        def add_candidate(device, label=""):
            key = (device, label)
            if key not in candidates:
                candidates.append(key)

        add_candidate(self.device_id, self.device_label)
        if self.device_id is None:
            add_candidate(None, "System default")
            if default_input is not None:
                add_candidate(default_input, f"Default input {default_input}")

        try:
            all_devices = list(sd.query_devices())
        except Exception:
            all_devices = []

        preferred_ids = []
        fallback_ids = []
        for index, device in enumerate(all_devices):
            if device.get("max_input_channels", 0) <= 0:
                continue
            name = device.get("name", f"Input {index}")
            lowered = name.lower()
            if lowered in {"default", "pipewire", "sysdefault"} or "monitor" in lowered:
                fallback_ids.append((index, name))
                continue
            if any(token in lowered for token in ("built-in", "analog", "mic", "microphone", "hda intel", "alc")):
                preferred_ids.append((index, name))
            else:
                fallback_ids.append((index, name))

        for index, label in preferred_ids + fallback_ids:
            add_candidate(index, label)

        attempted = []
        for device, label in candidates:
            info = self._query_input_device_info(sd, device, default_input)
            if not info:
                continue
            max_channels = max(1, int(info.get("max_input_channels", 1) or 1))
            sample_rates = self._candidate_sample_rates(info)
            info_name = str(info.get("name", "")).strip().lower()
            label_name = str(label or "").strip().lower()
            prefers_stereo_first = info_name in {"default", "pipewire", "sysdefault"} or label_name.startswith("default input")
            channel_options = []
            if max_channels > 1 and prefers_stereo_first:
                channel_options.append(min(2, max_channels))
            channel_options.append(1)
            if max_channels > 1:
                stereo_channels = min(2, max_channels)
                if stereo_channels not in channel_options:
                    channel_options.append(stereo_channels)

            for sample_rate in sample_rates:
                for channels in channel_options:
                    blocksize = max(256, int(sample_rate * 0.05))
                    try:
                        sd.check_input_settings(
                            device=device,
                            samplerate=sample_rate,
                            channels=channels,
                            dtype="float32",
                        )
                        return {
                            "device": device,
                            "label": label or info.get("name", "System default"),
                            "samplerate": int(sample_rate),
                            "channels": channels,
                            "blocksize": blocksize,
                        }
                    except Exception as exc:
                        attempted.append(f"{label or device}:{sample_rate}Hz/{channels}ch ({exc})")
                        continue

        details = "; ".join(attempted[:6]) if attempted else "no compatible input candidates"
        raise RuntimeError(f"No compatible microphone input format found: {details}")

    def _query_input_device_info(self, sd, device, default_input):
        query_target = default_input if device is None and default_input is not None else device
        try:
            if query_target is None:
                return None
            return sd.query_devices(query_target, "input")
        except Exception:
            return None

    def _candidate_sample_rates(self, info):
        rates = [TARGET_SAMPLERATE]
        default_rate = info.get("default_samplerate")
        try:
            if default_rate:
                rounded = int(default_rate)
                if rounded not in rates:
                    rates.append(rounded)
        except Exception:
            pass
        for fallback in (48000, 44100):
            if fallback not in rates:
                rates.append(fallback)
        return rates


def main():
    parser = argparse.ArgumentParser(description="FRIDAY Double Clap Detector")
    parser.add_argument("--stop", action="store_true", help="Stop any running clap detector instances.")
    parser.add_argument("--status", action="store_true", help="Check if the clap detector is running.")
    parser.add_argument("--start", action="store_true", help="Start the clap detector (default if no args).")
    args = parser.parse_args()

    if args.stop:
        count = stop_existing()
        message = f"Stopped {count} running clap detector(s)." if count else "No running clap detector found."
        print(message)
        LOGGER.info(message)
        return

    if args.status:
        message = "Clap detector is RUNNING." if get_status() else "Clap detector is NOT running."
        print(message)
        LOGGER.info(message)
        return

    if get_status():
        message = "Clap detector is already running in another process."
        print(message)
        LOGGER.info(message)
        sys.exit(0)

    if not os.path.exists(VENV_PYTHON):
        message = f"Error: Virtual environment not found at {VENV_PYTHON}"
        print(message)
        LOGGER.error(message)
        sys.exit(1)

    service = ClapDetectorService()
    service.run()


if __name__ == "__main__":
    main()
