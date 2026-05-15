"""TaskRunner — cancellable turn execution for voice commands.

Voice commands are submitted here rather than blocking the STT listen-loop.
Each submission cancels any in-progress task, so a new voice command always
wins immediately. CLI / GUI text input still uses the synchronous path.
"""
from __future__ import annotations

import threading

from core.logger import logger


class TaskRunner:
    def __init__(self, app) -> None:
        self._app = app
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel_event: threading.Event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, text: str, source: str = "voice") -> None:
        """Cancel any running task and start a new one in a daemon thread."""
        cancel_event = threading.Event()
        self._cancel_current(cancel_event)  # stop old, install new event
        t = threading.Thread(
            target=self._run,
            args=(text, source, cancel_event),
            daemon=True,
            name=f"friday-task",
        )
        with self._lock:
            self._thread = t
        t.start()

    def cancel_current(self, announce: bool = True) -> bool:
        """Signal the running task to stop. Returns True if something was cancelled."""
        was_busy = self._cancel_current(threading.Event())
        if was_busy:
            if announce:
                self._say("Task cancelled, sir. Ready for your next command.")
            logger.info("[TaskRunner] Task cancelled by user.")
        return was_busy

    def cancel_nowait(self) -> bool:
        """Signal stop and kill TTS immediately without blocking the caller.
        The background thread exits on its own once it notices the cancel event.
        Safe to call from the GUI thread."""
        with self._lock:
            old_event = self._cancel_event
            self._cancel_event = threading.Event()
            thread = self._thread
        was_busy = bool(thread and thread.is_alive())
        if was_busy:
            old_event.set()
            tts = getattr(self._app, "tts", None)
            if tts and hasattr(tts, "stop"):
                try:
                    tts.stop()
                except Exception:
                    pass
            logger.info("[TaskRunner] cancel_nowait — signalled, not joining.")
        return was_busy

    def is_busy(self) -> bool:
        with self._lock:
            t = self._thread
        return bool(t and t.is_alive())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cancel_current(self, new_event: threading.Event) -> bool:
        """Replace cancel event and wait for any live thread to finish."""
        with self._lock:
            old_event = self._cancel_event
            self._cancel_event = new_event
            thread = self._thread

        was_busy = bool(thread and thread.is_alive())
        if was_busy:
            old_event.set()
            # Stop TTS immediately so the user hears silence
            tts = getattr(self._app, "tts", None)
            if tts and hasattr(tts, "stop"):
                try:
                    tts.stop()
                except Exception:
                    pass
            thread.join(timeout=2.0)
        return was_busy

    def _run(self, text: str, source: str, cancel_event: threading.Event) -> None:
        try:
            self._app._execute_turn(text, source=source, cancel_event=cancel_event)
        except Exception as exc:
            logger.debug("[TaskRunner] Turn raised: %s", exc)
        finally:
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None

    def _say(self, message: str) -> None:
        bus = getattr(self._app, "event_bus", None)
        if bus:
            try:
                bus.publish("voice_response", message)
            except Exception:
                pass
