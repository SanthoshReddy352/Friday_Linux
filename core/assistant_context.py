import json
import re
from collections import deque


NEGATIVE_KEYWORD_PATTERN = re.compile(
    r"\b("
    r"wtf|wth|ffs|omfg|shit(?:ty|tiest)?|dumbass|horrible|awful|"
    r"piss(?:ed|ing)? off|piece of (?:shit|crap|junk)|what the (?:fuck|hell)|"
    r"fucking? (?:broken|useless|terrible|awful|horrible)|fuck you|"
    r"screw (?:this|you)|so frustrating|this sucks|damn it"
    r")\b",
    re.IGNORECASE,
)

KEEP_GOING_PATTERN = re.compile(r"\b(?:keep going|go on)\b", re.IGNORECASE)
LEADING_FILLERS_PATTERN = re.compile(
    r"^(?:uh|um|hmm|hm|ah|please|hey|okay|ok|well)\b[\s,]*",
    re.IGNORECASE,
)
POLITE_PREFIX_PATTERN = re.compile(
    r"^(?:can|could|would|will)\s+you\b[\s,]*",
    re.IGNORECASE,
)


class AssistantContext:
    """
    Shared conversational context for FRIDAY.

    The prompt layering builds a stable assistant identity first, 
    then appends live turn context.
    """

    def __init__(self, max_messages=32):
        self.history = deque(maxlen=max_messages)
        self.last_user_tone = "neutral"
        self.last_tool_name = None
        self.last_tool_args = {}
        self.context_store = None
        self.session_id = None

    def bind_context_store(self, context_store, session_id):
        self.context_store = context_store
        self.session_id = session_id

    def record_message(self, role, text, source=None):
        if not text:
            return
        self.history.append(
            {
                "role": role,
                "text": str(text).strip(),
                "source": source or role,
            }
        )
        if role == "user":
            self.last_user_tone = self.detect_user_tone(text)

    def remember_tool_use(self, tool_name, args=None):
        self.last_tool_name = tool_name
        self.last_tool_args = dict(args or {})

    def detect_user_tone(self, text):
        normalized = (text or "").strip().lower()
        if not normalized:
            return "neutral"
        if self.matches_negative_keyword(normalized):
            return "frustrated"
        if self.matches_keep_going_keyword(normalized):
            return "continuing"
        if re.fullmatch(r"(?:hi|hello|hey|good morning|good afternoon|good evening)[.!?]?", normalized):
            return "warm"
        if normalized.endswith("?") or normalized.startswith(("what", "how", "why", "when", "where", "who")):
            return "curious"
        if any(word in normalized for word in ("please", "could you", "can you", "would you")):
            return "polite"
        if any(word in normalized for word in ("now", "quickly", "urgent", "asap")):
            return "urgent"
        return "neutral"

    def matches_negative_keyword(self, text):
        return bool(NEGATIVE_KEYWORD_PATTERN.search(text or ""))

    def matches_keep_going_keyword(self, text):
        normalized = (text or "").strip().lower()
        return normalized == "continue" or bool(KEEP_GOING_PATTERN.search(normalized))

    def clean_voice_transcript(self, text):
        return self.clean_user_text(text, source="voice")

    def clean_user_text(self, text, source="user"):
        if not isinstance(text, str):
            return ""

        cleaned = text.lower().strip()
        cleaned = re.sub(r"[^\w\s']", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Fix common typos
        cleaned = re.sub(r"\bcalender\b", "calendar", cleaned)

        previous = None
        while cleaned and cleaned != previous:
            previous = cleaned
            cleaned = LEADING_FILLERS_PATTERN.sub("", cleaned).strip()

        cleaned = re.sub(r"^(?:hey friday|friday)\b[\s,]*", "", cleaned).strip()
        cleaned = POLITE_PREFIX_PATTERN.sub("", cleaned).strip()
        cleaned = re.sub(r"\bplease\b", "", cleaned)
        cleaned = re.sub(r"\bfor me\b", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def build_router_prompt(self, user_text, tools, dialog_state=None, last_context=None, target_tool=None):
        workflow_summary = ""
        semantic_recall = []
        if self.context_store and self.session_id:
            workflow_summary = self.context_store.get_workflow_summary(self.session_id)
            semantic_recall = self.context_store.semantic_recall(user_text, self.session_id, limit=3)

        tool_list = tools
        if target_tool:
            tool_list = [
                {
                    "name": target_tool["spec"]["name"],
                    "description": target_tool["spec"]["description"],
                    "parameters": target_tool["spec"].get("parameters", {}),
                }
            ]

        prompt_payload = {
            "assistant_identity": "FRIDAY, a warm local desktop assistant powered by Whisper and Gemma.",
            "response_style": [
                "sound natural and calm",
                "prefer action when the intent is clear",
                "reuse recent context when the user says things like it, that, this one, or continue",
                "if the user is frustrated, respond supportively and without sounding robotic",
            ],
            "recent_history": self._recent_history_lines(limit=6),
            "dialog_state": self._dialog_state_snapshot(dialog_state),
            "last_context": last_context or {},
            "active_workflow": workflow_summary,
            "semantic_recall": semantic_recall,
            "user_tone": self.detect_user_tone(user_text),
            "available_tools": tool_list,
        }
        prompt_json = json.dumps(prompt_payload, ensure_ascii=True)
        return (
            "ROUTER_HEADER: FAST_JSON_TOOL_ROUTER_V2\n"
            "ROUTER_FLAGS: JSON_ONLY, COMPACT_ARGS, NO_EXTRA_TEXT\n"
            "You are FRIDAY's intent engine.\n"
            "Use the context to decide whether the user wants a tool, a conversational reply, or clarification.\n"
            "Return exactly one JSON object and nothing else.\n"
            "Preferred schema:\n"
            '{"mode":"tool|chat|clarify","tool":"tool_name","args":{},"say":"short spoken acknowledgement","reply":"assistant reply"}\n'
            'Legacy schema is also allowed: {"tool":"tool_name","args":{}}\n'
            f"Context: {prompt_json}\n"
            f"User: {user_text}"
        )

    def build_chat_messages(self, query, dialog_state=None):
        is_short = len((query or "").split()) <= 6
        session_summary = ""
        workflow_summary = ""
        semantic_recall = []
        if self.context_store and self.session_id:
            workflow_summary = self.context_store.get_workflow_summary(self.session_id)
            if not is_short:
                session_summary = self.context_store.summarize_session(self.session_id, limit=4)
                semantic_recall = self.context_store.semantic_recall(query, self.session_id, limit=2)

        persona = (
            "You are FRIDAY, a personal AI assistant. "
            "You are intelligent, warm, and speak like a real person — not a formal assistant. "
            "Match the user's energy and give responses as long as the topic deserves. "
            "No preamble, no chain-of-thought, no emoji unless the user uses one first."
        )
        if is_short:
            guidance = persona
        else:
            guidance = (
                f"{persona}\n"
                f"Active workflow: {workflow_summary or 'none'}\n"
                f"Session summary: {session_summary or 'none'}\n"
                f"Relevant recall: {json.dumps(semantic_recall, ensure_ascii=True)}"
            )

        recent_limit = 6 if is_short else 12
        recent = [
            {"role": item.get("role"), "content": item.get("text", "")}
            for item in list(self.history)[-recent_limit:]
        ]
        alternating = self._coerce_alternating_history(recent)

        messages = []
        if alternating and alternating[0]["role"] == "user":
            first = dict(alternating[0])
            first["content"] = f"{guidance}\n\n{first['content']}"
            messages.append(first)
            messages.extend(alternating[1:])
        else:
            messages.append({"role": "user", "content": guidance})
            messages.extend(alternating)

        if messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": query})
        elif messages[-1]["content"].strip() != query:
            messages[-1]["content"] = f"{messages[-1]['content']}\n\n{query}".strip()
        return messages

    def humanize_tool_result(self, text):
        if not isinstance(text, str):
            return text

        if text.startswith("SUCCESS: "):
            body = text[len("SUCCESS: "):].strip()
            if body.startswith("Found "):
                return "I " + body[:1].lower() + body[1:]
            if body.startswith("Files in "):
                return "Here are the " + body[:1].lower() + body[1:]
            return body[:1].upper() + body[1:] if body else text

        if text.startswith("FAILURE: "):
            body = text[len("FAILURE: "):].strip()
            return body[:1].upper() + body[1:] if body else text

        if text == "Done.":
            return "All set."

        return text

    def latest_assistant_text(self):
        for item in reversed(self.history):
            if item.get("role") == "assistant":
                return item.get("text", "")
        return ""

    def _dialog_state_snapshot(self, dialog_state):
        if not dialog_state:
            return {}

        snapshot = {}
        if getattr(dialog_state, "current_folder", None):
            snapshot["current_folder"] = dialog_state.current_folder
        if getattr(dialog_state, "selected_file", None):
            snapshot["selected_file"] = dialog_state.selected_file
        pending = getattr(dialog_state, "pending_file_request", None)
        if pending and pending.candidates:
            snapshot["pending_file_request"] = {
                "filename_query": pending.filename_query,
                "folder_path": pending.folder_path,
                "requested_actions": list(pending.requested_actions),
                "candidates": list(pending.candidates[:5]),
            }
        return snapshot

    def _recent_history_lines(self, limit=6):
        lines = []
        for item in list(self.history)[-limit:]:
            lines.append(f"{item['role']}: {item['text']}")
        return lines

    def _coerce_alternating_history(self, items):
        normalized = []
        for item in items:
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = str(item.get("content", "")).strip()
            if not content:
                continue

            if not normalized and role == "assistant":
                continue

            if normalized and normalized[-1]["role"] == role:
                normalized[-1]["content"] = f"{normalized[-1]['content']}\n{content}"
            else:
                normalized.append({"role": role, "content": content})
        return normalized
