import argparse
import logging
import os
import platform as _platform
import queue
import re
import signal
import subprocess
import sys
import threading
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


MIN_THRESHOLD = float(os.getenv("FRIDAY_CLAP_PEAK_THRESHOLD", "0.30"))

TARGET_SAMPLERATE = int(os.getenv("FRIDAY_CLAP_SAMPLERATE", "16000"))

MIN_GAP = float(os.getenv("FRIDAY_CLAP_MIN_GAP", "0.08"))
MAX_GAP = float(os.getenv("FRIDAY_CLAP_MAX_GAP", "1.0"))
TRIGGER_COOLDOWN = float(os.getenv("FRIDAY_CLAP_COOLDOWN", "2.0"))
SIGNAL_NORM_TARGET = 1.0

STATUS_LOG_INTERVAL_S = float(os.getenv("FRIDAY_CLAP_STATUS_LOG_INTERVAL_S", "10.0"))
WARMUP_SECONDS = float(os.getenv("FRIDAY_CLAP_WARMUP_S", "2.0"))
# Skip this many seconds at mic-open to avoid hardware turn-on transients
WARMUP_SETTLE_S = float(os.getenv("FRIDAY_CLAP_WARMUP_SETTLE_S", "0.5"))
STREAM_RETRY_DELAY_S = float(os.getenv("FRIDAY_CLAP_RETRY_DELAY_S", "2.0"))
# Burst detection: each frame is split into N_SUB_FRAMES chunks; a clap concentrates
# energy in 1-2 chunks (high burst ratio). Sustained noise spreads evenly (ratio ~1.0).
N_SUB_FRAMES = int(os.getenv("FRIDAY_CLAP_SUB_FRAMES", "10"))
BURST_RATIO_THRESHOLD = float(os.getenv("FRIDAY_CLAP_BURST_RATIO", "1.8"))


LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
CLAP_LOG_PATH = os.path.join(LOGS_DIR, "clap_detector.log")
CLAP_LAUNCH_LOG_PATH = os.path.join(LOGS_DIR, "clap_launch.log")

if _platform.system() == "Windows":
    VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
else:
    VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "bin", "python3")
MAIN_PY = os.path.join(PROJECT_ROOT, "main.py")
THIS_SCRIPT = os.path.abspath(__file__)
DETECTOR_MODULE = "modules.voice_io.clap_detector"


class TraceIdFilter(logging.Filter):
    """Injects a dummy trace_id into log records to prevent formatting errors."""
    def filter(self, record):
        if not hasattr(record, "trace_id"):
            record.trace_id = "-"
        return True

def setup_logger():
    """Configure rotating file logger and console output."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    logger = logging.getLogger("clap_detector")

    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s - PID:%(process)d - [%(trace_id)s] - %(levelname)s - %(message)s")

    file_handler = RotatingFileHandler(CLAP_LOG_PATH, maxBytes=1_000_000, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(TraceIdFilter())
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(TraceIdFilter())
    logger.addHandler(console_handler)

    return logger


LOGGER = setup_logger()


def _iter_processes():
    if _platform.system() == "Windows":
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/V", "/NH"],
            capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"tasklist failed: {error}")
        import csv
        import io
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) < 2:
                continue
            try:
                pid = int(row[1].strip('"'))
            except (ValueError, IndexError):
                continue
            command = row[0].strip('"')
            yield pid, command
    else:
        result = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
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
        popen_kwargs = dict(
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=launch_log,
            stderr=launch_log,
        )
        if _platform.system() == "Windows":
            popen_kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen([VENV_PYTHON, MAIN_PY], **popen_kwargs)
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
            if _platform.system() == "Windows":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
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
        if gap <= self.max_gap:
            self.waiting_for_second = False
            self.cooldown_until = now + self.cooldown
            self.last_spike_at = now  # Keep it as now to prevent immediate re-trigger during cooldown
            return "double"


        # Gap too long, restart sequence with this spike as the new 'first'
        self.last_spike_at = now
        self.waiting_for_second = True
        return "restart"



class ClapDetectorEngine:
    def __init__(
        self,
        min_threshold=MIN_THRESHOLD,
        min_gap=MIN_GAP,
        max_gap=MAX_GAP,
        cooldown=TRIGGER_COOLDOWN,
        warmup_seconds=WARMUP_SECONDS,
        warmup_settle_s=WARMUP_SETTLE_S,
        status_log_interval_s=STATUS_LOG_INTERVAL_S,
        n_sub_frames=N_SUB_FRAMES,
        burst_ratio_threshold=BURST_RATIO_THRESHOLD,
    ):
        self.base_min_threshold = min_threshold
        self.min_threshold = min_threshold
        self.n_sub_frames = n_sub_frames
        self.burst_ratio_threshold = burst_ratio_threshold
        self.status_log_interval_s = status_log_interval_s
        self.state = DoubleClapStateMachine(min_gap=min_gap, max_gap=max_gap, cooldown=cooldown)
        self.last_log_time = 0.0
        self.warmup_seconds = warmup_seconds
        self.warmup_settle_s = warmup_settle_s
        self._warmup_start = time.monotonic()
        self.warmup_until = self._warmup_start + warmup_seconds
        self._warmup_peaks = []
        self._warmup_done = False

    def _finish_warmup(self):
        if self._warmup_peaks:
            noise_floor = float(np.percentile(self._warmup_peaks, 75))
            
            # Dynamically adjust minimum threshold to be safely above the noise floor
            # A clap must be at least 1.5x louder than the ambient noise floor to avoid false triggers
            dynamic_threshold = max(self.base_min_threshold, noise_floor * 1.5)
            self.min_threshold = dynamic_threshold

            LOGGER.info("Warmup complete. Noise floor p75=%.4f. Using burst-ratio detection (threshold=%.2fx). Adjusted min_threshold=%.4f",
                        noise_floor, self.burst_ratio_threshold, self.min_threshold)
            
            if noise_floor > 0.5:
                LOGGER.warning(
                    "High ambient noise (noise_floor=%.4f). If false triggers persist, "
                    "reduce microphone gain in system audio settings.",
                    noise_floor,
                )
        self._warmup_peaks = []
        self._warmup_done = True

    def begin_warmup(self):
        now = time.monotonic()
        self._warmup_start = now
        self.warmup_until = now + self.warmup_seconds
        self._warmup_peaks = []
        self._warmup_done = False
        self.state.waiting_for_second = False
        self.state.last_spike_at = 0.0
        self.state.cooldown_until = 0.0

    def process_frame(self, indata, now=None):
        now = time.monotonic() if now is None else now
        audio = np.asarray(indata, dtype=np.float32)
        if audio.ndim <= 1:
            samples = audio.reshape(-1)
        else:
            samples = np.mean(audio, axis=1, dtype=np.float32)
        if samples.size == 0:
            return None

        # DC removal
        samples_centered = samples - np.mean(samples)
        peak = float(np.max(np.abs(samples_centered)))

        # Sub-frame burst ratio: split frame into N chunks, compare loudest chunk to mean.
        # A clap concentrates energy in 1-2 chunks → high ratio.
        # Sustained ambient noise spreads energy evenly → ratio near 1.0.
        n = self.n_sub_frames
        chunk_size = max(1, len(samples_centered) // n)
        sub_rms = [
            float(np.sqrt(np.mean(samples_centered[i:i + chunk_size] ** 2)))
            for i in range(0, len(samples_centered) - chunk_size + 1, chunk_size)
        ]
        mean_sub_rms = float(np.mean(sub_rms)) if sub_rms else 0.0
        max_sub_rms = float(np.max(sub_rms)) if sub_rms else 0.0
        burst_ratio = max_sub_rms / max(mean_sub_rms, 1e-6)

        if now - self.last_log_time >= self.status_log_interval_s:
            LOGGER.info(
                "Peak=%.4f BurstRatio=%.2f BurstThresh=%.2f WaitingSecond=%s",
                peak, burst_ratio, self.burst_ratio_threshold, self.state.waiting_for_second,
            )
            self.last_log_time = now

        if now < self.warmup_until:
            if (now - self._warmup_start) >= self.warmup_settle_s:
                self._warmup_peaks.append(peak)
            return None

        if not self._warmup_done:
            self._finish_warmup()

        # Noise gate: ignore very quiet frames
        if peak < self.min_threshold:
            self.state.expire(now)
            return None

        # Burst gate: require a transient shape, not just loud amplitude
        if burst_ratio < self.burst_ratio_threshold:
            self.state.expire(now)
            return None

        event = self.state.note_spike(now)
        if event == "first":
            LOGGER.info("First clap detected. Peak=%.3f BurstRatio=%.2f", peak, burst_ratio)
        elif event == "restart":
            LOGGER.info("Clap gap exceeded. Restarting sequence. Peak=%.3f BurstRatio=%.2f", peak, burst_ratio)
        elif event == "double":
            LOGGER.info("Double clap confirmed. Peak=%.3f BurstRatio=%.2f. Triggering launch.", peak, burst_ratio)
        return event



class ClapDetectorService:
    def __init__(self):
        self.device_id = None
        self.device_label = "System default"
        self._startup_device_selected = False
        self.detector = ClapDetectorEngine()
        self.events = queue.Queue(maxsize=4)
        # Signals the main loop that a launch was fired by the worker thread
        self._launched_event = threading.Event()

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

    def _launch_worker(self):
        """Daemon thread: blocks on the event queue and launches FRIDAY immediately on double-clap."""
        while True:
            try:
                event = self.events.get(timeout=1.0)
            except queue.Empty:
                continue

            if event != "double_clap":
                continue

            if is_friday_running():
                LOGGER.info("FRIDAY is already running. Ignoring clap launch request.")
                continue

            try:
                launch_friday()
                self._launched_event.set()
                # Drain any extra events queued during the same gesture
                while not self.events.empty():
                    try:
                        self.events.get_nowait()
                    except queue.Empty:
                        break
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

        worker = threading.Thread(target=self._launch_worker, daemon=True, name="clap-launch-worker")
        worker.start()

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
                        if self._launched_event.wait(timeout=0.5):
                            # Worker already launched FRIDAY; give the process a moment to appear
                            self._launched_event.clear()
                            LOGGER.info("Launch triggered. Releasing microphone.")
                            time.sleep(0.5)
                            break

                        if is_friday_running():
                            LOGGER.info("FRIDAY is running. Releasing microphone.")
                            break


                # Wait for FRIDAY to exit before trying to re-acquire the mic
                while is_friday_running():
                    time.sleep(5)
                LOGGER.info("FRIDAY stopped. Re-acquiring microphone.")


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
