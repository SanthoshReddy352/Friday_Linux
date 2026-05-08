import re
import os

def _get_extract_app_names():
    try:
        from modules.system_control.app_launcher import extract_app_names  # noqa: PLC0415
        return extract_app_names
    except Exception:
        return lambda _text: []

extract_app_names = _get_extract_app_names()


class IntentRecognizer:
    def __init__(self, router):
        self.router = router

    def plan(self, text, context=None):
        cleaned = self._clean_text(text)
        if not cleaned:
            return []

        actions = []
        seen_read_only_actions = set()
        current_context = dict(context or {})
        clauses = self._split_into_clauses(cleaned)
        for clause in clauses:
            action = self._parse_clause(clause, current_context)
            if not action:
                return []
            action_key = (action["tool"], self._hashable_args(action.get("args", {})))
            if action_key in seen_read_only_actions and not action.get("args"):
                continue
            if not action.get("args"):
                seen_read_only_actions.add(action_key)
            actions.append(action)
            current_context = {
                "tool": action["tool"],
                "domain": action.get("domain", action["tool"]),
                "args": dict(action.get("args", {})),
            }
        return actions

    def _clean_text(self, text):
        text = " ".join(text.strip().split())
        text = re.sub(r"\s+", " ", text)
        return text.strip(" \t\r\n")

    def _split_into_clauses(self, text):
        clauses = [text]
        for splitter in (
            re.compile(r"\b(?:and then|then|also|after that|afterwards|plus)\b", re.IGNORECASE),
            re.compile(r"\s*;\s*"),
        ):
            expanded = []
            for clause in clauses:
                expanded.extend(part.strip() for part in splitter.split(clause) if part.strip())
            clauses = expanded

        expanded = []
        for clause in clauses:
            expanded.extend(self._split_on_action_and(clause))
        return [clause for clause in expanded if clause]

    def _split_on_action_and(self, clause):
        if self._is_multi_app_launch_clause(clause):
            return [clause.strip()]
        if re.search(r"\bopen\s+youtube(?:\s+music)?\b.*\band\s+play\b", clause, re.IGNORECASE):
            return [clause.strip()]
        # Don't split when both halves act on a shared pronoun like "it":
        # "open and read it to me" describes two actions on the same target.
        # The downstream file controller can detect both verbs in one clause.
        if re.search(
            r"\b(?:open|read|summarize|preview|show|play)\s+and\s+(?:open|read|summarize|preview|show|play)\b.*?\b(?:it|this|that|the file|to me|out loud)\b",
            clause,
            re.IGNORECASE,
        ):
            return [clause.strip()]

        lower_clause = clause.lower()
        for marker in self._action_connectors_for(lower_clause):
            idx = lower_clause.find(marker)
            while idx != -1:
                left = clause[:idx].strip(" ,")
                right = clause[idx + len(marker):].strip(" ,")
                if left and right and self._looks_like_action_start(right):
                    return self._split_on_action_and(left) + self._split_on_action_and(right)
                idx = lower_clause.find(marker, idx + len(marker))
        return [clause.strip()]

    def _action_connectors_for(self, lower_clause):
        connectors = [" and "]
        # Whisper sometimes hears "and time" as "on time". Only treat "on" as
        # a connector in short status/time requests so normal phrases like
        # "play this on YouTube" stay intact.
        if re.search(
            r"\b(?:system info|system information|system status|system health|system details|"
            r"current time|the time|time|current date|date|battery|cpu|ram|memory)\b",
            lower_clause,
        ):
            connectors.append(" on ")
        return connectors

    def _is_multi_app_launch_clause(self, clause):
        clause_lower = clause.lower()
        if not re.search(r"\b(?:open|launch|start|bring up)\b", clause_lower):
            return False
        if re.search(r"\b(?:file|folder)\b", clause_lower):
            return False
        return len(extract_app_names(clause_lower)) > 1

    def _looks_like_action_start(self, text):
        normalized = text.lower().strip()
        normalized = re.sub(r"^(?:the|my|current)\s+", "", normalized)
        if self._looks_like_short_status_fragment(normalized):
            return True
        starters = (
            "open", "launch", "start", "bring up", "take", "capture", "find", "search",
            "locate", "set", "save", "write", "append", "add", "read", "show", "list", "get", "check", "tell",
            "what", "summarize", "summary", "remind", "enable", "disable", "turn",
            "mute", "unmute", "increase", "decrease", "lower", "raise", "stop", "pause",
            "play",
        )
        return any(normalized.startswith(starter) for starter in starters)

    def _looks_like_short_status_fragment(self, normalized):
        fragments = (
            "time",
            "date",
            "system info",
            "system information",
            "system status",
            "system health",
            "system details",
            "battery",
            "battery status",
        )
        return any(normalized == fragment or normalized.startswith(f"{fragment} ") for fragment in fragments)

    def _hashable_args(self, args):
        if not isinstance(args, dict):
            return ()
        return tuple(sorted((str(key), repr(value)) for key, value in args.items()))

    def _parse_clause(self, clause, context):
        clause_lower = clause.lower().strip()

        for parser in (
            self._parse_pending_selection,
            self._parse_dictation,
            self._parse_focus_session,
            self._parse_research_topic,
            self._parse_google_search,
            self._parse_browser_media,
            self._parse_volume,
            self._parse_system,
            self._parse_time_date,
            self._parse_screenshot,
            self._parse_file_action,
            self._parse_launch_app,
            self._parse_manage_file,
            self._parse_reminder,
            self._parse_notes,
            self._parse_voice_toggle,
            self._parse_exit,
            self._parse_help,
            self._parse_greeting,
            self._parse_confirmation,
        ):
            action = parser(clause, clause_lower, context)
            if action:
                return action

        return None

    def _parse_focus_session(self, clause, clause_lower, context):
        tools = getattr(self.router, "_tools_by_name", {})
        if "start_focus_session" not in tools:
            return None
        if re.search(
            r"\b(?:end|stop|exit|cancel|disable)\s+(?:my\s+)?(?:focus(?:\s+session|\s+mode)?|pomodoro|do\s+not\s+disturb)\b",
            clause_lower,
        ):
            return {"tool": "end_focus_session", "args": {}, "text": clause, "domain": "focus"}
        if re.search(
            r"\b(?:focus|pomodoro|do\s+not\s+disturb)\s+(?:status|left|remaining|time)\b",
            clause_lower,
        ):
            return {"tool": "focus_session_status", "args": {}, "text": clause, "domain": "focus"}
        if re.search(
            r"\bhow\s+much\s+(?:focus|time)\s+(?:is\s+)?(?:left|remaining)\b",
            clause_lower,
        ):
            return {"tool": "focus_session_status", "args": {}, "text": clause, "domain": "focus"}
        if re.search(
            r"\b(?:start|begin|enter|kick\s+off)\s+(?:a\s+|the\s+)?(?:focus(?:\s+session|\s+mode)?|pomodoro|do\s+not\s+disturb)\b",
            clause_lower,
        ):
            return {"tool": "start_focus_session", "args": {}, "text": clause, "domain": "focus"}
        if re.search(
            r"\b(?:focus|pomodoro)\s+(?:for\s+\d+|mode)\b",
            clause_lower,
        ):
            return {"tool": "start_focus_session", "args": {}, "text": clause, "domain": "focus"}
        if re.search(
            r"\bdo\s+not\s+disturb\s+(?:for\s+\d+\s*(?:minutes?|mins?|hours?))\b",
            clause_lower,
        ):
            return {"tool": "start_focus_session", "args": {}, "text": clause, "domain": "focus"}
        return None

    def _parse_dictation(self, clause, clause_lower, context):
        tools = getattr(self.router, "_tools_by_name", {})
        if {"start_dictation", "end_dictation", "cancel_dictation"} - set(tools):
            return None
        if re.search(r"\b(?:cancel|discard|throw away)\s+(?:the\s+)?(?:memo|dictation|recording)\b", clause_lower):
            return {"tool": "cancel_dictation", "args": {}, "text": clause, "domain": "dictation"}
        if re.search(
            r"\b(?:end|stop|finish|save|close)\s+(?:the\s+)?(?:memo|dictation|recording|note(?:\s+taking)?|writing)\b",
            clause_lower,
        ):
            return {"tool": "end_dictation", "args": {}, "text": clause, "domain": "dictation"}
        if re.search(r"\b(?:end|stop|finish)\s+dictating\b", clause_lower):
            return {"tool": "end_dictation", "args": {}, "text": clause, "domain": "dictation"}
        start_match = re.search(
            r"\b(?:take|start|begin|record|capture)\s+(?:a\s+|new\s+|the\s+)?(?:memo|dictation|note(?:\s+taking)?|recording|journal entry)(?:\s+(?:called|named|titled)\s+(.+))?$",
            clause_lower,
        )
        if start_match:
            label = (start_match.group(1) or "").strip(" .!?'\"")
            args = {"label": label} if label else {}
            return {"tool": "start_dictation", "args": args, "text": clause, "domain": "dictation"}
        if re.search(r"\b(?:dictation\s+mode\s+on|enter\s+dictation|dictate(?:\s+for\s+me)?)\b", clause_lower):
            return {"tool": "start_dictation", "args": {}, "text": clause, "domain": "dictation"}
        return None

    def _parse_research_topic(self, clause, clause_lower, context):
        if "research_topic" not in getattr(self.router, "_tools_by_name", {}):
            return None

        # "research X", "do a deep dive on X", "find research papers on X",
        # "put together a briefing on X", "give me a literature review of X",
        # "brief me on X", "investigate X", "look into X". The pattern is
        # ordered most-specific → least-specific so generic verbs ("look up")
        # don't swallow more specific phrasings.
        topic_patterns = (
            r"^(?:please\s+)?do\s+(?:a\s+)?(?:deep\s+dive|literature\s+review)\s+(?:on|about|into|for)\s+(.+)$",
            r"^(?:please\s+)?(?:put\s+together|prepare|write|draft|generate)\s+(?:me\s+)?"
            r"(?:a\s+)?(?:research\s+)?briefing\s+(?:on|about|for)\s+(.+)$",
            r"^(?:please\s+)?brief\s+me\s+(?:on|about)\s+(.+)$",
            r"^(?:please\s+)?(?:find|gather|fetch|pull|collect|surface|dig\s+up)\s+(?:me\s+)?"
            r"(?:some\s+)?(?:research\s+(?:papers|articles)|articles|papers|sources|references)"
            r"(?:\s+(?:on|about|for))?\s+(.+)$",
            r"^(?:please\s+)?give\s+me\s+(?:a\s+)?(?:literature\s+review|deep\s+dive|briefing)"
            r"\s+(?:on|about|of)\s+(.+)$",
            r"^(?:please\s+)?research\s+(?:the\s+latest\s+(?:on|about)\s+|on\s+|about\s+|into\s+)?(.+)$",
            r"^(?:please\s+)?(?:investigate|study)\s+(.+)$",
        )
        for pattern in topic_patterns:
            match = re.match(pattern, clause_lower)
            if not match:
                continue
            topic = match.group(1).strip(" .!?:'\"")
            if not topic or len(topic) < 2:
                continue
            return {
                "tool": "research_topic",
                "args": {"topic": topic},
                "text": clause,
                "domain": "research",
            }
        return None

    def _parse_google_search(self, clause, clause_lower, context):
        if "search_google" not in getattr(self.router, "_tools_by_name", {}):
            return None
        # "search google for X", "google search X", "google for X", "look up X"
        patterns = (
            r"\bsearch\s+google\s+for\s+(.+)$",
            r"\bgoogle\s+search\s+for\s+(.+)$",
            r"\bgoogle\s+(?:for\s+)?(.+)$",
            r"\bsearch\s+(?:on|in)\s+google\s+for\s+(.+)$",
            r"\bsearch\s+(?:the\s+)?(?:web|internet)\s+for\s+(.+)$",
            r"\blook\s+up\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, clause_lower)
            if match:
                query = match.group(1).strip(" ?.!,")
                # Avoid intercepting "google calendar" / "google drive" / etc.
                if query.split()[:1] and query.split()[0] in {"calendar", "drive", "docs", "sheets", "tasks", "keep"}:
                    return None
                if not query:
                    return None
                browser_name = "chromium" if "chromium" in clause_lower else "chrome"
                return {
                    "tool": "search_google",
                    "args": {"query": query, "browser_name": browser_name},
                    "text": clause,
                    "domain": "browser",
                }
        return None

    def _parse_browser_media(self, clause, clause_lower, context):
        browser_name = "chromium" if "chromium" in clause_lower else "chrome"
        active_browser = self._active_browser_workflow()

        play_music = re.search(r"\bplay\s+(.+?)\s+(?:in|on)\s+youtube music\b", clause_lower)
        if play_music and "play_youtube_music" in getattr(self.router, "_tools_by_name", {}):
            query = play_music.group(1).strip()
            if query in {"it", "this", "that"} and active_browser:
                query = active_browser.get("query", query)
            return {
                "tool": "play_youtube_music",
                "args": {"query": query, "browser_name": browser_name},
                "text": clause,
                "domain": "browser",
            }

        open_and_play_music = re.search(r"\bopen\s+youtube music\b.*?\band\s+play\s+(.+)$", clause_lower)
        if open_and_play_music and "play_youtube_music" in getattr(self.router, "_tools_by_name", {}):
            return {
                "tool": "play_youtube_music",
                "args": {"query": open_and_play_music.group(1).strip(), "browser_name": browser_name},
                "text": clause,
                "domain": "browser",
            }

        open_and_play_video = re.search(r"\bopen\s+youtube\b.*?\band\s+play\s+(.+)$", clause_lower)
        if (
            open_and_play_video
            and "play_youtube" in getattr(self.router, "_tools_by_name", {})
            and "youtube music" not in open_and_play_video.group(1)
        ):
            return {
                "tool": "play_youtube",
                "args": {"query": open_and_play_video.group(1).strip(), "browser_name": browser_name},
                "text": clause,
                "domain": "browser",
            }

        play_video = re.search(r"\bplay\s+(.+?)\s+(?:in|on)\s+youtube\b", clause_lower)
        if play_video and "play_youtube" in getattr(self.router, "_tools_by_name", {}):
            query = play_video.group(1).strip()
            if query in {"it", "this", "that"} and active_browser:
                query = active_browser.get("query", query)
            return {
                "tool": "play_youtube",
                "args": {"query": query, "browser_name": browser_name},
                "text": clause,
                "domain": "browser",
            }

        bare_play = re.search(r"\bplay\s+(.+)$", clause_lower)
        if bare_play:
            query = bare_play.group(1).strip()
            if query in {"it", "this", "that"} and active_browser:
                query = active_browser.get("query", query)
            if query and query not in {"it", "this", "that"}:
                platform = self._default_browser_platform(query, active_browser)
                tool_name = "play_youtube_music" if platform == "youtube_music" else "play_youtube"
                if tool_name in getattr(self.router, "_tools_by_name", {}):
                    return {
                        "tool": tool_name,
                        "args": {"query": query, "browser_name": browser_name},
                        "text": clause,
                        "domain": "browser",
                    }

        if re.search(r"\bopen\s+youtube music\b", clause_lower) and "open_browser_url" in getattr(self.router, "_tools_by_name", {}):
            return {
                "tool": "open_browser_url",
                "args": {"url": "https://music.youtube.com", "browser_name": browser_name},
                "text": clause,
                "domain": "browser",
            }

        if re.search(r"\bopen\s+youtube\b", clause_lower) and "open_browser_url" in getattr(self.router, "_tools_by_name", {}):
            return {
                "tool": "open_browser_url",
                "args": {"url": "https://www.youtube.com", "browser_name": browser_name},
                "text": clause,
                "domain": "browser",
            }

        if active_browser and "browser_media_control" in getattr(self.router, "_tools_by_name", {}):
            normalized = clause_lower.strip(" .!?")
            
            # Complex phrase matching for skipping/reverting (making 'seconds' optional)
            if re.search(r"\b(?:skip|forward|move)\b.*?\b(?:seconds?|secs?)\b", normalized) or re.search(r"\bfast\s+forward\b", normalized):
                return {"tool": "browser_media_control", "args": {"control": "forward"}, "text": clause, "domain": "browser"}
            if re.search(r"\b(?:revert|back|rewind|previous)\b.*?\b(?:seconds?|secs?)\b", normalized):
                return {"tool": "browser_media_control", "args": {"control": "backward"}, "text": clause, "domain": "browser"}
            
            mapping = {
                "play": "resume",
                "pause": "pause",
                "resume": "resume",
                "stop": "pause",
                "next": "next",
                "skip": "next",
                "next video": "next",
                "previous video": "previous",
                "previous": "previous",
                "rewind": "previous", # Requested mapping: Shift+P
                "forward": "forward",
                "backward": "backward",
                "revert": "backward",
                "back": "backward",
            }
            if normalized in mapping:
                return {
                    "tool": "browser_media_control",
                    "args": {"control": mapping[normalized]},
                    "text": clause,
                    "domain": "browser",
                }
            if "music instead" in normalized:
                control = "play"
                query = active_browser.get("query", "")
                return {
                    "tool": "play_youtube_music",
                    "args": {"query": query, "browser_name": active_browser.get("browser_name", "chrome")},
                    "text": clause,
                    "domain": "browser",
                }
            if "youtube instead" in normalized:
                return {
                    "tool": "play_youtube",
                    "args": {"query": active_browser.get("query", ""), "browser_name": active_browser.get("browser_name", "chrome")},
                    "text": clause,
                    "domain": "browser",
                }

        return None

    def _parse_pending_selection(self, clause, clause_lower, context):
        dialog_state = getattr(self.router, "dialog_state", None)
        pending = getattr(dialog_state, "pending_file_request", None) if dialog_state else None
        if not pending or not pending.candidates:
            return None

        normalized = clause_lower.strip(" .!?")
        if re.fullmatch(r"(?:option\s+)?\d+", normalized):
            return {"tool": "select_file_candidate", "args": {}, "text": clause, "domain": "files"}

        if re.fullmatch(r"(?:the\s+)?(?:pdf|txt|md|json|csv|py|docx)\s+one", normalized):
            return {"tool": "select_file_candidate", "args": {}, "text": clause, "domain": "files"}

        if normalized in {"that one", "this one"}:
            return {"tool": "select_file_candidate", "args": {}, "text": clause, "domain": "files"}

        candidate_names = {os.path.basename(path).lower() for path in pending.candidates}
        candidate_stems = {os.path.splitext(name)[0] for name in candidate_names}
        if normalized in candidate_names or normalized in candidate_stems:
            return {"tool": "select_file_candidate", "args": {}, "text": clause, "domain": "files"}

        return None

    def _parse_launch_app(self, clause, clause_lower, context):
        if re.search(r"\b(?:file|folder)\b", clause_lower):
            return None
        pending = getattr(getattr(self.router, "dialog_state", None), "pending_file_request", None)
        if pending and re.search(r"\b(?:open|launch|start|bring up)\s+(?:it|this|that|one)\b", clause_lower):
            return None
        app_names = extract_app_names(clause_lower)
        if app_names and re.search(r"\b(?:open|launch|start|bring up)\b", clause_lower):
            return {
                "tool": "launch_app",
                "args": {"app_names": app_names},
                "text": clause,
                "domain": "apps",
            }
        return None

    def _parse_volume(self, clause, clause_lower, context):
        absolute_percent = self._extract_volume_percent(clause_lower, context)
        if absolute_percent is not None:
            return {
                "tool": "set_volume",
                "args": {"percent": absolute_percent},
                "text": clause,
                "domain": "volume",
            }

        direction = None
        if re.search(r"\bunmute\b", clause_lower):
            direction = "unmute"
        elif re.search(r"\bmute\b", clause_lower):
            direction = "mute"
        elif re.search(r"\b(?:increase|raise|louder|volume up|turn up)\b", clause_lower):
            direction = "up"
        elif re.search(r"\b(?:decrease|lower|quieter|volume down|turn down)\b", clause_lower):
            direction = "down"
        elif "volume" in clause_lower and context.get("domain") == "volume":
            direction = context.get("args", {}).get("direction")

        if not direction:
            return None

        steps = self._extract_count(clause_lower)
        return {
            "tool": "set_volume",
            "args": {"direction": direction, "steps": steps},
            "text": clause,
            "domain": "volume",
        }

    def _parse_system(self, clause, clause_lower, context):
        if re.search(r"\b(?:system info|system information|system status|system health|system details)\b", clause_lower):
            return {"tool": "get_system_status", "args": {}, "text": clause, "domain": "system"}

        if re.search(r"\bbattery(?: status)?\b", clause_lower):
            return {"tool": "get_battery", "args": {}, "text": clause, "domain": "system"}

        if re.search(r"\b(?:cpu|ram|memory|resource|usage|performance)\b", clause_lower):
            return {"tool": "get_cpu_ram", "args": {}, "text": clause, "domain": "system"}

        return None

    def _parse_time_date(self, clause, clause_lower, context):
        if re.search(
            r"\b(?:what(?:'s| is)? (?:the )?time|what time is it|current time|tell me(?: the)? time)\b",
            clause_lower,
        ) or re.fullmatch(r"(?:the\s+)?time", clause_lower.strip(" .!?")):
            return {"tool": "get_time", "args": {}, "text": clause, "domain": "time"}

        if re.search(
            r"\b(?:today(?:'s)? date|what(?:'s| is)? (?:the )?date|what day is it|current date|tell me(?: the)? date)\b",
            clause_lower,
        ) or re.fullmatch(r"(?:the\s+)?date", clause_lower.strip(" .!?")):
            return {"tool": "get_date", "args": {}, "text": clause, "domain": "date"}

        return None

    def _parse_screenshot(self, clause, clause_lower, context):
        if re.search(r"\b(?:take|capture).*(?:screenshot|screen shot)\b", clause_lower) or "screenshot" in clause_lower:
            return {"tool": "take_screenshot", "args": {}, "text": clause, "domain": "screen"}
        return None

    def _parse_file_action(self, clause, clause_lower, context):
        active_file = self._active_file_reference()
        pending = getattr(getattr(self.router, "dialog_state", None), "pending_file_request", None)
        # Multi-action on the pending file: "open and read it", "read and summarize it".
        # Prefer the most informative downstream verb so a single tool fires; the
        # file controller still picks up secondary verbs from text via _detect_requested_actions.
        if pending and re.search(
            r"\b(?:open|read|summarize)\s+and\s+(?:open|read|summarize)\s+(?:it|this|that|the file|to me|out loud)\b",
            clause_lower,
        ):
            if "summarize" in clause_lower:
                return {"tool": "summarize_file", "args": {}, "text": clause, "domain": "files"}
            if "read" in clause_lower:
                return {"tool": "read_file", "args": {}, "text": clause, "domain": "files"}
            return {"tool": "open_file", "args": {}, "text": clause, "domain": "files"}
        if pending and re.search(r"\bopen\s+(?:it|this|that|the file)\b", clause_lower):
            return {"tool": "open_file", "args": {}, "text": clause, "domain": "files"}
        if pending and re.search(r"\bread\s+(?:it|this|that|the file)\b", clause_lower):
            return {"tool": "read_file", "args": {}, "text": clause, "domain": "files"}
        if pending and re.search(r"\bsummarize\s+(?:it|this|that|the file)\b", clause_lower):
            return {"tool": "summarize_file", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\b(?:which one|pick|choose|select|option\s+\d+)\b", clause_lower):
            return {"tool": "select_file_candidate", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\b(?:what are|list|show)\b.*\b(?:other\s+)?files?\b", clause_lower):
            return {"tool": "list_folder_contents", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\b(?:summarize|summary of|sum up)\b", clause_lower):
            return {"tool": "summarize_file", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\b(?:read|show contents of|preview)\b", clause_lower) and (
            "file" in clause_lower or "folder" in clause_lower or "it" in clause_lower or context.get("domain") == "files"
        ):
            return {"tool": "read_file", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\bopen\s+(?:the\s+)?folder\b", clause_lower):
            return {"tool": "open_folder", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\bopen\s+(?:the\s+)?(?:file\s+[a-z0-9][a-z0-9 _\-.]*|[a-z0-9][a-z0-9 _\-.]*\s+file)\b", clause_lower):
            return {"tool": "open_file", "args": {}, "text": clause, "domain": "files"}

        if "folder" in clause_lower and "open" in clause_lower:
            return {"tool": "open_file", "args": {}, "text": clause, "domain": "files"}

        if active_file:
            names = {active_file["filename"], active_file["stem"]}
            if re.search(r"\bopen\b", clause_lower) and any(name and re.search(rf"\b{re.escape(name)}\b", clause_lower) for name in names):
                return {"tool": "open_file", "args": {"filename": active_file["filename"]}, "text": clause, "domain": "files"}
            if re.search(r"\bread\b", clause_lower) and any(name and re.search(rf"\b{re.escape(name)}\b", clause_lower) for name in names):
                return {"tool": "read_file", "args": {"filename": active_file["filename"]}, "text": clause, "domain": "files"}
            if re.search(r"\bsummarize\b", clause_lower) and any(name and re.search(rf"\b{re.escape(name)}\b", clause_lower) for name in names):
                return {"tool": "summarize_file", "args": {"filename": active_file["filename"]}, "text": clause, "domain": "files"}

        if re.search(r"\bopen\b", clause_lower) and (
            "it" in clause_lower or re.search(r"\b(?:pdf|txt|md|json|csv|py|docx)\b", clause_lower)
        ):
            return {"tool": "open_file", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\b(?:find|search|locate)\s+(?:for\s+)?(?:file\s+)?\S+", clause_lower):
            return {"tool": "search_file", "args": {}, "text": clause, "domain": "files"}
        file_phrase = re.fullmatch(r"file\s+(.+)", clause_lower)
        if file_phrase:
            return {
                "tool": "search_file",
                "args": {"query": file_phrase.group(1).strip()},
                "text": clause,
                "domain": "files",
            }
        if self._should_recover_file_reference(clause_lower, context):
            return {
                "tool": "search_file",
                "args": {"query": clause.strip()},
                "text": clause,
                "domain": "files",
            }
        return None

    def _parse_manage_file(self, clause, clause_lower, context):
        if "manage_file" not in getattr(self.router, "_tools_by_name", {}):
            return None
        if not re.search(r"\b(?:create|make|write|save|append|add)\b", clause_lower):
            return None

        action = "create"
        if re.search(r"\b(?:append|add)\b", clause_lower):
            action = "append"
        elif re.search(r"\b(?:write|save)\b", clause_lower):
            action = "write"

        filename = ""
        det = r"(?:(?:the|a|an|new)\s+)?"
        patterns = (
            rf"\b(?:to|into|in)\s+{det}file\s+(?:named\s+|called\s+)?([a-z0-9][a-z0-9 _\-.]*)$",
            rf"\b(?:to|into|in)\s+{det}([a-z0-9][a-z0-9 _\-.]*)\s+file$",
            r"\b(?:file\s+)?(?:named|called)\s+([a-z0-9][a-z0-9 _\-.]*)$",
            rf"\b(?:create|make)\s+{det}file\s+(?:named\s+|called\s+)?([a-z0-9][a-z0-9 _\-.]*)$",
            rf"\b(?:to|into|in)\s+{det}(?!file\b|document\b)([a-z0-9][a-z0-9 _\-]*\.(?:pdf|txt|md|json|csv|py|docx))$",
            rf"\b(?:to|into|in)\s+{det}(?!file\b|document\b)([a-z0-9][a-z0-9 _\-]+?\s+(?:pdf|txt|md|json|csv|py|docx))$",
        )
        for pattern in patterns:
            match = re.search(pattern, clause_lower)
            if match:
                filename = " ".join(match.group(1).strip(" .,!?:;\"'").split())
                break

        if not filename:
            active_file = self._active_file_reference()
            if active_file and action in {"write", "append"}:
                filename = active_file["filename"]
            elif context.get("domain") == "files" and action in {"write", "append"}:
                return {
                    "tool": "manage_file",
                    "args": {"action": action},
                    "text": clause,
                    "domain": "files",
                }
            else:
                return None

        return {
            "tool": "manage_file",
            "args": {"action": action, "filename": filename},
            "text": clause,
            "domain": "files",
        }

    def _parse_reminder(self, clause, clause_lower, context):
        tools = getattr(self.router, "_tools_by_name", {})

        if "create_calendar_event" in tools and re.search(
            r"\b(?:create|add|schedule|set\s+up|book)\b.*\b(?:calendar\s+event|event|meeting|appointment)\b",
            clause_lower,
        ):
            return {"tool": "create_calendar_event", "args": {}, "text": clause, "domain": "calendar"}
        if "create_calendar_event" in tools and re.search(
            r"\badd\s+(?:.+?)\s+to\s+(?:my\s+)?calendar\b",
            clause_lower,
        ):
            return {"tool": "create_calendar_event", "args": {}, "text": clause, "domain": "calendar"}

        if "move_calendar_event" in tools and re.search(
            r"\b(?:move|reschedule|shift|push|change)\b.*\b(?:reminder|event|meeting|appointment|standup|gym|focus|block|the\s+next|the\s+\d{1,2}(?:\s*(?:am|pm))?)\b.*\b(?:to|by|until|forward|back|ahead|earlier|later)\b",
            clause_lower,
        ):
            return {"tool": "move_calendar_event", "args": {}, "text": clause, "domain": "calendar"}
        # "move my 3 PM to 4 PM", "shift my 9 AM by an hour" — clock-time targets.
        if "move_calendar_event" in tools and re.search(
            r"\b(?:move|reschedule|shift|push|change)\s+(?:my\s+|the\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s+(?:to|by)\b",
            clause_lower,
        ):
            return {"tool": "move_calendar_event", "args": {}, "text": clause, "domain": "calendar"}
        if "move_calendar_event" in tools and re.search(
            r"\b(?:move|reschedule|shift|push|change)\s+(?:the\s+|my\s+)?(?:next|upcoming)\b",
            clause_lower,
        ):
            return {"tool": "move_calendar_event", "args": {}, "text": clause, "domain": "calendar"}

        if "cancel_calendar_event" in tools and re.search(
            r"\b(?:cancel|delete|remove|drop)\b.*\b(?:reminder|calendar\s+event|event|meeting|appointment|block|standup|gym\s+block|focus\s+block)\b",
            clause_lower,
        ):
            return {"tool": "cancel_calendar_event", "args": {}, "text": clause, "domain": "calendar"}

        if "remind me" in clause_lower or re.search(r"\bset (?:a )?reminder\b", clause_lower):
            return {"tool": "set_reminder", "args": {}, "text": clause, "domain": "reminder"}
        return None

    def _parse_notes(self, clause, clause_lower, context):
        if re.search(r"\b(?:save note|note down|remember this|remember that)\b", clause_lower):
            return {"tool": "save_note", "args": {}, "text": clause, "domain": "notes"}
        if re.search(r"\b(?:read|show|list)\s+(?:my\s+)?notes\b", clause_lower):
            return {"tool": "read_notes", "args": {}, "text": clause, "domain": "notes"}
        return None

    def _parse_voice_toggle(self, clause, clause_lower, context):
        mode_match = re.search(
            r"\b(?:set|switch|change)\s+(?:voice|conversation|listening)\s+mode\s+(?:to\s+)?(persistent|always on|on[-\s]?demand|manual|off)\b",
            clause_lower,
        )
        if mode_match:
            mode = mode_match.group(1).replace("-", "_").replace(" ", "_")
            if mode == "always_on":
                mode = "persistent"
            if mode == "off":
                mode = "manual"
            return {"tool": "set_voice_mode", "args": {"mode": mode}, "text": clause, "domain": "voice"}
        if re.search(r"\b(?:use|enable)\s+on[-\s]?demand\s+(?:voice|conversation|listening)\b", clause_lower):
            return {"tool": "set_voice_mode", "args": {"mode": "on_demand"}, "text": clause, "domain": "voice"}
        if re.search(r"\b(?:use|enable)\s+(?:persistent|always on)\s+(?:voice|conversation|listening)\b", clause_lower):
            return {"tool": "set_voice_mode", "args": {"mode": "persistent"}, "text": clause, "domain": "voice"}
        if re.search(r"\bfriday\s+wake\s+up\b", clause_lower) or re.fullmatch(r"wake\s+up", clause_lower.strip()):
            return {"tool": "enable_voice", "args": {"wake_up": True}, "text": clause, "domain": "voice"}
        if re.search(r"\b(?:enable|start|turn on)\s+(?:the\s+)?(?:mic|microphone|voice)\b", clause_lower):
            return {"tool": "enable_voice", "args": {}, "text": clause, "domain": "voice"}
        if re.search(r"\b(?:disable|stop|turn off)\s+(?:the\s+)?(?:mic|microphone|voice)\b", clause_lower):
            return {"tool": "disable_voice", "args": {}, "text": clause, "domain": "voice"}
        return None

    def _parse_help(self, clause, clause_lower, context):
        if re.search(r"\bhelp\b", clause_lower) or re.search(r"\bwhat\s+(?:else\s+)?can\s+you\s+do\b", clause_lower):
            return {"tool": "show_help", "args": {}, "text": clause, "domain": "help"}
        return None

    def _parse_exit(self, clause, clause_lower, context):
        if re.fullmatch(r"(?:bye|goodbye|exit|quit|stop assistant)(?:\s+friday)?[.!?]?", clause_lower) or \
           re.search(r"\b(?:shut down|shutdown|close|exit|quit)\s+(?:friday|the assistant|yourself)\b", clause_lower):
            return {"tool": "shutdown_assistant", "args": {}, "text": clause, "domain": "system"}
        return None

    def _parse_greeting(self, clause, clause_lower, context):
        if re.fullmatch(r"(?:hi|hello|hey|good morning|good afternoon|good evening)[.!?]?", clause_lower):
            return {"tool": "greet", "args": {}, "text": clause, "domain": "greeting"}
        return None

    def _parse_confirmation(self, clause, clause_lower, context):
        if re.fullmatch(r"(?:yes|yeah|yep|sure|okay|ok|open it|do it)[.!?]?", clause_lower):
            return {"tool": "confirm_yes", "args": {}, "text": clause, "domain": "confirmation"}
        if re.fullmatch(r"(?:no|nope|cancel|stop)[.!?]?", clause_lower):
            return {"tool": "confirm_no", "args": {}, "text": clause, "domain": "confirmation"}
        return None

    def _extract_count(self, text):
        match = re.search(r"\b(\d+)\s+(?:times?|steps?|levels?)\b", text)
        if match:
            return max(1, int(match.group(1)))
        return 1

    def _extract_volume_percent(self, clause_lower, context):
        patterns = (
            r"\b(?:set|change|make|turn)\s+(?:the\s+)?volume\s+(?:to|at)\s+(\d{1,3})(?:\s*(?:percent|%))?\b",
            r"\bvolume\s+(?:to|at)\s+(\d{1,3})(?:\s*(?:percent|%))?\b",
        )
        for pattern in patterns:
            match = re.search(pattern, clause_lower)
            if match:
                return max(0, min(100, int(match.group(1))))

        if context.get("domain") == "volume":
            match = re.fullmatch(r"(?:to\s+)?(\d{1,3})(?:\s*(?:percent|%))?", clause_lower.strip())
            if match:
                return max(0, min(100, int(match.group(1))))
        return None

    def _active_browser_workflow(self):
        store = getattr(self.router, "context_store", None)
        session_id = getattr(self.router, "session_id", None)
        if not store or not session_id:
            return None
        return store.get_active_workflow(session_id, workflow_name="browser_media")

    def _default_browser_platform(self, query, active_browser):
        if active_browser and active_browser.get("platform") in {"youtube", "youtube_music"}:
            return active_browser["platform"]
        if re.search(r"\b(?:song|music|album|playlist)\b", query):
            return "youtube_music"
        return "youtube"

    def _should_recover_file_reference(self, clause_lower, context):
        normalized = clause_lower.strip(" .!?")
        if not normalized:
            return False
        if context.get("domain") != "files":
            return False
        if re.search(
            r"\b(?:open|launch|start|play|take|capture|find|search|locate|set|save|write|append|add|read|show|list|get|check|tell|what|summarize|summary|remind|enable|disable|turn|mute|unmute|increase|decrease|lower|raise|stop|pause)\b",
            normalized,
        ):
            return False
        tokens = normalized.split()
        if len(tokens) > 8:
            return False
        disallowed = {
            "a", "an", "the", "in", "on", "at", "to", "for", "with", "from", "within",
            "inside", "outside", "is", "are", "was", "were", "be", "being", "been",
            "please", "can", "could", "would", "should", "will", "not",
            "yes", "yeah", "yep", "sure", "okay", "ok", "no", "nope", "cancel", "stop",
        }
        if any(token in disallowed for token in tokens):
            return False
        return bool(re.fullmatch(r"[a-z0-9][a-z0-9 ._\-]*", normalized))

    def _active_file_reference(self):
        dialog_state = getattr(self.router, "dialog_state", None)
        selected_file = getattr(dialog_state, "selected_file", None) if dialog_state else None
        if selected_file:
            filename = os.path.basename(selected_file).lower()
            return {"filename": filename, "stem": os.path.splitext(filename)[0]}

        store = getattr(self.router, "context_store", None)
        session_id = getattr(self.router, "session_id", None)
        if not store or not session_id:
            return None
        workflow = store.get_active_workflow(session_id, workflow_name="file_workflow") or {}
        target = workflow.get("target") or {}
        filename = os.path.basename(target.get("path", "") or target.get("filename", "")).lower()
        if not filename:
            return None
        return {"filename": filename, "stem": os.path.splitext(filename)[0]}
