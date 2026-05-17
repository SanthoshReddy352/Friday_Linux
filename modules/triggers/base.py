"""BaseTrigger — contract all triggers must satisfy.

Each trigger publishes a `trigger_fired` event to the EventBus when its
condition is met. WorkflowOrchestrator subscribes and dispatches the
associated action.

Event payload:
  {
    "trigger_type": "cron" | "file_watch" | "clipboard" | "process",
    "trigger_id":   str,
    "name":         str,
    "data":         dict,   # trigger-specific payload
  }
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.logger import logger


class BaseTrigger(ABC):
    def __init__(self, trigger_id: str, name: str, event_bus):
        self.trigger_id = trigger_id
        self.name = name
        self.event_bus = event_bus
        self._running = False

    def fire(self, data: dict | None = None) -> None:
        payload = {
            "trigger_type": self.trigger_type,
            "trigger_id": self.trigger_id,
            "name": self.name,
            "data": data or {},
        }
        logger.debug("[trigger] fired: %s (%s)", self.name, self.trigger_type)
        self.event_bus.publish("trigger_fired", payload)

    @property
    @abstractmethod
    def trigger_type(self) -> str:
        ...

    @abstractmethod
    def start(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...
