"""ConsentService — single source of truth for online-consent and
confirmation-intent detection.

Previously these regex constants and helper methods were copy-pasted into
both CapabilityBroker and ConversationAgent (and partially into the old
CommandRouter). Phase 3 consolidates them here.

ConsentService is stateless — it inspects text and capability descriptors
but never mutates application state itself. Callers (CapabilityBroker,
ConversationAgent) handle state changes (set_pending_online, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.capability_registry import CapabilityDescriptor


# ---------------------------------------------------------------------------
# Canonical pattern sets — ONE definition, consumed everywhere
# ---------------------------------------------------------------------------

EXPLICIT_ONLINE_PATTERNS: tuple[str, ...] = (
    r"\bsearch (?:the )?(?:web|internet|online)\b",
    r"\blook (?:it|this|that) up\b",
    r"\bgo online\b",
    r"\bcheck (?:online|the web|the internet)\b",
    r"\bbrowse\b",
    r"\bopen (?:youtube|youtube music|website|browser)\b",
    r"\bplay\b.+\b(?:on|in)\s+youtube(?:\s+music)?\b",
)

POSITIVE_CONFIRMATION_PATTERNS: tuple[str, ...] = (
    r"\byes\b",
    r"\byeah\b",
    r"\byep\b",
    r"\bsure\b",
    r"\bok(?:ay)?\b",
    r"\bdo it\b",
    r"\bgo ahead\b",
    r"\bgo online\b",
)

NEGATIVE_CONFIRMATION_PATTERNS: tuple[str, ...] = (
    r"\bno\b",
    r"\bnope\b",
    r"\bcancel\b",
    r"\bstop\b",
    r"\bstay offline\b",
    r"\bdon't\b",
    r"\bdo not\b",
)

CURRENT_INFO_PATTERNS: tuple[str, ...] = (
    r"\bweather\b",
    r"\bnews\b",
    r"\blatest\b",
    r"\bcurrent\b",
    r"\btoday'?s\b",
    r"\bprice of\b",
    r"\bwhat'?s happening\b",
)

# Tools whose online nature is implicitly consented to (play intents are
# explicit enough that no extra confirmation dialog is needed).
_IMPLICIT_ONLINE_TOOLS: frozenset[str] = frozenset({
    "play_youtube",
    "play_youtube_music",
    "browser_media_control",
})


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class ConsentDecision(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class ConsentResult:
    decision: ConsentDecision
    prompt: str = ""

    @classmethod
    def allow(cls) -> "ConsentResult":
        return cls(decision=ConsentDecision.ALLOW)

    @classmethod
    def ask(cls, prompt: str = "") -> "ConsentResult":
        return cls(decision=ConsentDecision.ASK, prompt=prompt)

    @classmethod
    def deny(cls) -> "ConsentResult":
        return cls(decision=ConsentDecision.DENY)

    @property
    def allowed(self) -> bool:
        return self.decision == ConsentDecision.ALLOW

    @property
    def needs_confirmation(self) -> bool:
        return self.decision == ConsentDecision.ASK


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ConsentService:
    """Evaluate whether a capability may proceed given current consent policy.

    Instantiated once on FridayApp; injected into CapabilityBroker and
    ConversationAgent so neither class needs its own copy of the patterns.
    """

    def __init__(self, config=None):
        self._config = config

    # ------------------------------------------------------------------
    # Primary evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        tool_name: str,
        descriptor: "CapabilityDescriptor | None",
        user_text: str,
    ) -> ConsentResult:
        """Return a ConsentResult for executing `tool_name` given `user_text`."""
        if descriptor is None or descriptor.connectivity != "online":
            return ConsentResult.allow()

        if tool_name in _IMPLICIT_ONLINE_TOOLS:
            return ConsentResult.allow()

        if descriptor.permission_mode == "always_ok":
            # Capability owner has explicitly opted out of consent prompts —
            # don't let a global config override re-enable them.
            return ConsentResult.allow()

        mode = self._online_permission_mode(descriptor.permission_mode)

        if mode == "always":
            return ConsentResult.allow()
        if mode == "never":
            return ConsentResult.deny()

        # ask_first — skip dialog if the user already signalled intent
        if self.is_explicit_online_request(user_text):
            return ConsentResult.allow()

        label = tool_name.replace("_", " ")
        return ConsentResult.ask(prompt=f"Go online for {label}? Say yes or no.")

    # ------------------------------------------------------------------
    # Text classification helpers (public — used by CapabilityBroker etc.)
    # ------------------------------------------------------------------

    def is_explicit_online_request(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        return any(re.search(p, lowered) for p in EXPLICIT_ONLINE_PATTERNS)

    def is_current_info_request(self, text: str) -> bool:
        lowered = (text or "").strip().lower()
        return any(re.search(p, lowered) for p in CURRENT_INFO_PATTERNS)

    def is_positive_confirmation(self, text: str) -> bool:
        normalized = (text or "").strip().lower().strip(" .!?")
        if not normalized:
            return False
        if self.is_negative_confirmation(text):
            return False
        return any(re.search(p, normalized) for p in POSITIVE_CONFIRMATION_PATTERNS)

    def is_negative_confirmation(self, text: str) -> bool:
        normalized = (text or "").strip().lower().strip(" .!?")
        return any(re.search(p, normalized) for p in NEGATIVE_CONFIRMATION_PATTERNS)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _online_permission_mode(self, descriptor_default: str) -> str:
        if self._config and hasattr(self._config, "get"):
            val = self._config.get("conversation.online_permission_mode", None)
            if val:
                return str(val)
        return descriptor_default or "ask_first"
