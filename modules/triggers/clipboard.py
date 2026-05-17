"""Clipboard trigger — fires when clipboard content changes.

Uses the platform adapter's clipboard_read() for polling.
No external dependencies.

Usage:
    trigger = ClipboardTrigger(
        trigger_id="clipboard_watch",
        name="Clipboard changed",
        event_bus=app.event_bus,
    )
    trigger.start()
"""
from __future__ import annotations

import threading

from core.logger import logger
from .base import BaseTrigger


class ClipboardTrigger(BaseTrigger):
    """Fires when the clipboard content changes."""

    def __init__(
        self,
        trigger_id: str,
        name: str,
        event_bus,
        poll_interval: float = 1.5,
        min_length: int = 3,
    ):
        super().__init__(trigger_id, name, event_bus)
        self._poll_interval = poll_interval
        self._min_length = min_length
        self._last_value: str = ""
        self._thread: threading.Thread | None = None

    @property
    def trigger_type(self) -> str:
        return "clipboard"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            from modules.system_control.adapters import get_adapter
            self._adapter = get_adapter()
        except Exception as exc:
            logger.warning("[ClipboardTrigger] adapter unavailable: %s", exc)
            self._adapter = None
            return
        self._last_value = self._read()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _read(self) -> str:
        if self._adapter is None:
            return ""
        try:
            return (self._adapter.clipboard_read() or "").strip()
        except Exception:
            return ""

    def _loop(self) -> None:
        import time
        while self._running:
            time.sleep(self._poll_interval)
            current = self._read()
            if current != self._last_value and len(current) >= self._min_length:
                self._last_value = current
                self.fire({"text": current[:500]})
