"""PermissionService — capability tier enforcement.

Tiers (ascending privilege):
  read     — side-effect free; auto-approved.
  write    — mutates local state (file write, volume change, launch app);
             approved once per session on first use.
  critical — destructive or irreversible (shutdown, delete, send email);
             requires explicit per-invocation confirmation.
"""

from __future__ import annotations

import ipaddress
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
    # Network scope / authorized target checks (security tools)
    # ------------------------------------------------------------------

    @staticmethod
    def classify_target_scope(target: str) -> str:
        """Classify a host/IP/CIDR/domain into local|lab|public|unknown.

        - "local": loopback (127.0.0.0/8, ::1, localhost)
        - "lab":   RFC1918 private ranges (10/8, 172.16/12, 192.168/16) or link-local
        - "public": any other routable address / public domain
        - "unknown": domain we cannot resolve here (no DNS lookups at this layer)
        """
        raw = (target or "").strip().strip("[]")
        if not raw:
            return "unknown"
        # Strip CIDR suffix for classification (but classify the network).
        net_part = raw.split("/")[0]
        if net_part.lower() in ("localhost", "::1"):
            return "local"
        try:
            if "/" in raw:
                net = ipaddress.ip_network(raw, strict=False)
                if net.is_loopback:
                    return "local"
                if net.is_private or net.is_link_local:
                    return "lab"
                return "public"
            addr = ipaddress.ip_address(net_part)
            if addr.is_loopback:
                return "local"
            if addr.is_private or addr.is_link_local:
                return "lab"
            return "public"
        except ValueError:
            # Not an IP literal — treat as hostname; do not resolve here.
            return "unknown"

    def check_network_scope(self, target: str, allowed_scope: str) -> tuple[bool, str]:
        """Return (allowed, reason) for whether `target` is within `allowed_scope`.

        allowed_scope is the capability's declared `network_scope`:
          - "local"   -> only loopback targets allowed
          - "lab"     -> loopback or RFC1918 targets allowed
          - "public"  -> any classified target allowed (still blocks "unknown")
          - "unknown" -> nothing allowed (capability must declare scope)
        """
        actual = self.classify_target_scope(target)
        allowed_scope = (allowed_scope or "unknown").lower()
        ladder = {"local": 0, "lab": 1, "public": 2, "unknown": 3}
        if actual == "unknown":
            return False, f"target {target!r} could not be classified; provide an IP/CIDR or pre-authorize the hostname"
        if allowed_scope == "unknown":
            return False, "capability declares unknown network_scope — refuse by default"
        if ladder[actual] > ladder[allowed_scope]:
            return False, f"target scope {actual!r} exceeds capability's allowed scope {allowed_scope!r}"
        return True, "ok"

    def check_authorized_target(self, target: str, authorized_scopes: list[str]) -> tuple[bool, str]:
        """Return (allowed, reason) for whether `target` falls inside any of
        `authorized_scopes` (config.yaml `security.authorized_scopes`).

        Entries can be IP literals, CIDR blocks, or exact hostnames/domains.
        Hostname matching is exact or suffix-based (".lab.local" matches
        "host1.lab.local").
        """
        raw = (target or "").strip()
        if not raw:
            return False, "empty target"
        net_part = raw.split("/")[0]
        try:
            target_ip = ipaddress.ip_address(net_part)
        except ValueError:
            target_ip = None

        for entry in authorized_scopes or []:
            scope = str(entry or "").strip()
            if not scope:
                continue
            if target_ip is not None:
                try:
                    if "/" in scope:
                        if target_ip in ipaddress.ip_network(scope, strict=False):
                            return True, f"matched authorized scope {scope!r}"
                    else:
                        if ipaddress.ip_address(scope) == target_ip:
                            return True, f"matched authorized scope {scope!r}"
                except ValueError:
                    # Scope entry isn't an IP — fall through to hostname compare.
                    pass
            # Hostname / domain match (exact or suffix on dot boundary).
            lower_target = net_part.lower()
            lower_scope = scope.lower().lstrip(".")
            if lower_target == lower_scope or lower_target.endswith("." + lower_scope):
                return True, f"matched authorized scope {scope!r}"
        return False, f"target {target!r} is not within any authorized scope"

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
