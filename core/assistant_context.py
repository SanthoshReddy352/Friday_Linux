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


# Batch 6 / Issue 6b — retrieval gating. The semantic_recall + user_facts
# fetch costs ~50-150ms; skipping it on small-talk turns is a real win.
# These regexes detect a *referential signal* — a pronoun, an explicit
# memory verb ("remember", "recall"), or a proper noun. When any fire we
# fetch even if the query is short.
_REFERENTIAL_PRONOUN_RE = re.compile(
    r"\b(?:i|me|my|mine|myself|you|your|yours|we|us|our|ours|"
    r"he|him|his|she|her|hers|they|them|their|theirs|"
    r"it|its|that|this|these|those)\b",
    re.IGNORECASE,
)
_REFERENTIAL_VERB_RE = re.compile(
    r"\b(?:remember|recall|forget|known|knew|told|mentioned|"
    r"earlier|previously|last\s+time|last\s+session)\b",
    re.IGNORECASE,
)
# Tokens that are stylistic capitalisation rather than proper nouns —
# they appear at the start of sentences without naming entities.
_NON_PROPER_LEADING = frozenset({
    "i", "i'm", "i've", "i'll", "i'd",
    "what", "where", "when", "who", "why", "how",
    "tell", "show", "list", "open", "close", "play",
    "yes", "no", "ok", "okay", "sure",
})


def _has_proper_noun(text: str) -> bool:
    """Cheap proper-noun probe.

    Treats a token as a proper noun if it isn't the first word of the
    sentence, starts uppercase, and is followed by lowercase letters
    (so "USA" / "API" don't false-positive). Good enough as a trigger;
    not meant to be an NER replacement.
    """
    if not text:
        return False
    tokens = text.strip().split()
    for i, tok in enumerate(tokens):
        if i == 0:
            continue
        cleaned = tok.strip(".,!?;:'\"()")
        if (
            len(cleaned) >= 2
            and cleaned[0].isupper()
            and cleaned[1:].islower()
            and cleaned.lower() not in _NON_PROPER_LEADING
        ):
            return True
    return False


def _needs_referential_recall(query: str) -> bool:
    """Return True iff the query contains any referential signal worth
    paying the memory-bundle cost for. Used by ``build_chat_messages``
    to override the cheap is-short gate for personal queries.
    """
    if not query:
        return False
    if _REFERENTIAL_PRONOUN_RE.search(query):
        return True
    if _REFERENTIAL_VERB_RE.search(query):
        return True
    return _has_proper_noun(query)


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
        self.session_rag = None
        self.memory_service = None

    def bind_context_store(self, context_store, session_id, memory_service=None):
        self.context_store = context_store
        self.session_id = session_id
        if memory_service is not None:
            self.memory_service = memory_service

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
        # Strip special chars only for voice/STT input — typed text (chat,
        # telegram, gui) can contain meaningful punctuation like dots in model
        # version numbers ("3.5-0.6B"), hyphens, slashes, etc.
        if source == "voice":
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
        # Batch 6 / Issue 6b: even a "short" turn earns semantic recall
        # when it contains a referential signal (pronoun, proper noun,
        # explicit "remember/recall" verb). Without this override,
        # "what do you know about me?" and "remind me of Mumbai trip"
        # would silently skip recall because they're under the
        # six-word threshold.
        needs_recall = _needs_referential_recall(query)
        session_summary = ""
        workflow_summary = ""
        semantic_recall = []
        user_facts = ""
        if self.context_store and self.session_id:
            workflow_summary = self.context_store.get_workflow_summary(self.session_id)
            if (not is_short) or needs_recall:
                session_summary = self.context_store.summarize_session(self.session_id, limit=4)
                semantic_recall = self.context_store.semantic_recall(query, self.session_id, limit=2)
            # Surface durable user facts (Mem0 / curated profile facts) so the
            # chat model can answer "what do you remember about me?" without
            # routing to a tool. Best-effort — falls back silently on any error.
            # Only fetch when there's a referential signal — otherwise we'd
            # pay the bundle cost on every "hi" / "what time is it" turn.
            if (not is_short) or needs_recall:
                try:
                    memory_service = getattr(self, "memory_service", None)
                    if memory_service is not None:
                        bundle = memory_service.build_context_bundle(self.session_id, query) or {}
                        facts = bundle.get("user_facts")
                        if facts:
                            user_facts = str(facts).strip()
                except Exception:
                    user_facts = ""

        persona = (
            "You are FRIDAY, a personal AI assistant. "
            "You are intelligent, warm, and speak like a real person — not a formal assistant. "
            "Match the user's energy and give responses as long as the topic deserves. "
            "No preamble, no chain-of-thought, no emoji unless the user uses one first."
        )

        # User profile block — populated by the onboarding flow. Always
        # injected when any profile field is set, regardless of Mem0 status,
        # so questions like "what's my name?" don't fall back to a generic
        # "I'm an AI" reply.
        user_profile_block = ""
        if self.context_store:
            try:
                profile_facts = {
                    f["key"]: (f["value"] or "").strip()
                    for f in self.context_store.get_facts_by_namespace("user_profile")
                }
                name = profile_facts.get("name", "")
                role = profile_facts.get("role", "")
                location = profile_facts.get("location", "")
                preferences = profile_facts.get("preferences", "")
                comm_style = profile_facts.get("comm_style", "")
                if any((name, role, location, preferences, comm_style)):
                    lines = ["The user's profile (always known to you, refer to them by name):"]
                    if name:        lines.append(f"  - Name: {name}")
                    if role:        lines.append(f"  - Role: {role}")
                    if location:    lines.append(f"  - Location: {location}")
                    if preferences: lines.append(f"  - Cares about: {preferences}")
                    if comm_style:  lines.append(f"  - Preferred communication style: {comm_style}")
                    user_profile_block = "\n".join(lines)
            except Exception:
                user_profile_block = ""

        rag_context = ""
        if self.session_rag and self.session_rag.is_active:
            rag_context = self.session_rag.get_context_block(query)

        last_topic = ""
        resumed_context = ""
        if self.context_store:
            try:
                facts = self.context_store.get_facts_by_namespace("system")
                last_topic = next((f["value"] for f in facts if f["key"] == "last_session_topic"), "")
                resumed_context = next((f["value"] for f in facts if f["key"] == "resumed_session_context"), "")
            except Exception:
                pass

        if is_short:
            guidance = persona
            if user_profile_block:
                guidance += f"\n\n{user_profile_block}"
            if last_topic:
                guidance += f"\nNote: In the previous session, you discussed: {last_topic}"
        else:
            guidance = (
                f"{persona}\n"
                f"Active workflow: {workflow_summary or 'none'}\n"
                f"Session summary: {session_summary or 'none'}\n"
            )
            if user_profile_block:
                guidance += f"{user_profile_block}\n"
            if last_topic:
                guidance += f"Previous session topic: {last_topic}\n"
            guidance += f"Relevant recall: {json.dumps(semantic_recall, ensure_ascii=True)}"
            if user_facts:
                guidance += f"\nWhat you know about the user:\n{user_facts}"

        if resumed_context:
            guidance += (
                "\n\nThe user just resumed from a previous session. "
                "Use the context below to answer follow-up questions like 'answer it', "
                "'continue', 'fix it', or 'go on':\n"
                f"{resumed_context}"
            )

        if rag_context:
            guidance = f"{guidance}\n\n{rag_context}"

        recent_limit = 4 if is_short else 6
        recent = []
        for item in list(self.history)[-recent_limit:]:
            role = item.get("role")
            content = item.get("text", "")
            # Truncate long past assistant responses to save prompt processing time
            if role == "assistant" and len(content.split()) > 100:
                content = " ".join(content.split()[:100]) + "... [truncated]"
            recent.append({"role": role, "content": content})
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
