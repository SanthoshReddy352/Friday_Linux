"""MemoryService — unified memory facade.

Phase 2 of the v2 architecture (docs/friday_architecture.md §12).

Today, twelve different sites read or write `app.context_store.*` directly.
That makes the storage layer impossible to evolve safely — any schema
change in `ContextStore` is a multi-file change with no contract
enforcement. `MemoryService` is the stable facade those sites should
target instead. Internally it delegates to:

  * `ContextStore` for SQLite-backed persistent state (turns, sessions,
    workflows, facts, memory items, online-consent log, persona).
  * `MemoryBroker` for the typed memory tiers (episodic / semantic /
    procedural) and the per-turn context bundle.

The doc lists the v2 contract — `build_context_bundle`, `record_turn`,
`learn_fact`, `recall_semantic`, `top_capabilities`,
`get_active_workflow`, `save_workflow_state`, `clear_workflow_state`.
For migration safety the facade also exposes the legacy operations
(pending-online, session-state, store_fact, store_memory_item,
log_online_permission) so existing callers can be redirected without
behaviour changes. As callers migrate, the legacy methods become
obviously unused and can be deleted in a future pass.
"""
from __future__ import annotations

from typing import Any


class MemoryService:
    """Single read/write surface over ContextStore + MemoryBroker."""

    def __init__(self, context_store, memory_broker=None):
        self._store = context_store
        self._broker = memory_broker

    # Convenience accessor — used by code that still needs the raw store
    # during the migration. New code should NOT use this; it exists to
    # make the ContextStore reachable from a single facade so the next
    # cleanup pass can find every remaining site.
    @property
    def context_store(self):
        return self._store

    @property
    def memory_broker(self):
        return self._broker

    # ------------------------------------------------------------------
    # Doc §12 — the v2 public contract
    # ------------------------------------------------------------------

    def build_context_bundle(self, session_id: str, query: str) -> dict:
        if self._broker is None or not session_id:
            return {}
        return self._broker.build_context_bundle(query, session_id) or {}

    def record_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        trace_id: str = "",
    ) -> None:
        if not session_id:
            return
        if user_text:
            self._store.append_turn(session_id, "user", user_text, source=trace_id or None)
        if assistant_text:
            self._store.append_turn(session_id, "assistant", assistant_text, source=trace_id or None)

    def learn_fact(
        self,
        session_id: str,
        key: str,
        value: str,
        confidence: float = 0.7,
        namespace: str = "general",
    ) -> None:
        if not key:
            return
        # ContextStore.store_fact accepts confidence indirectly via the
        # `value` payload only when callers preformat it. The facade
        # stores both the bare value and a typed semantic memory item so
        # MemoryBroker.semantic can recall it later with the confidence.
        self._store.store_fact(key, value, session_id=session_id, namespace=namespace)
        if self._broker is not None:
            try:
                self._broker.semantic.upsert(
                    session_id=session_id,
                    key=key,
                    value=value,
                    confidence=float(confidence),
                )
            except Exception:
                pass

    def forget_fact(self, item_id: str) -> None:
        if not item_id:
            return
        self._store.delete_memory_item(item_id)

    def record_outcome(
        self, capability_name: str, context_features: dict | None, success: bool
    ) -> None:
        if self._broker is not None and hasattr(self._broker, "record_capability_outcome"):
            self._broker.record_capability_outcome(capability_name, context_features, success)

    def top_capabilities(self, limit: int = 3) -> list[str]:
        if self._broker is None:
            return []
        proc = getattr(self._broker, "procedural", None)
        if proc is None:
            return []
        try:
            return proc.top_capabilities(limit=limit) or []
        except Exception:
            return []

    def recall_semantic(self, query: str, session_id: str = "", limit: int = 3) -> list[dict]:
        return list(self._store.semantic_recall(query, session_id, limit=limit) or [])

    def get_active_workflow(self, session_id: str, workflow_name: str | None = None) -> dict | None:
        return self._store.get_active_workflow(session_id, workflow_name=workflow_name)

    def save_workflow_state(self, session_id: str, name: str, state: dict) -> None:
        self._store.save_workflow_state(session_id, name, state)

    def clear_workflow_state(self, session_id: str, name: str) -> None:
        self._store.clear_workflow_state(session_id, name)

    # ------------------------------------------------------------------
    # Legacy operations — kept on the facade so callers can migrate off
    # `app.context_store.*` without behaviour changes. These are wrapped
    # rather than re-implemented; the v2 doc folds online-consent and
    # session-state ownership into ConsentGate / TurnContext but those
    # migrations are out of scope for Phase 2.
    # ------------------------------------------------------------------

    def get_session_state(self, session_id: str) -> dict:
        return self._store.get_session_state(session_id) or {}

    def save_session_state(self, session_id: str, state: dict) -> None:
        self._store.save_session_state(session_id, state)

    def set_pending_online(self, session_id: str, payload: dict) -> None:
        self._store.set_pending_online(session_id, payload)

    def clear_pending_online(self, session_id: str) -> None:
        self._store.clear_pending_online(session_id)

    def log_online_permission(
        self, session_id: str, tool_name: str, decision: str, reason: str = ""
    ) -> None:
        self._store.log_online_permission(session_id, tool_name, decision, reason=reason)

    def store_fact(
        self, key: str, value: Any, session_id: str | None = None, namespace: str = "general"
    ) -> None:
        self._store.store_fact(key, value, session_id=session_id, namespace=namespace)

    def store_memory_item(
        self,
        session_id: str,
        content: str,
        memory_type: str = "episodic",
        persona_id: str = "",
        sensitivity: str = "safe_auto",
        metadata: dict | None = None,
    ) -> None:
        self._store.store_memory_item(
            session_id,
            content,
            memory_type=memory_type,
            persona_id=persona_id,
            sensitivity=sensitivity,
            metadata=metadata,
        )
