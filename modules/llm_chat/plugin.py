import os
from core.plugin_manager import FridayPlugin
from core.logger import logger


FRIDAY_PERSONA = (
    "You are FRIDAY, an offline AI assistant inspired by the Iron Man AI. "
    "You are helpful, concise, and occasionally witty. "
    "You run entirely locally — no internet. "
    "Keep answers short (2-4 sentences) unless the user asks for details."
)

MAX_HISTORY_TURNS = 6  # keep last N user+assistant pairs


class LLMChatPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "LLMChat"
        self._history = []  # list of {"role": "user"|"assistant", "content": str}
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

        # Build conversation prompt with history
        messages = self._build_messages(query)

        logger.debug(f"[LLMChat] Sending chat prompt for: '{query}'")
        try:
            res = llm.create_chat_completion(
                messages,
                max_tokens=200,
                temperature=0.7,
            )
            answer = res["choices"][0]["message"]["content"].strip()

            # Store in history
            self._history.append({"role": "user", "content": query})
            self._history.append({"role": "assistant", "content": answer})
            # Trim history to MAX_HISTORY_TURNS pairs
            if len(self._history) > MAX_HISTORY_TURNS * 2:
                self._history = self._history[-(MAX_HISTORY_TURNS * 2):]

            logger.info(f"[LLMChat] Response: {answer[:80]}...")
            return answer

        except Exception as e:
            logger.error(f"[LLMChat] Inference error: {e}")
            return "I ran into an issue generating a response. Please try again."

    def _build_messages(self, new_query):
        """Construct a list of messages with persona + conversation history."""
        messages = []
        
        # Add history
        for idx, turn in enumerate(self._history):
            role_label = turn["role"]
            content = turn["content"]
            # Prepend system persona to the first user message, since Gemma doesn't support "system" role natively
            if idx == 0 and role_label == "user":
                content = f"{FRIDAY_PERSONA}\n\n{content}"
            messages.append({"role": role_label, "content": content})
            
        # Add new query
        final_query = new_query
        if not self._history:
            final_query = f"{FRIDAY_PERSONA}\n\n{new_query}"
        messages.append({"role": "user", "content": final_query})
        
        return messages


def setup(app):
    return LLMChatPlugin(app)
