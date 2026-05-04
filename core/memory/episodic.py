"""EpisodicMemory — verbatim conversation turns with time-decay pruning.

Phase 7: 30-day rolling window store backed by ContextStore's `turns` table.
"""
from __future__ import annotations

from typing import List


class EpisodicMemory:
    """Store and retrieve verbatim conversation turns.

    Backed by ContextStore's SQLite `turns` table.  Provides time-decay
    aware retrieval and optional rolling-window pruning.
    """

    ROLLING_WINDOW_DAYS = 30

    def __init__(self, context_store):
        self._store = context_store

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, session_id: str, role: str, text: str, source: str | None = None) -> None:
        """Append a turn to the episodic log."""
        self._store.append_turn(session_id, role, text, source=source)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall(self, session_id: str, limit: int = 8) -> List[dict]:
        """Return recent turns as plain dicts."""
        summary = self._store.summarize_session(session_id, limit=limit)
        if isinstance(summary, list):
            return summary
        # summarize_session may return a formatted string — wrap it
        if summary:
            return [{"role": "context", "text": str(summary)}]
        return []

    # ------------------------------------------------------------------
    # Prune
    # ------------------------------------------------------------------

    def prune(self, session_id: str, days: int | None = None) -> int:
        """Delete turns older than *days* days from the episodic log.

        Returns the number of rows deleted.  Uses ContextStore's prune helper
        if available; otherwise silently no-ops.
        """
        cutoff = days or self.ROLLING_WINDOW_DAYS
        fn = getattr(self._store, "prune_old_turns", None)
        if callable(fn):
            return fn(session_id, older_than_days=cutoff)
        return 0
