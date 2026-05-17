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
# Port #3 — ImpactTier + voice-approval gating (mirrors jarvis authority.ts)
# ---------------------------------------------------------------------------

class ImpactTier(Enum):
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"


# Maps side_effect_level values and tool name fragments → ImpactTier.
# Destructive tier: never resolve by voice — requires deliberate re-type.
_IMPACT_MAP: dict[str, ImpactTier] = {
    "read": ImpactTier.READ,
    "write": ImpactTier.WRITE,
    "external": ImpactTier.EXTERNAL,
    "destructive": ImpactTier.DESTRUCTIVE,
}

# Keywords in tool names that escalate to DESTRUCTIVE regardless of side_effect_level.
_DESTRUCTIVE_TOOL_KEYWORDS: tuple[str, ...] = (
    "delete", "remove", "wipe", "format", "drop", "destroy",
    "execute", "run_command", "shell", "terminate", "kill",
    "install", "uninstall", "send_email", "send_message",
    "make_payment", "payment",
)


def _tool_impact_tier(tool_name: str, descriptor=None) -> ImpactTier:
    name_lower = (tool_name or "").lower()
    for kw in _DESTRUCTIVE_TOOL_KEYWORDS:
        if kw in name_lower:
            return ImpactTier.DESTRUCTIVE
    if descriptor is not None:
        sel = str(getattr(descriptor, "side_effect_level", "read") or "read").lower()
        return _IMPACT_MAP.get(sel, ImpactTier.READ)
    return ImpactTier.READ


# Minimum STT confidence to allow voice-approval of non-destructive actions.
_MIN_VOICE_CONFIDENCE: float = 0.85


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
        """Return a ConsentResult for executing `tool_name` given `user_text`.

        Online consent is globally disabled — always allow. Keeping the
        method signature intact so callers don't need to change.
        """
        return ConsentResult.allow()

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
    # Port #3 — Voice-approval gate (mirrors jarvis gateVoiceApprovalResolution)
    # ------------------------------------------------------------------

    def gate_voice_approval(
        self,
        tool_name: str,
        descriptor=None,
        stt_confidence: float = 1.0,
    ) -> "ConsentResult":
        """Decide whether a voice 'yes' may resolve a pending approval.

        Destructive impacts are *never* resolved by voice — the user must
        type the confirmation explicitly. Non-destructive actions require
        STT confidence ≥ _MIN_VOICE_CONFIDENCE to guard against mishearing.

        Returns ConsentResult.allow() or ConsentResult.ask(clarification).
        """
        tier = _tool_impact_tier(tool_name, descriptor)
        if tier == ImpactTier.DESTRUCTIVE:
            return ConsentResult.ask(
                prompt=(
                    f"'{tool_name}' is a high-impact action and cannot be approved by voice. "
                    "Please type 'yes' or 'confirm' to proceed."
                )
            )
        if stt_confidence < _MIN_VOICE_CONFIDENCE:
            return ConsentResult.ask(
                prompt=(
                    "I wasn't confident I heard you correctly. "
                    "Please say 'yes' clearly or type it to confirm."
                )
            )
        return ConsentResult.allow()

    def impact_tier(self, tool_name: str, descriptor=None) -> ImpactTier:
        """Return the ImpactTier for a tool without making an approval decision."""
        return _tool_impact_tier(tool_name, descriptor)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _online_permission_mode(self, descriptor_default: str) -> str:
        if self._config and hasattr(self._config, "get"):
            val = self._config.get("conversation.online_permission_mode", None)
            if val:
                return str(val)
        return descriptor_default or "ask_first"
