"""TurnGatedMemoryExtractor — queues turns for Mem0 extraction after active_turns == 0.

Extraction is asynchronous and fires only between voice turns.
Failures are logged and silently discarded — never block the main pipeline.
"""
from __future__ import annotations

import threading

from core.logger import logger


class TurnGatedMemoryExtractor:
    def __init__(self, mem0_client, turn_feedback):
        self._mem0 = mem0_client
        self._feedback = turn_feedback
        self._pending: list[dict] = []
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._running = True
        self._trigger = threading.Event()
        self._start_worker()

    def queue_turn(self, user_text: str, assistant_text: str, user_id: str = "default") -> None:
        """Queue a completed turn for async Mem0 extraction. Non-blocking."""
        with self._lock:
            self._pending.append({
                "user": user_text,
                "assistant": assistant_text,
                "user_id": user_id,
            })
        self._trigger.set()

    def stop(self) -> None:
        self._running = False
        self._trigger.set()

    def _start_worker(self) -> None:
        self._worker = threading.Thread(
            target=self._drain_loop, name="mem0-extractor", daemon=True
        )
        self._worker.start()

    def _drain_loop(self) -> None:
        import time
        while self._running:
            self._trigger.wait(timeout=5.0)
            self._trigger.clear()

            if not self._running:
                return

            # Wait until no active voice turn
            while getattr(self._feedback, "active_turns", 0) > 0:
                time.sleep(0.5)
                if not self._running:
                    return

            with self._lock:
                turns = list(self._pending)
                self._pending.clear()

            for turn in turns:
                try:
                    self._mem0.add(
                        [
                            {"role": "user", "content": turn["user"]},
                            {"role": "assistant", "content": turn["assistant"]},
                        ],
                        user_id=turn["user_id"],
                    )
                    logger.debug("[mem0] Extracted facts for turn.")
                except Exception as exc:
                    logger.warning("[mem0] Extraction failed: %s", exc)
