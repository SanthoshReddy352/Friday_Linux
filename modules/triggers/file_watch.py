"""FileWatch trigger — fires when a file or directory changes.

Uses the stdlib watchdog (if available) or a polling fallback.
Install watchdog for better performance: pip install watchdog

Usage:
    trigger = FileWatchTrigger(
        trigger_id="docs_changed",
        name="Docs changed",
        path="~/Documents",
        event_bus=app.event_bus,
    )
    trigger.start()
"""
from __future__ import annotations

import os
import threading

from core.logger import logger
from .base import BaseTrigger


class FileWatchTrigger(BaseTrigger):
    """Watches a path for changes and fires trigger_fired events."""

    def __init__(
        self,
        trigger_id: str,
        name: str,
        path: str,
        event_bus,
        patterns: list[str] | None = None,
        poll_interval: float = 5.0,
    ):
        super().__init__(trigger_id, name, event_bus)
        self._path = os.path.expanduser(path)
        self._patterns = patterns or ["*"]
        self._poll_interval = poll_interval
        self._observer = None
        self._poll_thread: threading.Thread | None = None

    @property
    def trigger_type(self) -> str:
        return "file_watch"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        if not os.path.exists(self._path):
            logger.warning("[FileWatch] path does not exist: %s", self._path)
            return
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class _Handler(FileSystemEventHandler):
                def __init__(self, trigger):
                    self._trigger = trigger

                def on_any_event(self, event):
                    if not event.is_directory:
                        self._trigger.fire({
                            "event_type": event.event_type,
                            "src_path": str(event.src_path),
                        })

            handler = _Handler(self)
            self._observer = Observer()
            self._observer.schedule(handler, self._path, recursive=True)
            self._observer.start()
            logger.info("[FileWatch] watching %s (watchdog)", self._path)
        except ImportError:
            logger.info("[FileWatch] watchdog not installed, using poll fallback for %s", self._path)
            self._start_poll()

    def _start_poll(self) -> None:
        self._poll_state = self._snapshot()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _snapshot(self) -> dict[str, float]:
        state: dict[str, float] = {}
        try:
            for root, _, files in os.walk(self._path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        state[fp] = os.path.getmtime(fp)
                    except OSError:
                        pass
        except Exception:
            pass
        return state

    def _poll_loop(self) -> None:
        import time
        while self._running:
            time.sleep(self._poll_interval)
            new_state = self._snapshot()
            for path, mtime in new_state.items():
                if path not in self._poll_state or self._poll_state[path] != mtime:
                    self.fire({"event_type": "modified", "src_path": path})
            self._poll_state = new_state

    def stop(self) -> None:
        self._running = False
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
            self._observer = None
