"""SecurityToolsPlugin — Kali capability wrappers.

Phase 1 registers two capabilities backed by nmap:
  - host_service_scan: read-only TCP service/version scan on authorized targets
  - ping_sweep: read-only host discovery across an authorized subnet

The LLM only sees compact capability cards (`description`, `aliases`,
`patterns`, `context_terms`). It never sees command strings or flag lists.
All argument validation, scope enforcement, dangerous-flag denial, and
audit logging happen here — not in the model layer.
"""
from __future__ import annotations

import re

from core.logger import logger
from core.plugin_manager import FridayPlugin

try:
    from core.turn_context import current_turn
except Exception:  # pragma: no cover - defensive boundary
    current_turn = None  # type: ignore[assignment]

from .audit import SecurityAuditLog
from .parsers.nmap_parser import parse_nmap_xml
from .wrappers.nmap_wrapper import NmapWrapper


# Compact regex patterns for deterministic routing — the IntentRecognizer /
# RouteScorer can pick this up before the LLM gets involved.
_HOST_SCAN_PATTERNS = [
    r"\b(?:scan|nmap|port[\s-]*scan)\b.+\b(?:host|machine|server|ip|localhost|127\.0\.0\.1)\b",
    r"\b(?:open\s+ports?|services?)\b.+\b(?:on|of|for)\b",
    r"\bservice\s+(?:scan|version|enum(?:eration)?)\b",
]
_PING_SWEEP_PATTERNS = [
    r"\b(?:ping[\s-]*sweep|host\s+discovery|live\s+hosts?)\b",
    r"\b(?:discover|find|list)\s+(?:live\s+|active\s+)?hosts?\b",
]


class SecurityToolsPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "security_tools"
        self.on_load()

    def _get_cfg(self) -> dict:
        cfg = getattr(self.app, "config", None)
        if cfg and hasattr(cfg, "get"):
            return cfg.get("security") or {}
        return {}

    def on_load(self) -> None:
        cfg = self._get_cfg()
        if not cfg.get("lab_mode", False):
            logger.info(
                "[security_tools] Plugin idle — set security.lab_mode: true and "
                "populate security.authorized_scopes in config.yaml to enable."
            )
            return

        self._authorized_scopes = list(cfg.get("authorized_scopes") or [])
        self._audit = SecurityAuditLog(cfg.get("audit_log_path") or "logs/security_audit.log")
        self._nmap = NmapWrapper(
            nmap_binary=cfg.get("nmap_binary") or "nmap",
            default_timeout_sec=int(cfg.get("default_timeout_sec") or 120),
            authorized_scopes=self._authorized_scopes,
        )

        self._register_host_service_scan()
        self._register_ping_sweep()
        logger.info(
            "[security_tools] Loaded — host_service_scan + ping_sweep registered "
            "(authorized_scopes=%d)", len(self._authorized_scopes),
        )

    # ------------------------------------------------------------------
    # Capability registration
    # ------------------------------------------------------------------

    def _register_host_service_scan(self) -> None:
        self.app.router.register_tool(
            {
                "name": "host_service_scan",
                "description": (
                    "Read-only TCP service/version scan of an authorized lab or "
                    "loopback host using nmap. Returns open ports and detected "
                    "service versions. Refuses any target outside the configured "
                    "authorized_scopes."
                ),
                "parameters": {
                    "target": "string — IPv4/IPv6/hostname of the authorized host to scan",
                    "profile": "string — 'quick' (default), 'standard', or 'safe_deep'",
                    "ports": "string — optional port spec like '22,80,443' or '1-1024'",
                },
                "aliases": [
                    "port scan", "service scan", "scan host", "nmap host",
                    "open ports", "what services are running",
                    "service enumeration", "version scan",
                ],
                "patterns": _HOST_SCAN_PATTERNS,
                "context_terms": [
                    "nmap", "port", "scan", "service", "ssh", "http",
                    "open", "tcp", "version", "enumerate",
                ],
            },
            self.handle_host_service_scan,
            capability_meta={
                "connectivity": "local",
                "latency_class": "slow",
                "permission_mode": "always_ok",  # scope check is the real gate
                "side_effect_level": "read",
                "network_scope": "lab",
                "requires_authorization": True,
                "allowed_use_cases": [
                    "scan my own machine",
                    "scan an authorized lab host",
                    "service inventory in my lab subnet",
                ],
                "forbidden_use_cases": [
                    "unauthorized scanning of public targets",
                    "stealth/evasion scanning",
                    "exploit delivery",
                ],
                "command_templates": {
                    "quick": "nmap -sT --open -oX - -T4 --top-ports 100 <target>",
                    "standard": "nmap -sT --open -oX - -T3 --top-ports 1000 -sV <target>",
                    "safe_deep": "nmap -sT --open -oX - -T2 -p- -sV <target>",
                },
                "argument_constraints": {
                    "target": "IPv4|IPv6|hostname; must match an authorized_scope",
                    "profile": "enum: quick | standard | safe_deep",
                    "ports": "optional; '80,443' or '1-1024' format",
                    "deny_flags": [
                        "--script", "-O", "-f", "--mtu", "-D", "-S",
                    ],
                },
                "parser": "nmap_xml_v1",
                "success_conditions": [
                    "structured host list emitted",
                    "process exit code 0",
                ],
                "failure_conditions": [
                    "target outside authorized_scopes",
                    "process timeout",
                    "process exit code != 0",
                ],
                "next_step_hints": [
                    "if http service found, suggest web_app_recon",
                    "if dns service found, suggest dns_enum_owned_domain",
                ],
                "rollback_or_cleanup": [],
                "logging_requirements": [
                    "trace_id", "turn_id", "source", "target",
                    "command", "status", "exit_ms",
                ],
            },
        )

    def _register_ping_sweep(self) -> None:
        self.app.router.register_tool(
            {
                "name": "ping_sweep",
                "description": (
                    "Read-only host discovery (-sn) across an authorized subnet. "
                    "Returns the list of live hosts. Refuses any subnet outside "
                    "the configured authorized_scopes."
                ),
                "parameters": {
                    "subnet": "string — IPv4 CIDR (e.g. 192.168.56.0/24) or single host",
                },
                "aliases": [
                    "ping sweep", "host discovery", "find live hosts",
                    "list live hosts", "who's up", "discover hosts",
                ],
                "patterns": _PING_SWEEP_PATTERNS,
                "context_terms": [
                    "ping", "sweep", "live", "hosts", "subnet", "discover",
                ],
            },
            self.handle_ping_sweep,
            capability_meta={
                "connectivity": "local",
                "latency_class": "slow",
                "permission_mode": "always_ok",
                "side_effect_level": "read",
                "network_scope": "lab",
                "requires_authorization": True,
                "allowed_use_cases": [
                    "discover live hosts in my lab subnet",
                ],
                "forbidden_use_cases": [
                    "internet-wide host discovery",
                    "unauthorized subnet scanning",
                ],
                "command_templates": {
                    "default": "nmap -sn -oX - <subnet>",
                },
                "argument_constraints": {
                    "subnet": "IPv4/IPv6 CIDR or single host; must match authorized_scope",
                },
                "parser": "nmap_xml_v1",
                "success_conditions": ["host list emitted (may be empty)"],
                "failure_conditions": ["subnet outside authorized_scopes", "process timeout"],
                "next_step_hints": ["for each live host, suggest host_service_scan"],
                "logging_requirements": [
                    "trace_id", "turn_id", "source", "subnet",
                    "command", "status", "exit_ms",
                ],
            },
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def handle_host_service_scan(self, text: str, args: dict) -> str:
        args = dict(args or {})
        target = (args.get("target") or "").strip() or self._extract_target(text or "")
        if not target:
            return "Which host should I scan? Give me an IP or hostname inside your authorized scopes."

        profile = (args.get("profile") or "quick").strip().lower()
        ports = (args.get("ports") or None)
        if ports is not None:
            ports = str(ports).strip() or None

        result = self._nmap.host_service_scan(
            target=target,
            profile=profile,
            ports=ports,
            allowed_scope="lab",
        )

        self._audit_call(
            capability="host_service_scan",
            mode=profile,
            target=target,
            args={"profile": profile, "ports": ports},
            result=result,
        )

        if result.status == "refused":
            return f"I can't scan {target}: {result.reason}."
        if result.status == "timeout":
            return f"The scan of {target} timed out after {self._nmap.default_timeout}s."
        if result.status != "success":
            return f"Scan failed: {result.reason or 'unknown error'}"

        observation = parse_nmap_xml(result.raw_stdout)
        return self._format_host_scan_response(target, observation)

    def handle_ping_sweep(self, text: str, args: dict) -> str:
        args = dict(args or {})
        subnet = (args.get("subnet") or "").strip() or self._extract_target(text or "")
        if not subnet:
            return "Which subnet should I sweep? Provide a CIDR like 192.168.56.0/24."

        result = self._nmap.ping_sweep(subnet=subnet, allowed_scope="lab")
        self._audit_call(
            capability="ping_sweep",
            mode="default",
            target=subnet,
            args={"subnet": subnet},
            result=result,
        )

        if result.status == "refused":
            return f"I can't sweep {subnet}: {result.reason}."
        if result.status == "timeout":
            return f"Ping sweep of {subnet} timed out."
        if result.status != "success":
            return f"Ping sweep failed: {result.reason or 'unknown error'}"

        observation = parse_nmap_xml(result.raw_stdout)
        live = [h for h in observation["structured_data"]["hosts"] if h["state"] == "up"]
        if not live:
            return f"No live hosts found in {subnet}."
        addrs = ", ".join(h["address"] for h in live[:20])
        more = "" if len(live) <= 20 else f" (+{len(live) - 20} more)"
        return f"{len(live)} live host(s) in {subnet}: {addrs}{more}."

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    _TARGET_TOKEN_RE = re.compile(
        r"\b("
        r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?:/[0-9]{1,2})?"
        r"|localhost"
        r")\b"
    )

    def _extract_target(self, text: str) -> str:
        m = self._TARGET_TOKEN_RE.search(text or "")
        return m.group(1) if m else ""

    def _format_host_scan_response(self, target: str, obs: dict) -> str:
        hosts = obs.get("structured_data", {}).get("hosts", [])
        if not hosts:
            return f"No host data returned for {target}."
        host = hosts[0]
        if host["state"] != "up":
            return f"{target} appears down or filtered."
        services = host.get("services") or []
        if not services:
            return f"{target} is up but no open TCP ports were found."
        lines = [f"{target} is up. Open services:"]
        for svc in services[:15]:
            ver = f" ({svc['version_hint']})" if svc.get("version_hint") else ""
            lines.append(f"  - {svc['port']}/{svc['protocol']} {svc['service_name'] or '?'}{ver}")
        if len(services) > 15:
            lines.append(f"  ...and {len(services) - 15} more.")
        return "\n".join(lines)

    def _audit_call(self, *, capability: str, mode: str, target: str, args: dict, result) -> None:
        ctx = current_turn() if current_turn else None
        trace_id = getattr(ctx, "trace_id", "") if ctx else ""
        turn_id = getattr(ctx, "turn_id", "") if ctx else ""
        source = getattr(ctx, "source", "") if ctx else ""
        self._audit.write({
            "trace_id": trace_id,
            "turn_id": turn_id,
            "source": source,
            "capability": capability,
            "mode": mode,
            "target": target,
            "args": args,
            "command": result.command,
            "status": result.status,
            "exit_ms": result.exec_ms,
            "reason": result.reason,
        })
