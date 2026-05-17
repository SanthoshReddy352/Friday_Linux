"""Safety helpers for Kali capability wrappers.

The LLM is never allowed to construct shell commands directly. Wrappers
own a small set of command_templates and feed validated, shlex-quoted
arguments into them. This module centralizes the validation that every
wrapper applies before subprocess.run():

- target scope check (loopback / RFC1918 / authorized list)
- dangerous flag deny-list
- argument shape constraints (length, allowed chars)

`validate_target` returns (allowed, classified_scope, reason). A wrapper
should refuse execution unless allowed=True.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.kernel.permissions import PermissionService


# Flags that must never appear in any argument string passed to a Kali tool.
# These cover NSE script execution, OS fingerprinting that touches the kernel,
# packet fragmentation evasion, source spoofing, and arbitrary script paths.
DANGEROUS_FLAG_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?:^|\s)--script(?:=|\s|$)", re.IGNORECASE),
    re.compile(r"(?:^|\s)--script-args(?:=|\s|$)", re.IGNORECASE),
    re.compile(r"(?:^|\s)-O\b", re.IGNORECASE),               # OS detection
    re.compile(r"(?:^|\s)-sS\s.*--privileged", re.IGNORECASE),
    re.compile(r"(?:^|\s)-f\b", re.IGNORECASE),               # fragmentation
    re.compile(r"(?:^|\s)--mtu(?:=|\s)", re.IGNORECASE),
    re.compile(r"(?:^|\s)-D\s", re.IGNORECASE),               # decoy
    re.compile(r"(?:^|\s)-S\s", re.IGNORECASE),               # source IP spoof
    re.compile(r"(?:^|\s)--source-port(?:=|\s)", re.IGNORECASE),
    re.compile(r"(?:^|\s)--data-string(?:=|\s)", re.IGNORECASE),
    re.compile(r"[;&|`$()<>]"),                                # shell metachars
)

# Conservative port-list grammar: 80, 80,443, 1-1024, 80,443,8000-8100
PORTS_RE = re.compile(r"^[0-9]{1,5}(?:[-,][0-9]{1,5})*$")

# Target literal: IPv4, IPv4-CIDR, IPv6, IPv6-CIDR, or DNS label-style hostname.
TARGET_RE = re.compile(
    r"^(?:"
    r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}(?:/[0-9]{1,2})?"           # IPv4 / CIDR
    r"|[A-Fa-f0-9:]+(?:/[0-9]{1,3})?"                          # IPv6 / CIDR
    r"|[A-Za-z0-9][A-Za-z0-9\-\.]{0,253}"                      # hostname
    r")$"
)


@dataclass
class TargetCheck:
    allowed: bool
    scope: str          # local|lab|public|unknown
    reason: str         # human-readable; logged on refusal


def validate_target(
    target: str,
    *,
    allowed_scope: str,
    authorized_scopes: list[str] | None = None,
) -> TargetCheck:
    """Validate a target string against capability scope + config allowlist."""
    raw = (target or "").strip()
    if not raw or not TARGET_RE.match(raw):
        return TargetCheck(False, "unknown", f"target {target!r} is not a valid IP/CIDR/hostname")

    perms = PermissionService()
    scope_ok, scope_reason = perms.check_network_scope(raw, allowed_scope)
    classified = perms.classify_target_scope(raw)
    if not scope_ok:
        return TargetCheck(False, classified, scope_reason)

    # For "lab" / "public" capabilities, also require an explicit authorized
    # scope match from config (defense in depth — RFC1918 alone isn't
    # sufficient if the user hasn't said this is their lab).
    if allowed_scope in ("lab", "public") and authorized_scopes:
        auth_ok, auth_reason = perms.check_authorized_target(raw, authorized_scopes)
        if not auth_ok:
            return TargetCheck(False, classified, auth_reason)

    return TargetCheck(True, classified, "ok")


def block_dangerous_flags(value: str) -> str | None:
    """Return the matched dangerous flag if `value` contains one, else None."""
    if not value:
        return None
    for pat in DANGEROUS_FLAG_PATTERNS:
        m = pat.search(value)
        if m:
            return m.group(0).strip()
    return None


def validate_ports(spec: str) -> tuple[bool, str]:
    """Validate a port spec string like '22,80,443' or '1-1024'."""
    if spec is None or spec == "":
        return True, "ok"
    if not PORTS_RE.match(spec):
        return False, f"port spec {spec!r} is not a valid number/range list"
    # Numeric range sanity
    for part in spec.split(","):
        for end in part.split("-"):
            try:
                n = int(end)
            except ValueError:
                return False, f"non-numeric port in {spec!r}"
            if not (1 <= n <= 65535):
                return False, f"port {n} out of range 1..65535"
    return True, "ok"
