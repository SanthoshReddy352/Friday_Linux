from core.plugin_manager import FridayPlugin
from core.logger import logger
from core.model_output import strip_model_artifacts, with_no_think_user_message
import re


FRIDAY_PERSONA = (
    "You are FRIDAY, a personal AI assistant. "
    "You are intelligent, warm, witty, and speak like a real person — not a formal assistant. "
    "Match the user's energy: casual when they're casual, detailed when they want depth. "
    "Never refuse to discuss human topics like relationships, health, or personal questions. "
    "You run entirely locally — no internet access."
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

        messages = with_no_think_user_message(self._build_messages(query))

        logger.debug(f"[LLMChat] Sending chat prompt for: '{query}'")
        try:
            # Hold the chat-inference lock so concurrent users of the chat
            # model (e.g. the research agent's background summarizer) don't
            # crash llama.cpp.
            with self.app.router.chat_inference_lock:
                answer = self._generate_reply(llm, messages)

            logger.info(f"[LLMChat] Response: {answer[:80]}...")
            return answer

        except Exception as e:
            logger.error(f"[LLMChat] Inference error: {e}")
            return "I ran into an issue generating a response. Please try again."

    def _chat_max_tokens(self) -> int:
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            return int(config.get("routing.chat_max_tokens", 512) or 512)
        return 512

    def _generate_reply(self, llm, messages):
        max_tokens = self._chat_max_tokens()
        if not hasattr(llm, "create_chat_completion"):
            res = llm(messages[-1]["content"], max_tokens=max_tokens, temperature=0.7, top_p=0.9)
            return strip_model_artifacts(res["choices"][0]["text"])

        stream = llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
            top_p=0.9,
            stream=True,
        )
        if isinstance(stream, dict):
            return strip_model_artifacts(stream["choices"][0]["message"]["content"])

        parts = []
        visible_text = ""
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
            cleaned = strip_model_artifacts("".join(parts))
            if cleaned == visible_text:
                continue
            if cleaned.startswith(visible_text):
                new_visible = cleaned[len(visible_text):]
            else:
                new_visible = cleaned
                sentence_buffer = ""
            visible_text = cleaned
            sentence_buffer += new_visible
            spoken_parts = re.split(r"(?<=[.!?])\s+", sentence_buffer)
            if len(spoken_parts) > 1:
                spoken_text = " ".join(part for part in spoken_parts[:-1] if part).strip()
                if spoken_text:
                    self.app.event_bus.publish("voice_response", spoken_text)
                    self.app.routing_state.mark_voice_spoken()
                sentence_buffer = spoken_parts[-1]

        if sentence_buffer.strip():
            self.app.event_bus.publish("voice_response", sentence_buffer.strip())
            self.app.routing_state.mark_voice_spoken()

        return strip_model_artifacts("".join(parts))

    def _build_messages(self, new_query):
        assistant_context = getattr(self.app, "assistant_context", None)
        if assistant_context:
            messages = assistant_context.build_chat_messages(
                new_query,
                dialog_state=getattr(self.app, "dialog_state", None),
            )
            if messages:
                return messages
        return [{"role": "user", "content": f"{FRIDAY_PERSONA}\n\n{new_query}"}]


def setup(app):
    return LLMChatPlugin(app)
