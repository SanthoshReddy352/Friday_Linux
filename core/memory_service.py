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

from core.logger import logger


class MemoryService:
    """Single read/write surface over ContextStore + MemoryBroker."""

    def __init__(self, context_store, memory_broker=None, mem0_client=None, extractor=None):
        self._store = context_store
        self._broker = memory_broker
        self._mem0 = mem0_client       # None when Mem0 is unavailable
        self._extractor = extractor    # TurnGatedMemoryExtractor

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
        bundle = {}
        if self._broker is not None and session_id:
            bundle = self._broker.build_context_bundle(query, session_id) or {}

        # Inject Mem0 facts — ~15-30ms retrieval, ~60 tokens injected
        if self._mem0 and query:
            try:
                results = self._mem0.search(query, user_id="default", limit=5)
                facts = [r["memory"] for r in (results.get("results") or [])]
                if facts:
                    bundle["user_facts"] = "\n".join(facts)
            except Exception as exc:
                logger.debug("[mem0] Retrieval failed (non-fatal): %s", exc)

        # Port #9: inject typed knowledge-graph entities relevant to the query
        if query:
            try:
                from core.memory.graph import GraphRecall  # noqa: PLC0415
                fragment = GraphRecall(self).build_fragment(query)
                if fragment:
                    bundle["knowledge_graph"] = fragment
            except Exception as exc:
                logger.debug("[graph] recall failed (non-fatal): %s", exc)

        return bundle

    def record_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        trace_id: str = "",
        store_turns: bool = False,
    ) -> None:
        """Notify the memory pipeline that a turn has completed.

        Two responsibilities:
          1. Queue the (user, assistant) pair for async Mem0 fact extraction.
          2. Optionally persist the turn rows to ContextStore. Off by default
             because `app.emit_message` already calls `append_turn` on both
             user and assistant emissions in the live runtime; passing
             ``store_turns=True`` is only useful when calling this method
             outside the normal emit path (e.g. batch ingestion / tests).
        """
        if not session_id:
            return
        if store_turns:
            if user_text:
                self._store.append_turn(session_id, "user", user_text, source=trace_id or None)
            if assistant_text:
                self._store.append_turn(session_id, "assistant", assistant_text, source=trace_id or None)

        # Queue Mem0 extraction (fires only after active_turns == 0)
        if self._extractor and user_text and assistant_text:
            try:
                self._extractor.queue_turn(user_text, assistant_text, user_id="default")
            except Exception as exc:
                logger.debug("[mem0] queue_turn failed (non-fatal): %s", exc)

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

    # ------------------------------------------------------------------
    # Port #2 — Commitments facade
    # ------------------------------------------------------------------

    def record_commitment(
        self,
        what: str,
        session_id: str = "",
        when_due: str = "",
        priority: str = "medium",
        retry_policy: str = "none",
        assigned_to: str = "friday",
    ) -> str:
        return self._store.record_commitment(
            what,
            session_id=session_id or "",
            when_due=when_due,
            priority=priority,
            retry_policy=retry_policy,
            assigned_to=assigned_to,
        )

    def complete_commitment(self, commitment_id: str, result: str = "") -> bool:
        return self._store.complete_commitment(commitment_id, result=result)

    def fail_commitment(self, commitment_id: str, result: str = "") -> bool:
        return self._store.fail_commitment(commitment_id, result=result)

    def cancel_commitment(self, commitment_id: str) -> bool:
        return self._store.cancel_commitment(commitment_id)

    def list_pending_commitments(self, session_id: str = "", limit: int = 20) -> list:
        return self._store.list_pending_commitments(session_id=session_id, limit=limit)

    def list_all_commitments(self, session_id: str = "", limit: int = 50) -> list:
        return self._store.list_all_commitments(session_id=session_id, limit=limit)

    def get_commitment(self, commitment_id: str) -> dict | None:
        return self._store.get_commitment(commitment_id)

    # ------------------------------------------------------------------
    # Port #3 — Audit trail facade
    # ------------------------------------------------------------------

    def log_audit_event(
        self,
        tool_name: str,
        ok: bool,
        args_summary: str = "",
        output_summary: str = "",
        exec_ms: int = 0,
        session_id: str = "",
        agent_id: str = "friday",
        authority_decision: str = "allowed",
    ) -> None:
        try:
            self._store.log_audit_event(
                tool_name=tool_name,
                ok=ok,
                args_summary=args_summary,
                output_summary=output_summary,
                exec_ms=exec_ms,
                session_id=session_id,
                agent_id=agent_id,
                authority_decision=authority_decision,
            )
        except Exception as exc:
            logger.debug("[audit] log failed (non-fatal): %s", exc)

    def query_audit_events(
        self, tool_name: str = "", limit: int = 50, session_id: str = ""
    ) -> list:
        try:
            return self._store.query_audit_events(
                tool_name=tool_name, limit=limit, session_id=session_id
            )
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Port #9 — Knowledge graph facade
    # ------------------------------------------------------------------

    def upsert_entity(
        self,
        name: str,
        entity_type: str = "concept",
        properties: dict | None = None,
        session_id: str = "",
    ) -> str:
        return self._store.upsert_entity(
            name, entity_type=entity_type, properties=properties, session_id=session_id
        )

    def add_entity_fact(
        self,
        subject_id: str,
        predicate: str,
        obj: str,
        confidence: float = 0.7,
        source: str = "",
    ) -> str:
        return self._store.add_entity_fact(
            subject_id, predicate, obj, confidence=confidence, source=source
        )

    def add_entity_relationship(
        self, from_id: str, to_id: str, rel_type: str = "related_to", properties: dict | None = None
    ) -> str:
        return self._store.add_entity_relationship(
            from_id, to_id, rel_type=rel_type, properties=properties
        )

    def query_entity_facts(self, subject_id: str) -> list:
        return self._store.query_entity_facts(subject_id)

    def find_entities(self, name_fragment: str = "", entity_type: str = "") -> list:
        return self._store.find_entities(name_fragment=name_fragment, entity_type=entity_type)

    # ------------------------------------------------------------------
    # Port #7 — Goals facade
    # ------------------------------------------------------------------

    def create_goal(
        self,
        title: str,
        description: str = "",
        level: str = "task",
        parent_id: str = "",
        time_horizon: str = "weekly",
        tags: list | None = None,
        session_id: str = "",
    ) -> str:
        return self._store.create_goal(
            title,
            description=description,
            level=level,
            parent_id=parent_id,
            time_horizon=time_horizon,
            tags=tags,
            session_id=session_id,
        )

    def update_goal_score(self, goal_id: str, score: float, note: str = "") -> bool:
        return self._store.update_goal_score(goal_id, score, note=note)

    def update_goal_status(self, goal_id: str, status: str) -> bool:
        return self._store.update_goal_status(goal_id, status)

    def list_goals(self, session_id: str = "", status: str = "active") -> list:
        return self._store.list_goals(session_id=session_id, status=status)

    def get_goal(self, goal_id: str) -> dict | None:
        return self._store.get_goal(goal_id)

    # ------------------------------------------------------------------
    # Port #6 — Agent messages facade
    # ------------------------------------------------------------------

    def post_agent_message(
        self,
        from_agent: str,
        to_agent: str,
        msg_type: str,
        content: str,
        priority: str = "normal",
        requires_response: bool = False,
        deadline: str = "",
    ) -> str:
        return self._store.post_agent_message(
            from_agent, to_agent, msg_type, content,
            priority=priority, requires_response=requires_response, deadline=deadline,
        )

    def list_agent_messages(self, to_agent: str = "", status: str = "pending") -> list:
        return self._store.list_agent_messages(to_agent=to_agent, status=status)

    def ack_agent_message(self, msg_id: str) -> bool:
        return self._store.ack_agent_message(msg_id)

    # ------------------------------------------------------------------
    # Working artifact façade
    # ------------------------------------------------------------------

    def save_artifact(self, session_id: str, artifact) -> None:
        self._store.save_artifact(session_id, artifact)

    def get_artifact(self, session_id: str):
        return self._store.get_artifact(session_id)

    # ------------------------------------------------------------------
    # Reference registry façade
    # ------------------------------------------------------------------

    def save_reference(self, session_id: str, key: str, value: str) -> None:
        self._store.save_reference(session_id, key, value)

    def get_reference(self, session_id: str, key: str) -> "str | None":
        return self._store.get_reference(session_id, key)

    def get_all_references(self, session_id: str) -> dict:
        return self._store.get_all_references(session_id)
