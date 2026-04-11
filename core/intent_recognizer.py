import re
import os

from modules.system_control.app_launcher import extract_app_names


class IntentRecognizer:
    def __init__(self, router):
        self.router = router

    def plan(self, text, context=None):
        cleaned = self._clean_text(text)
        if not cleaned:
            return []

        actions = []
        current_context = dict(context or {})
        clauses = self._split_into_clauses(cleaned)
        for clause in clauses:
            action = self._parse_clause(clause, current_context)
            if not action:
                return []
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

        lower_clause = clause.lower()
        marker = " and "
        idx = lower_clause.find(marker)
        while idx != -1:
            left = clause[:idx].strip(" ,")
            right = clause[idx + len(marker):].strip(" ,")
            if left and right and self._looks_like_action_start(right):
                return self._split_on_action_and(left) + self._split_on_action_and(right)
            idx = lower_clause.find(marker, idx + len(marker))
        return [clause.strip()]

    def _is_multi_app_launch_clause(self, clause):
        clause_lower = clause.lower()
        if not re.search(r"\b(?:open|launch|start|bring up)\b", clause_lower):
            return False
        if re.search(r"\b(?:file|folder)\b", clause_lower):
            return False
        return len(extract_app_names(clause_lower)) > 1

    def _looks_like_action_start(self, text):
        normalized = text.lower().strip()
        starters = (
            "open", "launch", "start", "bring up", "take", "capture", "find", "search",
            "locate", "set", "save", "read", "show", "list", "get", "check", "tell",
            "what", "summarize", "summary", "remind", "enable", "disable", "turn",
            "mute", "unmute", "increase", "decrease", "lower", "raise", "stop", "pause",
        )
        return any(normalized.startswith(starter) for starter in starters)

    def _parse_clause(self, clause, context):
        clause_lower = clause.lower().strip()

        for parser in (
            self._parse_pending_selection,
            self._parse_launch_app,
            self._parse_volume,
            self._parse_system,
            self._parse_time_date,
            self._parse_screenshot,
            self._parse_file_action,
            self._parse_reminder,
            self._parse_notes,
            self._parse_voice_toggle,
            self._parse_help,
            self._parse_greeting,
            self._parse_confirmation,
        ):
            action = parser(clause, clause_lower, context)
            if action:
                return action

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
        if re.search(r"\b(?:what(?:'s| is)? the time|what time is it|current time|tell me(?: the)? time)\b", clause_lower):
            return {"tool": "get_time", "args": {}, "text": clause, "domain": "time"}

        if re.search(r"\b(?:today(?:'s)? date|what day is it|current date|tell me(?: the)? date)\b", clause_lower):
            return {"tool": "get_date", "args": {}, "text": clause, "domain": "date"}

        return None

    def _parse_screenshot(self, clause, clause_lower, context):
        if re.search(r"\b(?:take|capture).*(?:screenshot|screen shot)\b", clause_lower) or "screenshot" in clause_lower:
            return {"tool": "take_screenshot", "args": {}, "text": clause, "domain": "screen"}
        return None

    def _parse_file_action(self, clause, clause_lower, context):
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

        if re.search(r"\bopen\s+(?:the\s+)?file\b", clause_lower):
            return {"tool": "open_file", "args": {}, "text": clause, "domain": "files"}

        if "folder" in clause_lower and "open" in clause_lower:
            return {"tool": "open_file", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\bopen\b", clause_lower) and (
            "it" in clause_lower or re.search(r"\b(?:pdf|txt|md|json|csv|py|docx)\b", clause_lower)
        ):
            return {"tool": "open_file", "args": {}, "text": clause, "domain": "files"}

        if re.search(r"\b(?:find|search|locate)\s+(?:for\s+)?(?:file\s+)?\S+", clause_lower):
            return {"tool": "search_file", "args": {}, "text": clause, "domain": "files"}
        return None

    def _parse_reminder(self, clause, clause_lower, context):
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
        if re.search(r"\b(?:enable|start|turn on)\s+(?:the\s+)?(?:mic|microphone|voice)\b", clause_lower):
            return {"tool": "enable_voice", "args": {}, "text": clause, "domain": "voice"}
        if re.search(r"\b(?:disable|stop|turn off)\s+(?:the\s+)?(?:mic|microphone|voice)\b", clause_lower):
            return {"tool": "disable_voice", "args": {}, "text": clause, "domain": "voice"}
        return None

    def _parse_help(self, clause, clause_lower, context):
        if re.search(r"\bhelp\b", clause_lower) or "what can you do" in clause_lower:
            return {"tool": "show_help", "args": {}, "text": clause, "domain": "help"}
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
