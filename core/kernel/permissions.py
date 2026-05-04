"""PermissionService — capability tier enforcement.

Tiers (ascending privilege):
  read     — side-effect free; auto-approved.
  write    — mutates local state (file write, volume change, launch app);
             approved once per session on first use.
  critical — destructive or irreversible (shutdown, delete, send email);
             requires explicit per-invocation confirmation.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.capability_registry import CapabilityDescriptor


class PermissionTier(Enum):
    READ = "read"
    WRITE = "write"
    CRITICAL = "critical"

    @classmethod
    def from_str(cls, value: str) -> "PermissionTier":
        mapping = {
            "read": cls.READ,
            "write": cls.WRITE,
            "critical": cls.CRITICAL,
        }
        return mapping.get((value or "").lower().strip(), cls.READ)

    def __ge__(self, other: "PermissionTier") -> bool:
        order = [PermissionTier.READ, PermissionTier.WRITE, PermissionTier.CRITICAL]
        return order.index(self) >= order.index(other)

    def __gt__(self, other: "PermissionTier") -> bool:
        order = [PermissionTier.READ, PermissionTier.WRITE, PermissionTier.CRITICAL]
        return order.index(self) > order.index(other)


# Tools that are unconditionally critical regardless of descriptor annotation.
_ALWAYS_CRITICAL: frozenset[str] = frozenset({
    "shutdown_assistant",
    "reboot_system",
    "factory_reset",
})

# Keyword fragments that bump a tool to "critical" during inference.
_CRITICAL_KEYWORDS: tuple[str, ...] = (
    "delete",
    "remove",
    "destroy",
    "format",
    "shutdown",
    "reboot",
    "reset",
    "send",       # send email / send message
    "factory",
)


class PermissionService:
    """Evaluate and enforce permission tiers for capability execution.

    Stateless — callers own the session consent store.
    """

    # ------------------------------------------------------------------
    # Tier resolution
    # ------------------------------------------------------------------

    def resolve_tier(self, tool_name: str, descriptor: "CapabilityDescriptor | None") -> PermissionTier:
        """Return the effective PermissionTier for a capability."""
        if tool_name in _ALWAYS_CRITICAL:
            return PermissionTier.CRITICAL

        if descriptor is not None:
            level = (descriptor.side_effect_level or "read").lower()
            if level == "critical":
                return PermissionTier.CRITICAL
            if level == "write":
                return PermissionTier.WRITE
            return PermissionTier.READ

        # Fallback: infer from the tool name alone.
        return self._infer_tier_from_name(tool_name)

    def _infer_tier_from_name(self, tool_name: str) -> PermissionTier:
        lower = tool_name.lower()
        if any(kw in lower for kw in _CRITICAL_KEYWORDS):
            return PermissionTier.CRITICAL
        write_tokens = ("open", "launch", "play", "set_", "write", "create", "manage", "enable", "disable")
        if any(t in lower for t in write_tokens):
            return PermissionTier.WRITE
        return PermissionTier.READ

    # ------------------------------------------------------------------
    # Enforcement queries (callers decide how to present UI)
    # ------------------------------------------------------------------

    def requires_session_consent(self, tier: PermissionTier) -> bool:
        """Write-tier tools need one-time session consent before first use."""
        return tier >= PermissionTier.WRITE

    def requires_per_invocation_confirmation(self, tier: PermissionTier) -> bool:
        """Critical-tier tools must be confirmed on every invocation."""
        return tier == PermissionTier.CRITICAL

    def confirmation_prompt(self, tool_name: str, descriptor: "CapabilityDescriptor | None") -> str:
        noun = (getattr(descriptor, "description", None) or tool_name.replace("_", " ")).lower()
        tier = self.resolve_tier(tool_name, descriptor)
        if tier == PermissionTier.CRITICAL:
            return f"This will {noun}. Are you sure you want to proceed? Say yes to confirm."
        return f"I'll need permission to {noun}. Say yes to allow this action."

    # ------------------------------------------------------------------
    # Inference helper (used by CapabilityRegistry)
    # ------------------------------------------------------------------

    @staticmethod
    def infer_side_effect_level(tool_name: str) -> str:
        """Return a side_effect_level string from a tool name alone.

        Used by CapabilityRegistry._infer_side_effect_level() as a
        single source of truth rather than duplicating the keyword list.
        """
        lower = (tool_name or "").lower()
        if any(kw in lower for kw in _CRITICAL_KEYWORDS):
            return "critical"
        write_tokens = ("open", "launch", "play", "set_", "manage", "write", "create")
        if any(t in lower for t in write_tokens):
            return "write"
        return "read"
