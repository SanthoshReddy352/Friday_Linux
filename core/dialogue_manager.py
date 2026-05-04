"""DialogueManager — contextual acks, tone matching, and pacing.

Phase 9: Replaces generic "On it..." / "Done." with content-aware
responses. Manages tone switching between casual ↔ task-focused based on
the detected user mood and persona configuration.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.capability_broker import ToolPlan


# ---------------------------------------------------------------------------
# Ack templates per domain
# ---------------------------------------------------------------------------

_DOMAIN_ACKS: dict[str, str] = {
    "weather": "Fetching weather data...",
    "calendar": "Checking your calendar...",
    "email": "Looking at your emails...",
    "task": "Pulling up your tasks...",
    "reminder": "Setting that reminder now.",
    "file": "On it — finding that file.",
    "screenshot": "Taking a screenshot.",
    "volume": "Adjusting volume.",
    "battery": "Checking battery status.",
    "cpu": "Pulling system stats.",
    "ram": "Checking memory usage.",
    "youtube": "Opening YouTube now.",
    "music": "Starting the music.",
    "browser": "Opening the browser.",
    "search": "Searching now.",
    "news": "Fetching the latest news...",
    "note": "Saving your note.",
    "shutdown": "Understood. Shutting down.",
    "launch": "Launching that for you.",
    "read": "Reading that file now.",
    "summarize": "Summarizing that for you.",
    "chat": "Let me think about that.",
}

_TONE_STARTERS: dict[str, tuple[str, ...]] = {
    "frustrated": (r"\b(?:why|seriously|again|ugh|come on|not working|broken)\b",),
    "urgent": (r"\b(?:quick|quickly|asap|now|hurry|right now|fast)\b",),
    "curious": (r"\b(?:how|what|why|could you|can you|would you|tell me)\b",),
    "warm": (r"\b(?:please|thanks|thank you|appreciate|great|awesome|love)\b",),
}


class DialogueManager:
    """Provides contextual acknowledgements and tone-aware response adaptation.

    Injected into CapabilityBroker and TurnManager so both planning and
    execution phases can emit appropriately phrased feedback.
    """

    def __init__(self, config=None):
        self._config = config
        self._current_tone: str = "neutral"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def contextual_ack(self, user_text: str, plan: "ToolPlan | None" = None) -> str:
        """Return a context-aware acknowledgement for the pending action.

        Falls back to a generic ack if no domain-specific template matches.
        Returns "" (no ack) for fast interactive commands.
        """
        if plan is not None:
            # No ack for instant commands — only for slow/online/multi-step
            latency = getattr(plan, "estimated_latency", "interactive")
            steps = getattr(plan, "steps", [])
            if latency == "interactive" and len(steps) <= 1:
                return ""
            # Use plan's existing ack if it's already contextual
            existing = getattr(plan, "ack", "")
            if existing and existing not in ("I'll handle that in steps.", "I'm with you.", "Let me think that through."):
                return existing

        return self._ack_from_text(user_text) or ""

    def detect_tone(self, text: str) -> str:
        """Classify user tone: frustrated | urgent | curious | warm | neutral."""
        lowered = (text or "").lower()
        for tone, patterns in _TONE_STARTERS.items():
            if any(re.search(p, lowered) for p in patterns):
                self._current_tone = tone
                return tone
        self._current_tone = "neutral"
        return "neutral"

    def adapt_response(self, response: str, tone: str | None = None) -> str:
        """Lightly adapt *response* to match the detected or given tone.

        Keeps changes minimal — mainly capitalization / brevity for urgent,
        empathetic prefix for frustrated.
        """
        t = tone or self._current_tone
        if not response:
            return response
        if t == "frustrated":
            return f"I hear you. {response}"
        if t == "urgent":
            # Strip filler phrases for urgency
            for filler in ("Let me ", "I'll go ahead and ", "Sure thing, "):
                if response.startswith(filler):
                    response = response[len(filler):]
                    response = response[0].upper() + response[1:]
        return response

    def clarification_prompt(self, partial_text: str) -> str:
        """Return a clarification question for ambiguous input."""
        return f"I didn't quite catch that. Could you rephrase? You said: '{partial_text[:60]}'"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ack_from_text(self, text: str) -> str:
        lowered = (text or "").lower()
        for domain, ack in _DOMAIN_ACKS.items():
            if domain in lowered:
                return ack
        return ""
