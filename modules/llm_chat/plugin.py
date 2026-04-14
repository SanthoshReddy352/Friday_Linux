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
        }, self.handle_chat)

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
        for chunk in stream:
            delta = chunk["choices"][0].get("delta", {})
            content = delta.get("content")
            if not content:
                continue
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
        assistant_context = getattr(self.app, "assistant_context", None)
        if assistant_context:
            return assistant_context.build_chat_messages(
                new_query,
                dialog_state=getattr(self.app, "dialog_state", None),
            )

        return [{"role": "user", "content": f"{FRIDAY_PERSONA}\n\n{new_query}"}]


def setup(app):
    return LLMChatPlugin(app)
