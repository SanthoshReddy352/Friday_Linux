"""Cron trigger — fires on a schedule using threading.Timer.

No external dependencies. Supports cron-like interval specification
(seconds, minutes, hours) or a simple period in seconds.

Usage:
    trigger = CronTrigger(
        trigger_id="morning_briefing",
        name="Morning briefing",
        interval_seconds=3600,
        event_bus=app.event_bus,
    )
    trigger.start()
"""
from __future__ import annotations

import threading

from .base import BaseTrigger


class CronTrigger(BaseTrigger):
    """Fires at a fixed interval."""

    def __init__(
        self,
        trigger_id: str,
        name: str,
        interval_seconds: float,
        event_bus,
        extra_data: dict | None = None,
    ):
        super().__init__(trigger_id, name, event_bus)
        self._interval = float(interval_seconds)
        self._extra = extra_data or {}
        self._timer: threading.Timer | None = None

    @property
    def trigger_type(self) -> str:
        return "cron"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._schedule()

    def stop(self) -> None:
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _schedule(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        if not self._running:
            return
        self.fire({"interval_seconds": self._interval, **self._extra})
        self._schedule()
