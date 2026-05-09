from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnRecord:
    turn_id: str
    text: str
    source: str
    started_at: float = field(default_factory=time.monotonic)
    completed_at: float = 0.0
    cancelled: bool = False
    metrics: dict[str, float] = field(default_factory=dict)


class RuntimeMetrics:
    def __init__(self, max_records: int = 20):
        self.max_records = max(1, int(max_records))
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = []

    def record(self, turn: TurnRecord, response: str = "", ok: bool = True):
        item = {
            "turn_id": turn.turn_id,
            "source": turn.source,
            "duration_ms": round((turn.completed_at - turn.started_at) * 1000, 1) if turn.completed_at else 0.0,
            "ok": ok,
            "response_chars": len(response or ""),
            **turn.metrics,
        }
        with self._lock:
            self._records.append(item)
            self._records = self._records[-self.max_records :]
        return item

    def latest(self):
        with self._lock:
            return dict(self._records[-1]) if self._records else {}

    def summary_lines(self):
        latest = self.latest()
        if not latest:
            return ["runtime metrics: no turns recorded yet"]
        parts = [
            f"last turn: {latest.get('duration_ms', 0)}ms",
        ]
        for key in ("route_duration_ms", "first_ack_ms", "llm_first_token_ms", "tool_duration_ms"):
            if key in latest:
                parts.append(f"{key.replace('_', ' ')}: {latest[key]}ms")
        return ["runtime metrics: " + ", ".join(parts)]


class TurnFeedbackRuntime:
    def __init__(self, event_bus, config=None, metrics: RuntimeMetrics | None = None):
        self.event_bus = event_bus
        self.config = config
        self.metrics = metrics or RuntimeMetrics()
        self._lock = threading.RLock()
        self._turns: dict[str, TurnRecord] = {}
        self._timers: dict[str, list[threading.Timer]] = {}

    @property
    def active_turns(self) -> int:
        """Count of turns that have been started but not yet completed or failed."""
        with self._lock:
            return sum(
                1 for t in self._turns.values()
                if not t.cancelled and t.completed_at == 0.0
            )

    def start_turn(self, text: str, source: str = "user") -> TurnRecord:
        turn = TurnRecord(turn_id=str(uuid.uuid4()), text=text, source=source)
        with self._lock:
            self._turns[turn.turn_id] = turn
        self._publish("turn_started", turn, {"text": text, "source": source})
        return turn

    def emit_ack(self, turn: TurnRecord, text: str):
        if not text or self._is_cancelled(turn.turn_id):
            return
        turn.metrics.setdefault("first_ack_ms", round((time.monotonic() - turn.started_at) * 1000, 1))
        self._publish("assistant_ack", turn, {"text": text})

    def emit_progress(self, turn: TurnRecord, text: str):
        if not text or self._is_cancelled(turn.turn_id):
            return
        # Suppress if turn already finished (timer raced with complete_turn).
        if turn.completed_at > 0.0:
            return
        # Suppress if LLM has already started streaming — the response is
        # already being spoken and a progress phrase would interrupt it.
        if "llm_first_token_ms" in turn.metrics:
            return
        self._publish("assistant_progress", turn, {"text": text})

    def emit_tool_started(self, turn: TurnRecord, name: str, args: dict | None = None):
        self._publish("tool_started", turn, {"tool_name": name, "args": dict(args or {})})

    def emit_tool_finished(self, turn: TurnRecord, name: str, ok: bool, duration_ms: float, error: str = ""):
        turn.metrics["tool_duration_ms"] = round(
            float(turn.metrics.get("tool_duration_ms", 0.0)) + float(duration_ms),
            1,
        )
        self._publish(
            "tool_finished",
            turn,
            {"tool_name": name, "ok": bool(ok), "duration_ms": round(duration_ms, 1), "error": error},
        )

    def emit_llm_started(self, turn: TurnRecord, lane: str = "chat"):
        self._publish("llm_started", turn, {"lane": lane})

    def emit_llm_first_token(self, turn: TurnRecord):
        turn.metrics.setdefault("llm_first_token_ms", round((time.monotonic() - turn.started_at) * 1000, 1))
        # LLM is streaming — kill any pending progress timers now so "One moment."
        # can't fire while the actual response is already being spoken.
        self.cancel_progress(turn.turn_id)
        self._publish("llm_first_token", turn, {})

    def start_progress_timers(self, turn: TurnRecord, phrases: list[str] | None = None):
        delays = self._progress_delays()
        if not delays:
            return
        phrases = phrases or [
            "One moment.",
            "Still on it.",
        ]
        timers = []
        for index, delay in enumerate(delays):
            phrase = phrases[min(index, len(phrases) - 1)]
            timer = threading.Timer(delay, self.emit_progress, args=(turn, phrase))
            timer.daemon = True
            timer.start()
            timers.append(timer)
        with self._lock:
            self._timers.setdefault(turn.turn_id, []).extend(timers)

    def complete_turn(self, turn: TurnRecord, response: str, speak_final: bool = True, ok: bool = True):
        self.cancel_progress(turn.turn_id)
        turn.completed_at = time.monotonic()
        record = self.metrics.record(turn, response=response, ok=ok)
        self._publish(
            "turn_completed",
            turn,
            {"response": response, "speak_final": bool(speak_final), "ok": bool(ok), "metrics": record},
        )

    def fail_turn(self, turn: TurnRecord, error: str):
        self.cancel_progress(turn.turn_id)
        turn.completed_at = time.monotonic()
        record = self.metrics.record(turn, response=error, ok=False)
        self._publish("turn_failed", turn, {"error": error, "metrics": record})

    def cancel_turn(self, turn_id: str):
        with self._lock:
            turn = self._turns.get(turn_id)
            if turn:
                turn.cancelled = True
        self.cancel_progress(turn_id)

    def cancel_progress(self, turn_id: str):
        with self._lock:
            timers = self._timers.pop(turn_id, [])
        for timer in timers:
            timer.cancel()

    def _publish(self, event_type: str, turn: TurnRecord, payload: dict[str, Any]):
        data = {
            "turn_id": turn.turn_id,
            "source": turn.source,
            "elapsed_ms": round((time.monotonic() - turn.started_at) * 1000, 1),
            **payload,
        }
        self.event_bus.publish(event_type, data)

    def _is_cancelled(self, turn_id: str):
        with self._lock:
            turn = self._turns.get(turn_id)
            return bool(turn and turn.cancelled)

    def _progress_delays(self):
        value = None
        if self.config and hasattr(self.config, "get"):
            value = self.config.get("conversation.progress_delays_s", None)
        if value is None:
            value = [2.5, 6.0, 12.0]
        if isinstance(value, str):
            value = [part.strip() for part in value.split(",")]
        try:
            return [max(0.1, float(item)) for item in value]
        except Exception:
            return [2.5, 6.0, 12.0]
