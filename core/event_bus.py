"""In-process publish/subscribe bus.

Kept sync for backward compatibility (Qt slots, audio callbacks, and llama
streaming hooks all expect synchronous delivery). Phase 0 changes:

  * Subscriber exceptions are now routed through the structured logger with
    topic, handler qualname, and trace_id, instead of printed to stdout.
  * Each publish records a debug-level breadcrumb so traces can be replayed
    after the fact.
  * Public API (subscribe / unsubscribe / publish) is unchanged.

Async-safe variants and topic schemas land in Phase 4 alongside the
extension-protocol rewrite.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from core.logger import logger
from core.tracing import current_trace_id


Subscriber = Callable[[Any], None]


class EventBus:
    def __init__(self):
        self.subscribers: dict[str, list[Subscriber]] = defaultdict(list)

    def subscribe(self, event_type: str, callback: Subscriber) -> None:
        bucket = self.subscribers[event_type]
        if callback not in bucket:
            bucket.append(callback)

    def unsubscribe(self, event_type: str, callback: Subscriber) -> None:
        bucket = self.subscribers.get(event_type)
        if not bucket:
            return
        try:
            bucket.remove(callback)
        except ValueError:
            pass

    def publish(self, event_type: str, data: Any = None) -> None:
        """Deliver `data` to every subscriber of `event_type`.

        Subscriber exceptions are caught per-subscriber so one failing
        handler cannot starve the rest. Failures are logged with structured
        fields (topic, handler, trace_id) so they show up in the rotating
        file log instead of being lost to stdout.
        """
        bucket = self.subscribers.get(event_type)
        if not bucket:
            return

        trace_id = current_trace_id()
        # Snapshot the list so subscribers that mutate it during dispatch
        # (subscribe/unsubscribe from inside a handler) do not corrupt the
        # iteration.
        for callback in list(bucket):
            try:
                callback(data)
            except Exception:
                logger.exception(
                    "[event_bus] subscriber failed",
                    extra={
                        "event_topic": event_type,
                        "event_handler": _handler_name(callback),
                        "trace_id": trace_id,
                    },
                )


def _handler_name(callback: Subscriber) -> str:
    name = getattr(callback, "__qualname__", None) or getattr(callback, "__name__", None)
    if name:
        module = getattr(callback, "__module__", "")
        return f"{module}.{name}" if module else name
    return repr(callback)
