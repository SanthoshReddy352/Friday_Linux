"""Lightweight tracing primitives for FRIDAY.

A single contextvar (`trace_id_var`) carries a per-turn correlation id through
synchronous and threaded code paths. The TurnManager binds it at the start of
each turn; everything that logs or publishes during that turn picks it up
automatically through the logging filter and the EventBus.

Phase 0: contextvar + trace_scope.
Phase 10: structured per-turn trace export to data/traces.jsonl.
"""

from __future__ import annotations

import contextvars
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any


trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "friday_trace_id", default=""
)

_write_lock = threading.Lock()
_traces_path: str | None = None


def configure_trace_export(path: str) -> None:
    """Set the path for structured JSONL trace export.

    Call once from FridayApp.initialize() with the data directory path.
    If never called, traces are captured in memory only.
    """
    global _traces_path
    _traces_path = path


def current_trace_id() -> str:
    return trace_id_var.get("")


def new_trace_id() -> str:
    return uuid.uuid4().hex[:12]


@contextmanager
def trace_scope(trace_id: str | None = None):
    """Bind a trace_id for the duration of the with-block.

    Usage:
        with trace_scope() as tid:
            ...   # all logger.* calls and event_bus.publish() carry `tid`
    """
    tid = trace_id or new_trace_id()
    token = trace_id_var.set(tid)
    started_at = time.monotonic()
    try:
        yield trace_id_var.get()
    finally:
        trace_id_var.reset(token)


class TurnTrace:
    """Accumulates structured events for one turn and exports them to JSONL.

    Usage (inside TurnManager):
        with TurnTrace(turn_id=turn.turn_id) as trace:
            trace.record("capability", capability_name, duration_ms=..., ok=True)
    """

    def __init__(self, turn_id: str):
        self.turn_id = turn_id
        self._started_at = time.monotonic()
        self._events: list[dict] = []

    def record(self, event_type: str, name: str, *, duration_ms: float = 0.0, ok: bool = True, error: str = "") -> None:
        self._events.append({
            "type": event_type,
            "name": name,
            "duration_ms": round(duration_ms, 1),
            "ok": ok,
            "error": error,
        })

    def __enter__(self) -> "TurnTrace":
        return self

    def __exit__(self, *_: Any) -> None:
        self._export()

    def _export(self) -> None:
        if not _traces_path:
            return
        record = {
            "trace_id": self.turn_id,
            "wall_ms": round((time.monotonic() - self._started_at) * 1000, 1),
            "events": self._events,
        }
        try:
            os.makedirs(os.path.dirname(_traces_path), exist_ok=True)
            with _write_lock:
                with open(_traces_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        except Exception:
            pass
