"""SemanticMemory — structured facts with confidence scores.

Phase 7: {key, value, confidence} store. Facts with confidence < PRUNE_FLOOR
are candidates for removal. Backed by ContextStore's `memory_items` table.
"""
from __future__ import annotations

import json
import uuid
from typing import List


class SemanticMemory:
    """Store and retrieve structured, key-value facts.

    Each fact has a confidence score (0.0–1.0).  Lower-confidence facts
    can be pruned to keep the store clean.  Facts are surfaced during
    semantic recall alongside episodic memories.
    """

    PRUNE_FLOOR = 0.5

    def __init__(self, context_store):
        self._store = context_store

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def remember(
        self,
        session_id: str,
        key: str,
        value: str,
        confidence: float = 1.0,
        persona_id: str = "",
    ) -> None:
        """Upsert a fact.  If the same key exists it is overwritten."""
        item_id = f"sem:{session_id}:{key}"
        content = f"{key}: {value}"
        self._store.store_memory_item(
            session_id=session_id,
            content=content,
            memory_type="semantic",
            persona_id=persona_id,
            metadata={
                "item_id": item_id,
                "key": key,
                "value": value,
                "confidence": round(float(confidence), 4),
            },
        )

    def forget(self, session_id: str, key: str) -> None:
        """Remove a specific fact from the store."""
        fn = getattr(self._store, "delete_memory_item", None)
        if callable(fn):
            item_id = f"sem:{session_id}:{key}"
            fn(item_id)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recall(self, session_id: str, query: str, limit: int = 4) -> List[dict]:
        """Return semantically relevant facts for *query*."""
        return self._store.semantic_recall(query, session_id, limit=limit) or []

    def recent(self, session_id: str, limit: int = 6, persona_id: str = "") -> List[dict]:
        """Return recently updated semantic memories."""
        all_items = self._store.recent_memory_items(session_id, limit=limit * 2, persona_id=persona_id) or []
        return [item for item in all_items if item.get("memory_type") == "semantic"][:limit]

    # ------------------------------------------------------------------
    # Prune
    # ------------------------------------------------------------------

    def prune(self, session_id: str, min_confidence: float | None = None) -> int:
        """Remove facts below *min_confidence*.  Returns count removed."""
        floor = min_confidence if min_confidence is not None else self.PRUNE_FLOOR
        fn = getattr(self._store, "prune_low_confidence_memories", None)
        if callable(fn):
            return fn(session_id, min_confidence=floor)
        # Fallback: scan and delete manually
        items = self._store.recent_memory_items(session_id, limit=500) or []
        removed = 0
        delete_fn = getattr(self._store, "delete_memory_item", None)
        for item in items:
            if item.get("memory_type") != "semantic":
                continue
            meta = item.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            conf = float(meta.get("confidence", 1.0))
            if conf < floor and callable(delete_fn):
                delete_fn(item["item_id"])
                removed += 1
        return removed
