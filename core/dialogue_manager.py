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
# Keys are matched against lowercased user text — put multi-word keys first
# so they win over shorter overlapping keys.
# ---------------------------------------------------------------------------

_DOMAIN_ACKS: dict[str, str] = {
    # --- Multi-word keys first (higher specificity) ---
    "world monitor": "Let me get the latest news.",
    "good news": "Let me find something uplifting.",
    "tech news": "Pulling up tech news.",
    "finance news": "Checking the markets.",
    "energy news": "Pulling up energy news.",
    "commodity news": "Checking commodity prices.",
    "daily briefing": "Pulling up your briefing.",
    "morning briefing": "Pulling up your briefing.",
    "unread email": "Checking your inbox.",
    "latest email": "Let me pull that up.",
    "google drive": "Searching your Drive.",
    "search drive": "Searching your Drive.",
    # --- Single-word keys ---
    "weather": "Let me check the weather.",
    "calendar": "Checking your calendar.",
    "email": "Let me check your inbox.",
    "gmail": "Checking your inbox.",
    "inbox": "Let me check your inbox.",
    "task": "Let me pull up your tasks.",
    "reminder": "Setting that.",
    "file": "Looking for that.",
    "drive": "Searching your Drive.",
    "screenshot": "Analyzing the screen.",
    "volume": "Done.",
    "battery": "Checking battery.",
    "cpu": "Let me check.",
    "ram": "Let me check.",
    "youtube": "Opening YouTube.",
    "music": "On it.",
    "browser": "Opening that.",
    "search": "Looking that up.",
    "news": "Pulling up the news.",
    "briefing": "Pulling up your briefing.",
    "research": "Starting research — back in a moment.",
    "document": "Searching your documents.",
    "note": "Saving that.",
    "shutdown": "Sure, shutting down.",
    "launch": "Opening that.",
    "read": "Let me read that.",
    "summarize": "Let me take a look.",
    "analyze": "Taking a look.",
    "screen": "Analyzing the screen.",
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
            generic_ack = existing.strip().lower()
            if (
                existing
                and generic_ack not in ("i'll handle that in steps.", "i'm with you.")
                and "think that through" not in generic_ack
            ):
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
            return f"Got it. {response}"
        if t == "urgent":
            for filler in ("Let me ", "I'll go ahead and ", "Sure thing, "):
                if response.startswith(filler):
                    response = response[len(filler):]
                    response = response[0].upper() + response[1:]
        return response

    def clarification_prompt(self, partial_text: str) -> str:
        """Return a clarification question for ambiguous input."""
        return f"Sorry, I didn't catch that. Could you say that again?"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ack_from_text(self, text: str) -> str:
        lowered = (text or "").lower()
        for domain, ack in _DOMAIN_ACKS.items():
            if domain in lowered:
                return ack
        return ""
