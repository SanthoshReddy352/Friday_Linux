"""MemoryBroker — builds context bundles for each turn.

Phase 7: Upgraded to use the three typed memory stores (episodic, semantic,
procedural) from core.memory, while remaining backward-compatible with the
existing ContextStore interface.
"""
from __future__ import annotations

from core.memory.episodic import EpisodicMemory
from core.memory.semantic import SemanticMemory
from core.memory.procedural import ProceduralMemory


class MemoryBroker:
    def __init__(self, context_store, persona_manager):
        self.context_store = context_store
        self.persona_manager = persona_manager
        self.episodic = EpisodicMemory(context_store)
        self.semantic = SemanticMemory(context_store)
        self.procedural = ProceduralMemory(context_store)

    def build_context_bundle(self, query: str, session_id: str) -> dict:
        """Build a rich context bundle for capability planning.

        Returns a dict consumed by CapabilityBroker and ConversationAgent.
        Keys are stable — adding new keys here is non-breaking.
        """
        persona = self.persona_manager.get_active_persona(session_id)
        persona_id = persona.get("persona_id") if persona else ""

        return {
            "persona": persona or {},
            "session_summary": self.context_store.summarize_session(session_id, limit=8),
            "active_workflow": self.context_store.get_workflow_summary(session_id),
            "semantic_recall": self.context_store.semantic_recall(query, session_id, limit=4),
            "durable_memories": self.context_store.recent_memory_items(session_id, limit=6, persona_id=persona_id),
            "session_state": self.context_store.get_session_state(session_id) or {},
            # Phase 7 additions
            "top_capabilities": self.procedural.top_capabilities(limit=3),
        }

    def curate(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        persona_id: str = "",
    ) -> None:
        """Extract and store memories from a completed turn.

        Currently uses a heuristic: sentences containing "remember", "my name
        is", "I prefer", etc. are extracted as semantic facts.  Phase 9 will
        upgrade this to an LLM-based extraction pass.
        """
        import re

        REMEMBER_PATTERNS = (
            r"remember (?:that )?(.+)",
            r"(?:my name is|i am called|call me)\s+(\w+)",
            r"i (?:prefer|like|hate|love|always|never)\s+(.+)",
            r"my (?:favorite|preferred)\s+.+\s+is\s+(.+)",
        )
        for sentence in re.split(r"[.!?]\s+", user_text):
            for pattern in REMEMBER_PATTERNS:
                m = re.search(pattern, sentence.strip().lower())
                if m:
                    value = m.group(1).strip().rstrip(".")
                    key = sentence[:40].strip()
                    self.semantic.remember(session_id, key, value, confidence=0.9, persona_id=persona_id)
                    break

    def record_capability_outcome(self, capability_name: str, context_features: dict | None, success: bool) -> None:
        """Delegate to ProceduralMemory for bandit-style success tracking."""
        self.procedural.record_outcome(capability_name, context_features, success)
