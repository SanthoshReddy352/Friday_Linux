"""RouteScorer — deterministic capability routing extracted from CommandRouter.

Phase 5: Moves the scoring/matching logic out of CommandRouter so that
CapabilityBroker can find the best route without importing the router at all.

The scorer consumes a list of "route entries" with the same shape the router
builds internally:
    {
        "spec": {"name": str, "description": str, ...},
        "aliases": [str, ...],
        "patterns": [compiled re, ...],
        "context_terms": [str, ...],
    }

RouteScorer can also build route entries from plain CapabilityDescriptors so
CapabilityRegistry can eventually replace the router's tool list entirely.
"""
from __future__ import annotations

import re
from typing import Callable


# ---------------------------------------------------------------------------
# Default routing metadata per tool name
# (identical to what CommandRouter._default_*_for builds)
# ---------------------------------------------------------------------------

_DEFAULT_ALIASES: dict[str, set[str]] = {
    "greet": {"hello", "hi", "hey", "hey friday", "good morning", "good evening"},
    "show_help": {"help", "what can you do", "show help", "show commands"},
    "launch_app": {"open", "launch", "start"},
    "set_volume": {"volume up", "volume down", "mute", "increase volume", "decrease volume"},
    "take_screenshot": {"screenshot", "screen shot", "capture screen"},
    "search_file": {"find file", "search file", "locate file"},
    "open_file": {"open file"},
    "get_system_status": {"system status", "system health"},
    "get_battery": {"battery", "battery status"},
    "get_cpu_ram": {"cpu", "ram", "memory usage"},
    "set_reminder": {"remind me", "set reminder"},
    "save_note": {"save note", "note down", "remember this"},
    "read_notes": {"read notes", "show notes", "my notes"},
    "get_time": {"time", "what time is it"},
    "get_date": {"date", "today's date", "what day is it"},
    "manage_file": {"create file", "make file", "new file", "write it to", "save it to", "write that to", "save that to"},
    "enable_voice": {"enable voice", "start listening", "turn on mic", "turn on microphone"},
    "disable_voice": {"disable voice", "stop listening", "turn off mic", "turn off microphone"},
    "confirm_yes": {"yes", "yeah", "open it", "do it", "sure", "okay"},
    "confirm_no": {"no", "nope", "cancel", "stop that"},
    "select_file_candidate": {"first one", "second one", "this one", "that one", "option 1", "option 2"},
    "search_google": {
        "search google", "google search", "google for", "look up", "google it",
        "search the web", "search online", "web search",
    },
    # Google Workspace tools
    "check_unread_emails": {
        "unread emails", "check email", "check gmail", "my emails", "new emails",
        "latest email", "latest emails", "recent email", "recent emails",
        "any emails", "any new emails", "any new mail", "show emails",
        "read my email", "what's in my inbox", "inbox",
    },
    "read_email": {"read email", "read this email", "open email", "read the email"},
    "read_latest_email": {
        "read my latest email", "read the latest email", "read latest email",
        "read my newest email", "read most recent email", "read my last email",
        "open my latest email", "show me my latest email",
    },
    "get_calendar_today": {
        "today's calendar", "what's on my calendar", "my schedule today",
        "today's schedule", "what's on today", "what do i have today",
        "my day", "today's events",
    },
    "get_calendar_week": {"this week's calendar", "week schedule", "upcoming events", "what's this week"},
    "get_calendar_agenda": {"agenda", "next events", "upcoming", "calendar"},
    "search_drive": {"search drive", "find in drive", "drive search"},
    "daily_briefing": {"daily briefing", "morning briefing", "daily summary"},
}

_DEFAULT_CONTEXT_TERMS: dict[str, set[str]] = {
    "greet": {"greet", "greeting"},
    "show_help": {"help", "commands", "abilities"},
    "launch_app": {"application", "app", "browser", "firefox", "chrome"},
    "set_volume": {"volume", "audio", "sound", "mute"},
    "take_screenshot": {"screenshot", "screen", "capture"},
    "search_file": {"find", "search", "file", "locate"},
    "open_file": {"open", "file", "document"},
    "get_system_status": {"system", "status", "health"},
    "get_battery": {"battery", "charge"},
    "get_cpu_ram": {"cpu", "ram", "memory"},
    "set_reminder": {"reminder", "remind"},
    "save_note": {"note", "remember", "save"},
    "read_notes": {"notes", "read", "show"},
    "get_time": {"time", "clock"},
    "get_date": {"date", "day", "today"},
    "manage_file": {"create", "file", "document", "write"},
    "enable_voice": {"voice", "microphone", "mic", "listen"},
    "disable_voice": {"voice", "microphone", "mic", "stop"},
    "search_google": {"google", "search", "web", "internet", "lookup", "look", "up"},
    # Google Workspace
    "check_unread_emails": {"email", "emails", "gmail", "unread", "inbox", "mail", "latest", "recent", "new"},
    "read_email": {"email", "read", "message"},
    "read_latest_email": {"email", "latest", "newest", "recent", "last", "read", "inbox"},
    "get_calendar_today": {"calendar", "schedule", "today", "events", "agenda", "meetings", "day"},
    "get_calendar_week": {"calendar", "schedule", "week", "events"},
    "get_calendar_agenda": {"calendar", "agenda", "events", "upcoming"},
    "search_drive": {"drive", "file", "document", "search"},
    "daily_briefing": {"briefing", "summary", "morning", "daily"},
}

_DEFAULT_PATTERNS: dict[str, list[str]] = {
    "greet": [r"\b(hi|hello|hey|good morning|good afternoon|good evening)\b"],
    "show_help": [r"\bhelp\b", r"what can you do", r"show (?:me )?(?:the )?commands"],
    "launch_app": [r"\b(?:open|launch|start|bring up)\s+(?!file\b)[a-z0-9][\w\-\s,]*"],
    "set_volume": [r"\b(?:volume|mute|unmute)\b", r"\b(?:increase|decrease|turn)\s+volume\b"],
    "take_screenshot": [r"\b(?:take|capture).*(?:screenshot|screen shot)\b", r"\bscreenshot\b"],
    "search_file": [r"\b(?:find|search|locate)\s+(?:for\s+)?(?:file\s+)?\S+"],
    "open_file": [r"\bopen\s+(?:the\s+)?file\b"],
    "get_system_status": [r"\b(?:system status|system health)\b"],
    "get_battery": [r"\bbattery\b"],
    "get_cpu_ram": [r"\b(?:cpu|ram|memory usage)\b"],
    "set_reminder": [r"\bremind me\b", r"\bset (?:a )?reminder\b"],
    "save_note": [r"\b(?:save note|note down|remember this|remember that)\b"],
    "read_notes": [r"\b(?:read|show|list)\s+(?:my\s+)?notes\b"],
    "get_time": [r"\b(?:what(?:'s| is)? the time|what time is it|current time)\b", r"\btime\b"],
    "get_date": [r"\b(?:today(?:'s)? date|what day is it|current date)\b", r"\bdate\b"],
    "manage_file": [
        r"\b(?:create|make)\s+(?:a\s+)?file\b",
        r"\b(?:write|save|append|add)\s+(?:it|that|this|the answer|the response)\s+(?:to|into|in)\s+\S+",
    ],
    "enable_voice": [r"\b(?:enable|start|turn on)\s+(?:the\s+)?(?:mic|microphone|voice)\b"],
    "disable_voice": [r"\b(?:disable|stop|turn off)\s+(?:the\s+)?(?:mic|microphone|voice)\b"],
    "confirm_yes": [r"^(?:yes|yeah|yep|sure|okay|ok|open it|do it)$"],
    "confirm_no": [r"^(?:no|nope|cancel|stop)$"],
    "search_google": [
        r"\bsearch\s+google\b",
        r"\bgoogle\s+(?:search\s+)?(?:for|it)\b",
        r"\b(?:search|look\s+up)\s+(?:on|in)\s+google\b",
        r"\bsearch\s+the\s+(?:web|internet)\b",
        r"\blook\s+up\s+\S+",
    ],
    # Google Workspace
    "check_unread_emails": [
        r"\b(?:check|show|read|get|fetch|pull)\s+(?:up\s+)?(?:my\s+)?(?:unread\s+)?(?:emails?|gmail|inbox|mail)\b",
        r"\b(?:any|got|new|latest|recent|received)\s+(?:new\s+)?(?:emails?|mails?|gmails?)\b",
        r"\bwhat(?:'s| is)\s+(?:in\s+)?(?:my\s+)?(?:inbox|emails?|mail)\b",
        r"\bwhat(?:'s| is)\s+my\s+(?:latest|most\s+recent|newest)\s+(?:emails?|mails?)\b",
        r"\bdo\s+i\s+have\s+(?:any\s+)?(?:new\s+)?emails?\b",
        r"\bunread\b",
    ],
    "read_email": [r"\bread\s+(?:this|the|that)?\s*email\b", r"\bopen\s+(?:that|this|the)\s+email\b"],
    "read_latest_email": [
        r"\b(?:read|open|show)\s+(?:me\s+)?(?:my\s+|the\s+)?(?:latest|most\s+recent|newest|last|recent)\s+(?:unread\s+)?email\b",
        r"\bwhat'?s?\s+(?:in\s+)?my\s+(?:latest|most\s+recent|newest)\s+email\b",
    ],
    "get_calendar_today": [
        r"\b(?:what(?:'s| is|s)\s+on\s+(?:my\s+)?)?calendar\b.*\btoday\b",
        r"\btoday'?s?\s+(?:schedule|events?|calendar|agenda|meetings?)\b",
        r"\b(?:what(?:'s| is|s|\s+do\s+i\s+have))\s+(?:on\s+)?(?:my\s+)?(?:schedule|calendar|agenda|day|today)\b",
        r"\bany\s+(?:meetings?|events?)\s+today\b",
    ],
    "get_calendar_week": [r"\bweek(?:ly)?\s+(?:schedule|calendar|events?)\b", r"\bthis\s+week\b"],
    "get_calendar_agenda": [r"\b(?:upcoming\s+)?events?\b", r"\bagenda\b", r"\bschedule\b"],
    "search_drive": [r"\b(?:find|search|look\s+for)\s+(?:in\s+)?drive\b", r"\bgoogle\s+drive\b"],
    "daily_briefing": [r"\b(?:daily|morning)\s+(?:briefing|summary)\b", r"\bwhat'?s?\s+(?:on\s+)?(?:today|the\s+agenda)\b"],
}


class RouteScorer:
    """Score capability routes against user text without requiring CommandRouter.

    Accepts a callable that returns the current tools list so it always reflects
    newly registered capabilities.
    """

    def __init__(self, tools_getter: Callable[[], list[dict]]):
        self._get_tools = tools_getter

    # ------------------------------------------------------------------
    # Public API (same shape as CommandRouter.find_best_route)
    # ------------------------------------------------------------------

    def find_best_route(self, text: str, min_score: int = 20) -> dict | None:
        text_lower = _normalize(text)
        best_route = None
        best_score = 0
        for route in self._get_tools():
            if route["spec"]["name"] == "llm_chat":
                continue
            score = self._score_route(route, text_lower)
            if score > best_score:
                best_score = score
                best_route = route
        return best_route if best_score >= min_score else None

    # ------------------------------------------------------------------
    # Factory: build route entry from a plain spec dict
    # ------------------------------------------------------------------

    @classmethod
    def build_route_entry(cls, spec: dict, callback) -> dict:
        """Build a route entry dict from a capability spec + callback."""
        return {
            "spec": spec,
            "callback": callback,
            "aliases": cls._build_aliases(spec),
            "patterns": cls._build_patterns(spec),
            "context_terms": cls._build_context_terms(spec),
        }

    # ------------------------------------------------------------------
    # Scoring internals (extracted from CommandRouter._score_route)
    # ------------------------------------------------------------------

    @staticmethod
    def _score_route(route: dict, text_lower: str) -> int:
        score = 0

        if text_lower in route.get("aliases", []):
            score = max(score, 120)

        for pattern in route.get("patterns", []):
            if pattern.fullmatch(text_lower):
                score = max(score, 110)
            elif pattern.search(text_lower):
                score = max(score, 90)

        for alias in route.get("aliases", []):
            if alias == text_lower:
                score = max(score, 120)
            elif len(alias) > 2 and re.search(rf"\b{re.escape(alias)}\b", text_lower):
                score = max(score, 40 + len(alias.split()))

        for term in route.get("context_terms", []):
            if len(term) > 2 and re.search(rf"\b{re.escape(term)}\b", text_lower):
                score += 6

        tool_name_words = route["spec"]["name"].split("_")
        if tool_name_words and all(word in text_lower for word in tool_name_words):
            score = max(score, 25)

        return score

    # ------------------------------------------------------------------
    # Route entry builders
    # ------------------------------------------------------------------

    @classmethod
    def _build_aliases(cls, spec: dict) -> list[str]:
        name = spec["name"]
        aliases = set(spec.get("aliases", []))
        aliases.add(name.replace("_", " "))
        aliases.update(_DEFAULT_ALIASES.get(name, set()))
        return sorted(a for a in aliases if a)

    @classmethod
    def _build_patterns(cls, spec: dict) -> list:
        name = spec["name"]
        raw = list(spec.get("patterns", []) or []) + _DEFAULT_PATTERNS.get(name, [])
        compiled = []
        for p in raw:
            if isinstance(p, str):
                try:
                    compiled.append(re.compile(p, re.IGNORECASE))
                except re.error:
                    pass
            else:
                compiled.append(p)
        return compiled

    @classmethod
    def _build_context_terms(cls, spec: dict) -> list[str]:
        name = spec["name"]
        terms = set(spec.get("context_terms", []))
        terms.update(name.split("_"))
        terms.update(_DEFAULT_CONTEXT_TERMS.get(name, set()))
        return sorted(t for t in terms if t)


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().strip().split())
