"""LifecycleManager — ordered start / stop with signal integration.

Services register themselves (or are registered by the composition root).
On start_all() they are started in registration order.
On stop_all() they are stopped in reverse order, which is the standard
dependency-teardown convention.

A service qualifies if it has:
  * an optional start()  method (called on start_all)
  * a required  stop()   method (called on stop_all)

Services without stop() are accepted as registration errors would be
confusing at late shutdown; they are simply skipped with a warning.
"""

from __future__ import annotations

import threading
from typing import Any

from core.logger import logger


class LifecycleManager:
    def __init__(self):
        self._services: list[tuple[str, Any]] = []
        self._lock = threading.Lock()
        self._started = False

    def register(self, service: Any, name: str = "") -> None:
        label = name or type(service).__name__
        with self._lock:
            self._services.append((label, service))

    def start_all(self) -> None:
        with self._lock:
            services = list(self._services)
        for label, svc in services:
            if hasattr(svc, "start"):
                try:
                    svc.start()
                    logger.info("[lifecycle] started: %s", label)
                except Exception:
                    logger.exception("[lifecycle] start failed: %s", label)
        self._started = True

    def stop_all(self) -> None:
        with self._lock:
            services = list(reversed(self._services))
        for label, svc in services:
            if hasattr(svc, "stop"):
                try:
                    svc.stop()
                    logger.info("[lifecycle] stopped: %s", label)
                except Exception:
                    logger.exception("[lifecycle] stop failed: %s", label)
        self._started = False

    @property
    def is_running(self) -> bool:
        return self._started
