"""TurnContext — unified per-turn ephemeral state.

Phase 1 of the v2 architecture (docs/friday_architecture.md §13).

`TurnContext` is the per-turn handle that consolidates state previously
scattered across `RoutingState`, `DialogState`, and `SpeechCoordinator`'s
`SpeechTurnState`. Today it works as an additive view: the underlying
state owners (`RoutingState` on `app.routing_state`, `DialogState` on
`app.dialog_state`) remain authoritative, and `TurnContext` exposes a
unified read/write surface so future planning / orchestration code can
pass a single object instead of five.

A contextvar (`current_turn_var`) is bound by `TurnManager.handle_turn`
so any code running inside the turn can grab the active context with
`current_turn()`.
"""

from __future__ import annotations

import contextvars
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


current_turn_var: contextvars.ContextVar["TurnContext | None"] = contextvars.ContextVar(
    "friday_turn_context", default=None
)


def current_turn() -> "TurnContext | None":
    """Return the TurnContext bound to the active turn, or None."""
    return current_turn_var.get()


@dataclass
class TurnContext:
    """Per-turn ephemeral state handle.

    Identity fields are set at turn start and never mutate. The `voice_spoken`
    and `pending_*` properties delegate to the existing `RoutingState` /
    `DialogState` instances on the app, so legacy callers reading those
    objects directly still see consistent state.
    """

    turn_id: str
    session_id: str
    trace_id: str
    source: str
    text: str
    timestamp: float = field(default_factory=time.time)
    cancelled: bool = False
    timings: dict[str, float] = field(default_factory=dict)

    # Set by TurnManager so the property accessors below have something to
    # delegate to. Optional — TurnContext can be constructed in tests
    # without an app reference (the properties just no-op).
    _routing_state: Any = None
    _dialog_state: Any = None

    # ------------------------------------------------------------------
    # Voice-spoken (delegates to RoutingState.voice_already_spoken)
    # ------------------------------------------------------------------

    @property
    def voice_spoken(self) -> bool:
        if self._routing_state is None:
            return False
        return bool(self._routing_state.voice_already_spoken)

    @voice_spoken.setter
    def voice_spoken(self, value: bool) -> None:
        if self._routing_state is None:
            return
        if value:
            self._routing_state.mark_voice_spoken()
        else:
            self._routing_state.clear_voice_spoken()

    # ------------------------------------------------------------------
    # Dialog pending state (delegates to DialogState)
    # ------------------------------------------------------------------

    @property
    def pending_file_request(self):
        if self._dialog_state is None:
            return None
        return self._dialog_state.pending_file_request

    @property
    def pending_clarification(self):
        if self._dialog_state is None:
            return None
        return self._dialog_state.pending_clarification

    # ------------------------------------------------------------------
    # Timing helpers
    # ------------------------------------------------------------------

    def record_timing(self, label: str, duration_s: float) -> None:
        self.timings[label] = float(duration_s)

    @contextmanager
    def time_phase(self, label: str):
        start = time.monotonic()
        try:
            yield
        finally:
            self.record_timing(label, time.monotonic() - start)


@contextmanager
def turn_scope(ctx: TurnContext):
    """Bind *ctx* to the contextvar for the duration of the with-block."""
    token = current_turn_var.set(ctx)
    try:
        yield ctx
    finally:
        current_turn_var.reset(token)
