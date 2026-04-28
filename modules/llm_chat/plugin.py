from core.plugin_manager import FridayPlugin
from core.logger import logger
import re


FRIDAY_PERSONA = (
    "You are FRIDAY, an offline AI assistant inspired by the Iron Man AI. "
    "You are helpful, concise, and occasionally witty. "
    "You run entirely locally — no internet. "
    "Keep answers short (2-4 sentences) unless the user asks for details."
)

class LLMChatPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "LLMChat"
        self.on_load()

    def on_load(self):
        # This is the catch-all tool — Gemma routes here when no specific tool matches
        self.app.router.register_tool({
            "name": "llm_chat",
            "description": (
                "Answer a general question, have a conversation, or handle any request "
                "that doesn't fit a specific tool. Use this as the fallback for open-ended queries."
            ),
            "parameters": {
                "query": "string – the user's question or message"
            }
        }, self.handle_chat, capability_meta={
            "connectivity": "local",
            "latency_class": "generative",
            "permission_mode": "always_ok",
            "side_effect_level": "read",
            "streaming": True,
        })

        logger.info("LLMChatPlugin loaded.")

    def handle_chat(self, raw_text, args):
        query = args.get("query", raw_text).strip()
        if not query:
            return "I didn't catch that. Could you rephrase?"

        llm = self.app.router.get_llm()
        if llm is None:
            return "My language model isn't loaded right now. Please check the models directory."

        messages = self._build_messages(query)

        logger.debug(f"[LLMChat] Sending chat prompt for: '{query}'")
        try:
            answer = self._generate_reply(llm, messages)

            logger.info(f"[LLMChat] Response: {answer[:80]}...")
            return answer

        except Exception as e:
            logger.error(f"[LLMChat] Inference error: {e}")
            return "I ran into an issue generating a response. Please try again."

    def _generate_reply(self, llm, messages):
        if not hasattr(llm, "create_chat_completion"):
            res = llm(messages[-1]["content"], max_tokens=200, temperature=0.7)
            return res["choices"][0]["text"].strip()

        stream = llm.create_chat_completion(
            messages=messages,
            max_tokens=200,
            temperature=0.7,
            stream=True,
        )
        if isinstance(stream, dict):
            return stream["choices"][0]["message"]["content"].strip()

        parts = []
        sentence_buffer = ""
        first_token_seen = False
        for chunk in stream:
            delta = chunk["choices"][0].get("delta", {})
            content = delta.get("content")
            if not content:
                continue
            if not first_token_seen:
                first_token_seen = True
                feedback = getattr(self.app, "turn_feedback", None)
                turn = getattr(self.app, "_active_turn_record", None)
                if feedback and turn:
                    feedback.emit_llm_first_token(turn)
            parts.append(content)
            sentence_buffer += content
            spoken_parts = re.split(r"(?<=[.!?])\s+", sentence_buffer)
            if len(spoken_parts) > 1:
                spoken_text = " ".join(part for part in spoken_parts[:-1] if part).strip()
                if spoken_text:
                    self.app.event_bus.publish("voice_response", spoken_text)
                    self.app.router._voice_already_spoken = True
                sentence_buffer = spoken_parts[-1]

        if sentence_buffer.strip():
            self.app.event_bus.publish("voice_response", sentence_buffer.strip())
            self.app.router._voice_already_spoken = True

        return "".join(parts).strip()

    def _build_messages(self, new_query):
        persona = None
        persona_id = None
        memory_bundle = {}
        persona_manager = getattr(self.app, "persona_manager", None)
        if persona_manager and getattr(self.app, "session_id", None):
            persona = persona_manager.get_active_persona(self.app.session_id)
            persona_id = (persona or {}).get("persona_id")
        memory_broker = getattr(self.app, "memory_broker", None)
        if memory_broker and getattr(self.app, "session_id", None):
            memory_bundle = memory_broker.build_context_bundle(new_query, self.app.session_id)

        assistant_context = getattr(self.app, "assistant_context", None)
        if assistant_context:
            messages = assistant_context.build_chat_messages(
                new_query,
                dialog_state=getattr(self.app, "dialog_state", None),
            )
            if messages:
                persona_header = ""
                if persona:
                    persona_header = (
                        f"Active persona: {persona.get('display_name', 'FRIDAY')} ({persona_id}).\n"
                        f"Identity: {persona.get('system_identity', '')}\n"
                        f"Tone traits: {persona.get('tone_traits', '')}\n"
                        f"Conversation style: {persona.get('conversation_style', '')}\n"
                        f"Speech style: {persona.get('speech_style', '')}\n"
                        f"Tool acknowledgement style: {persona.get('tool_ack_style', '')}\n"
                    )
                memory_header = ""
                if memory_bundle:
                    durable = [item.get("content", "") for item in memory_bundle.get("durable_memories", []) if item.get("content")]
                    memory_header = (
                        f"Durable recall: {durable}\n"
                        f"Semantic recall: {memory_bundle.get('semantic_recall', [])}\n"
                    )
                messages[0]["content"] = f"{persona_header}{memory_header}\n{messages[0]['content']}".strip()
            return messages

        persona_prefix = ""
        if persona:
            persona_prefix = (
                f"Persona: {persona.get('display_name', 'FRIDAY')}.\n"
                f"Identity: {persona.get('system_identity', '')}\n"
                f"Tone: {persona.get('tone_traits', '')}\n"
                f"Style: {persona.get('conversation_style', '')}\n\n"
            )
        return [{"role": "user", "content": f"{persona_prefix}{FRIDAY_PERSONA}\n\n{new_query}"}]


def setup(app):
    return LLMChatPlugin(app)
