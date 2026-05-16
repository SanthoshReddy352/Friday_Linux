"""Global interrupt bus (Batch 3 / Issue 3).

A lightweight pub/sub coordination point for cancellation signals. The
existing primitives (``TaskRunner.cancel_nowait``, ``tts.stop``,
``WorkflowOrchestrator.cancel_active_workflow``) keep their behaviour —
the bus is **additive**, giving every subsystem a single place to
listen for "the user said stop" without coupling through ``FridayApp``.

Why it exists:
    Before, saying ``enough`` while TTS was playing called ``tts.stop()``
    and nothing else. The underlying LLM kept generating, the workflow
    state remained pending, the next turn picked up a dirty DialogState.
    A single bus signal now reaches DialogState (resets pending fields),
    the workflow orchestrator (cancels active workflow), and any future
    subscriber that needs to react.

Scopes
------
    ``"tts"``       — TTS subsystem (queue flush, lock release).
    ``"inference"`` — Long-running LLM generation (cooperative abort).
    ``"workflow"``  — Multi-turn workflow state (cancel + slot clear).
    ``"all"``       — Every subscriber regardless of subscribed scope.

A subscriber registered for one scope also receives ``"all"`` signals.

Generation counter
------------------
    Every ``signal()`` bumps a monotonic counter. Callers that started
    work before subscribing (e.g. an inference loop) capture the counter
    at start and call ``signaled_since(starting_gen)`` periodically; this
    avoids the race where the signal fires before the subscriber installs
    its callback.

Threading
---------
    The bus is thread-safe. Subscribers fire synchronously in the
    emitter's thread *outside* the internal lock so a slow callback
    never blocks other emitters. Exceptions in subscribers are logged
    and swallowed — one broken subscriber must not stop the others.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Literal

from core.logger import logger

Scope = Literal["tts", "inference", "workflow", "all"]

_VALID_SCOPES: frozenset[str] = frozenset({"tts", "inference", "workflow", "all"})


@dataclass(frozen=True)
class InterruptSignal:
    reason: str
    scope: Scope
    timestamp: float
    generation: int


SubscriberCallback = Callable[[InterruptSignal], None]
Unsubscribe = Callable[[], None]


class InterruptBus:
    """Process-wide cancellation coordination point.

    Use the module-level ``get_interrupt_bus()`` accessor in production
    code. Construct your own instance only in tests that need isolation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[Scope, list[SubscriberCallback]] = {
            "tts": [],
            "inference": [],
            "workflow": [],
            "all": [],
        }
        self._generation = 0
        self._last_signal: InterruptSignal | None = None

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, scope: Scope, callback: SubscriberCallback) -> Unsubscribe:
        """Register ``callback`` for ``scope``. Returns an unsubscribe handle."""
        if scope not in _VALID_SCOPES:
            raise ValueError(f"invalid scope: {scope!r}")
        with self._lock:
            self._subscribers[scope].append(callback)

        def _unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers[scope].remove(callback)
                except ValueError:
                    pass

        return _unsubscribe

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def signal(self, reason: str, scope: Scope = "all") -> InterruptSignal:
        """Broadcast an interrupt signal. Returns the signal record."""
        if scope not in _VALID_SCOPES:
            raise ValueError(f"invalid scope: {scope!r}")
        with self._lock:
            self._generation += 1
            sig = InterruptSignal(
                reason=reason,
                scope=scope,
                timestamp=time.time(),
                generation=self._generation,
            )
            self._last_signal = sig
            # Snapshot subscribers under the lock; fire outside.
            if scope == "all":
                targets: list[SubscriberCallback] = []
                for callbacks in self._subscribers.values():
                    targets.extend(callbacks)
            else:
                targets = list(self._subscribers.get(scope, ()))
                # "all" subscribers always receive scoped signals too.
                targets.extend(self._subscribers.get("all", ()))
        for cb in targets:
            try:
                cb(sig)
            except Exception as exc:
                # A misbehaving subscriber must never stop the rest.
                logger.warning("[interrupt-bus] subscriber raised: %s", exc)
        return sig

    # ------------------------------------------------------------------
    # Polling helpers (for cooperative cancel in long-running code)
    # ------------------------------------------------------------------

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def last_signal(self) -> InterruptSignal | None:
        with self._lock:
            return self._last_signal

    def signaled_since(self, starting_generation: int) -> bool:
        """Return True iff at least one signal has fired since the given
        generation. Use ``bus.generation`` to capture the starting value
        before launching long-running work.
        """
        with self._lock:
            return self._generation > starting_generation

    # ------------------------------------------------------------------
    # Test affordance
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all subscribers and reset the generation counter. Used
        by tests; production code should not call this."""
        with self._lock:
            for scope in self._subscribers:
                self._subscribers[scope] = []
            self._generation = 0
            self._last_signal = None


_BUS = InterruptBus()


def get_interrupt_bus() -> InterruptBus:
    """Return the process-wide ``InterruptBus`` singleton."""
    return _BUS
