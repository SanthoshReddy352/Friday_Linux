"""FocusModeWorkflow — distraction blocking with timer and reminders.

When started, the workflow:
  • mutes desktop notifications (GNOME `gsettings` if available),
  • pauses any active browser-media session via the browser worker,
  • starts a single end-of-session timer (default 25 min, capped at 120),
  • restores notifications and announces when the timer fires.

A second focus utterance while a session is active either reports the
remaining time or, if the user said "stop/end focus", ends it early.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time


_active_timer: threading.Timer | None = None
_focus_active: bool = False
_focus_state: dict = {
    "started_at": 0.0,
    "ends_at": 0.0,
    "minutes": 0,
    "previous_show_banners": None,
}


class FocusModeWorkflow:
    name = "focus_mode"

    _START_PATTERNS = (
        re.compile(r"\b(?:focus\s+mode|do\s+not\s+disturb|pomodoro|focus\s+for|concentrate)\b", re.IGNORECASE),
        re.compile(r"\bstart\s+(?:a\s+)?focus(?:\s+session)?\b", re.IGNORECASE),
        re.compile(r"\b(?:don'?t\s+disturb|no\s+interruptions?)\b", re.IGNORECASE),
    )
    _STOP_PATTERNS = (
        re.compile(r"\b(?:stop\s+focus|end\s+focus|exit\s+focus|disable\s+focus|focus\s+off|cancel\s+focus)\b", re.IGNORECASE),
        re.compile(r"\b(?:stop|end|cancel)\s+(?:my\s+)?focus\s+session\b", re.IGNORECASE),
    )
    _STATUS_PATTERNS = (
        re.compile(r"\b(?:focus\s+(?:status|left|remaining|time)|how\s+much\s+focus|when\s+does\s+focus\s+end)\b", re.IGNORECASE),
    )
    _DURATION_RE = re.compile(
        r"(\d+)\s*(?:min(?:ute)?s?|m\b|hour(?:s)?|hr(?:s)?|h\b)",
        re.IGNORECASE,
    )

    def __init__(self, app):
        self._app = app

    # ------------------------------------------------------------------
    # Workflow protocol
    # ------------------------------------------------------------------

    def should_start(self, user_text: str, context=None) -> bool:
        return (
            any(p.search(user_text) for p in self._START_PATTERNS)
            or any(p.search(user_text) for p in self._STOP_PATTERNS)
            or any(p.search(user_text) for p in self._STATUS_PATTERNS)
        )

    def can_continue(self, user_text: str, state: dict, context=None) -> bool:
        return any(p.search(user_text) for p in self._STOP_PATTERNS) or any(
            p.search(user_text) for p in self._STATUS_PATTERNS
        )

    def run(self, user_text: str, session_id: str, context=None):
        from core.workflow_orchestrator import WorkflowResult  # noqa: PLC0415

        if any(p.search(user_text) for p in self._STOP_PATTERNS):
            response = self._stop()
            return WorkflowResult(
                workflow_name=self.name,
                handled=True,
                response=response,
                state={"step": "ended"},
            )

        if any(p.search(user_text) for p in self._STATUS_PATTERNS):
            return WorkflowResult(
                workflow_name=self.name,
                handled=True,
                response=self._status(),
                state=dict(_focus_state),
            )

        minutes = self._extract_minutes(user_text)
        return WorkflowResult(
            workflow_name=self.name,
            handled=True,
            response=self._start(minutes, session_id),
            state={"step": "active", "minutes": minutes, "started_at": time.time()},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_minutes(self, user_text: str) -> int:
        match = self._DURATION_RE.search(user_text)
        if not match:
            return 25
        value = int(match.group(1))
        unit = match.group(0).lower()
        if "h" in unit and "m" not in unit.split("h", 1)[0]:
            value *= 60
        return max(1, min(value, 240))

    def _start(self, minutes: int, session_id: str) -> str:
        global _focus_active, _active_timer, _focus_state

        if _focus_active:
            remaining = max(0, int(_focus_state.get("ends_at", 0) - time.time()))
            return (
                f"Focus mode is already active with about {remaining // 60} minute(s) left. "
                "Say 'Friday end focus' to stop it early."
            )

        _focus_active = True
        previous_banners = self._set_notifications(False)
        self._pause_media()

        _focus_state = {
            "started_at": time.time(),
            "ends_at": time.time() + minutes * 60,
            "minutes": minutes,
            "previous_show_banners": previous_banners,
        }

        if _active_timer is not None:
            _active_timer.cancel()
        _active_timer = threading.Timer(minutes * 60, self._end_focus, args=(session_id,))
        _active_timer.daemon = True
        _active_timer.start()

        self._publish("focus_mode_changed", {"active": True, "duration_minutes": minutes})
        return (
            f"Focus mode activated for {minutes} minute(s), sir. "
            "Notifications are muted and media is paused. "
            "I'll let you know when time is up."
        )

    def _stop(self) -> str:
        global _focus_active, _active_timer, _focus_state
        if not _focus_active:
            return "Focus mode isn't active right now."
        if _active_timer is not None:
            _active_timer.cancel()
            _active_timer = None
        elapsed = max(0, int(time.time() - _focus_state.get("started_at", time.time())))
        self._restore_notifications()
        _focus_active = False
        _focus_state = {
            "started_at": 0.0,
            "ends_at": 0.0,
            "minutes": 0,
            "previous_show_banners": None,
        }
        self._publish("focus_mode_changed", {"active": False, "elapsed_minutes": elapsed // 60})
        return f"Ended focus mode after {elapsed // 60} minute(s). Notifications are back on."

    def _status(self) -> str:
        if not _focus_active:
            return "Focus mode isn't running."
        remaining = max(0, int(_focus_state.get("ends_at", 0) - time.time()))
        if remaining <= 0:
            return "Focus mode just finished."
        if remaining < 60:
            return f"About {remaining} second(s) left in this focus session."
        return f"About {remaining // 60} minute(s) left in this focus session."

    def _end_focus(self, session_id: str) -> None:
        global _focus_active, _focus_state, _active_timer
        if not _focus_active:
            return
        self._restore_notifications()
        _focus_active = False
        _active_timer = None
        minutes_done = _focus_state.get("minutes", 0)
        _focus_state = {
            "started_at": 0.0,
            "ends_at": 0.0,
            "minutes": 0,
            "previous_show_banners": None,
        }
        self._publish("focus_mode_changed", {"active": False, "elapsed_minutes": minutes_done})
        self._publish(
            "voice_response",
            f"Focus session complete after {minutes_done} minute(s), sir. Time to take a short break.",
        )

    # ------------------------------------------------------------------
    # System hooks
    # ------------------------------------------------------------------

    def _set_notifications(self, enabled: bool):
        global _focus_state
        if not shutil.which("gsettings"):
            return None
        try:
            previous = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.notifications", "show-banners"],
                capture_output=True, text=True, timeout=2, check=False,
            ).stdout.strip()
        except Exception:
            previous = None
        try:
            subprocess.run(
                [
                    "gsettings", "set", "org.gnome.desktop.notifications",
                    "show-banners", "true" if enabled else "false",
                ],
                check=False, timeout=2,
            )
        except Exception:
            pass
        return previous

    def _restore_notifications(self) -> None:
        global _focus_state
        previous = _focus_state.get("previous_show_banners")
        if previous is None:
            self._set_notifications(True)
            return
        if not shutil.which("gsettings"):
            return
        try:
            subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", previous],
                check=False, timeout=2,
            )
        except Exception:
            pass

    def _pause_media(self) -> None:
        service = getattr(self._app, "browser_media_service", None)
        if service is None:
            return
        fast = getattr(service, "fast_media_command", None)
        if fast is None:
            return
        try:
            fast("pause")
        except Exception:
            pass

    def _publish(self, event: str, data) -> None:
        bus = getattr(self._app, "event_bus", None)
        if bus:
            try:
                bus.publish(event, data)
            except Exception:
                pass

    @staticmethod
    def is_active() -> bool:
        return _focus_active
