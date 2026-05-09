"""SmartErrorDetector — event-driven error detection with cheap pre-filters.

Two-gate pipeline:
  1. Window title scan (xdotool) — keyword match for Error/Warning/Failed/etc.
  2. VLM inference only when a new error title is seen (deduplicated per title).

VLM is invoked at most once per unique window title to avoid flooding.
xdotool is optional; if unavailable the monitor exits quietly.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time

from core.logger import logger

ERROR_KEYWORDS = re.compile(
    r"\b(error|warning|failed|exception|crash|fatal|critical)\b",
    re.IGNORECASE,
)

_POLL_INTERVAL = 3.0   # seconds between window title polls


def _get_active_window_title() -> str:
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=1.0,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def start_error_monitor(vision_service, event_bus) -> threading.Thread:
    """Start a daemon thread that polls for error windows every 3 seconds.

    Returns the Thread so the caller can join() it if needed (rarely necessary
    since it is a daemon and dies with the process).
    """
    last_error_title: list[str] = [""]  # mutable container for closure capture

    def _monitor():
        # Bail out immediately if xdotool is not available.
        if not _get_active_window_title() and _get_active_window_title() == "":
            # Try once more — empty string on first call could be a timing issue.
            time.sleep(0.5)
            if _get_active_window_title() == "":
                logger.info("[vision] smart_error_detector: xdotool not available — monitor exiting.")
                return

        while True:
            time.sleep(_POLL_INTERVAL)
            try:
                title = _get_active_window_title()
                if not title or title == last_error_title[0]:
                    continue
                if not ERROR_KEYWORDS.search(title):
                    continue

                last_error_title[0] = title
                logger.info("[vision] Error window detected: %s", title)

                from modules.vision.screenshot import take_screenshot
                img = take_screenshot()
                prompt = (
                    f"Window title is '{title}'. "
                    "Explain this error briefly. Maximum 2 sentences."
                )
                result = vision_service.infer(img, prompt, max_tokens=80)
                event_bus.publish("assistant_progress", {"text": result})
            except Exception as exc:
                logger.debug("[vision] Error detector poll: %s", exc)

    t = threading.Thread(target=_monitor, name="vision-error-monitor", daemon=True)
    t.start()
    return t
