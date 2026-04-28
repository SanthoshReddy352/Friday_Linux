from __future__ import annotations


class MemoryBroker:
    def __init__(self, context_store, persona_manager):
        self.context_store = context_store
        self.persona_manager = persona_manager

    def build_context_bundle(self, query: str, session_id: str):
        persona = self.persona_manager.get_active_persona(session_id)
        persona_id = persona.get("persona_id") if persona else ""
        return {
            "persona": persona or {},
            "session_summary": self.context_store.summarize_session(session_id, limit=8),
            "active_workflow": self.context_store.get_workflow_summary(session_id),
            "semantic_recall": self.context_store.semantic_recall(query, session_id, limit=4),
            "durable_memories": self.context_store.recent_memory_items(session_id, limit=6, persona_id=persona_id),
            "session_state": self.context_store.get_session_state(session_id) or {},
        }
