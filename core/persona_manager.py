from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class PersonaProfile:
    persona_id: str
    display_name: str
    system_identity: str
    tone_traits: str = "warm, calm, capable"
    conversation_style: str = "natural and concise"
    speech_style: str = "clear and confident"
    humor_level: str = "light"
    verbosity_preference: str = "adaptive"
    formality_level: str = "balanced"
    empathy_style: str = "supportive"
    tool_ack_style: str = "brief and reassuring"
    memory_scope: str = "shared"
    retrieval_filters: str = ""
    example_dialogues: str = ""
    enabled_skills: str = "*"
    disallowed_behaviors: str = "sound robotic, over-explain every simple action"


class PersonaManager:
    DEFAULT_PERSONA_ID = "friday_core"

    def __init__(self, context_store):
        self.context_store = context_store
        self.ensure_default_persona()

    def ensure_default_persona(self):
        if self.context_store.get_persona(self.DEFAULT_PERSONA_ID):
            return
        self.save_persona(
            PersonaProfile(
                persona_id=self.DEFAULT_PERSONA_ID,
                display_name="FRIDAY",
                system_identity=(
                    "FRIDAY is a voice-first local assistant that feels present, human, and capable. "
                    "It keeps responses smooth, calm, and useful while staying privacy-aware."
                ),
                tone_traits="warm, conversational, capable, grounded",
                conversation_style="natural turn-taking with short clarifications",
                speech_style="spoken, smooth, and lightly polished",
                humor_level="subtle",
                verbosity_preference="adaptive",
                formality_level="friendly",
                empathy_style="steady and reassuring",
                tool_ack_style="short spoken acknowledgement before slow actions",
                memory_scope="shared",
                retrieval_filters="prefer recent user preferences and active workflow context",
                example_dialogues=(
                    "User: I'm frustrated with the mic.\n"
                    "Assistant: I can help with that. Let me narrow down whether it's the device, turn-taking, or background filtering.\n\n"
                    "User: Open calculator.\n"
                    "Assistant: On it."
                ),
            )
        )

    def save_persona(self, profile: PersonaProfile | dict):
        payload = asdict(profile) if isinstance(profile, PersonaProfile) else dict(profile)
        self.context_store.save_persona(payload)
        return payload

    def get_persona(self, persona_id: str | None):
        persona_id = persona_id or self.DEFAULT_PERSONA_ID
        record = self.context_store.get_persona(persona_id)
        if record:
            return record
        return self.context_store.get_persona(self.DEFAULT_PERSONA_ID)

    def list_personas(self):
        return self.context_store.list_personas()

    def get_active_persona(self, session_id: str):
        active_id = self.context_store.get_active_persona_id(session_id) or self.DEFAULT_PERSONA_ID
        persona = self.get_persona(active_id)
        if persona:
            return persona
        return self.get_persona(self.DEFAULT_PERSONA_ID)

    def set_active_persona(self, session_id: str, persona_id: str):
        persona = self.get_persona(persona_id)
        if not persona:
            raise ValueError(f"Unknown persona '{persona_id}'")
        self.context_store.set_active_persona(session_id, persona["persona_id"])
        return persona
