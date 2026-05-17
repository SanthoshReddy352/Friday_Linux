"""nmap capability wrapper.

The LLM never sees these command strings. It selects a `mode` and provides
validated JSON args; the wrapper composes the actual argv from a fixed
template and refuses if any safety check fails. argv is passed to
subprocess.run() directly (shell=False), so there is no shell-injection
surface — the audit log records `shlex.join(argv)` for traceability only.

Modes:
- host_service_scan: TCP connect scan + service/version detection on
  authorized lab/local targets. Read-only.
- ping_sweep: host discovery (-sn) across a subnet. Read-only.

Output is captured as nmap XML (-oX -) and returned as bytes for the
parser to convert into a structured Observation.
"""
from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass

from core.logger import logger

from ..safety import (
    block_dangerous_flags,
    validate_ports,
    validate_target,
)


# Per-profile flag set. Each entry is a list of literal argv tokens; the LLM
# never picks individual flags — it picks the profile name.
_PROFILE_FLAGS: dict[str, list[str]] = {
    "quick": ["-T4", "--top-ports", "100"],
    "standard": ["-T3", "--top-ports", "1000", "-sV", "--version-intensity", "2"],
    "safe_deep": ["-T2", "-p-", "-sV", "--version-intensity", "3"],
}


@dataclass
class WrapperResult:
    ok: bool
    status: str           # success | failure | timeout | refused
    raw_stdout: bytes = b""
    raw_stderr: str = ""
    command: str = ""     # shlex.join(argv) of the executed command (audit only)
    exec_ms: int = 0
    reason: str = ""      # populated on failure/refused


class NmapWrapper:
    """Safe subprocess wrapper around the nmap binary."""

    def __init__(
        self,
        *,
        nmap_binary: str = "nmap",
        default_timeout_sec: int = 120,
        authorized_scopes: list[str] | None = None,
    ):
        self.binary = nmap_binary
        self.default_timeout = int(default_timeout_sec)
        self.authorized_scopes = list(authorized_scopes or [])

    # -- public modes -----------------------------------------------------

    def host_service_scan(
        self,
        target: str,
        *,
        profile: str = "quick",
        ports: str | None = None,
        allowed_scope: str = "lab",
        timeout_sec: int | None = None,
    ) -> WrapperResult:
        """Service/version scan against a single authorized host."""
        check = validate_target(
            target,
            allowed_scope=allowed_scope,
            authorized_scopes=self.authorized_scopes,
        )
        if not check.allowed:
            return WrapperResult(ok=False, status="refused", reason=check.reason)

        if ports is not None and ports != "":
            ok_ports, port_reason = validate_ports(ports)
            if not ok_ports:
                return WrapperResult(ok=False, status="refused", reason=port_reason)

        profile_key = profile if profile in _PROFILE_FLAGS else "quick"
        profile_flags = list(_PROFILE_FLAGS[profile_key])

        # If the caller specified explicit ports, drop any --top-ports/-p- from
        # the profile and use -p <spec> instead.
        if ports:
            drop_keys = {"--top-ports", "-p-"}
            cleaned: list[str] = []
            skip_next = False
            for token in profile_flags:
                if skip_next:
                    skip_next = False
                    continue
                if token in drop_keys:
                    skip_next = token == "--top-ports"
                    continue
                cleaned.append(token)
            profile_flags = cleaned + ["-p", ports]

        argv = [self.binary, "-sT", "--open", "-oX", "-", *profile_flags, target]

        dangerous = block_dangerous_flags(" ".join(argv))
        if dangerous:
            return WrapperResult(ok=False, status="refused", reason=f"dangerous flag detected: {dangerous}")

        return self._run(argv, timeout_sec or self.default_timeout)

    def ping_sweep(
        self,
        subnet: str,
        *,
        allowed_scope: str = "lab",
        timeout_sec: int | None = None,
    ) -> WrapperResult:
        check = validate_target(
            subnet,
            allowed_scope=allowed_scope,
            authorized_scopes=self.authorized_scopes,
        )
        if not check.allowed:
            return WrapperResult(ok=False, status="refused", reason=check.reason)

        argv = [self.binary, "-sn", "-oX", "-", subnet]
        dangerous = block_dangerous_flags(" ".join(argv))
        if dangerous:
            return WrapperResult(ok=False, status="refused", reason=f"dangerous flag detected: {dangerous}")

        return self._run(argv, timeout_sec or self.default_timeout)

    # -- internal ---------------------------------------------------------

    def _run(self, argv: list[str], timeout_sec: int) -> WrapperResult:
        audit_command = shlex.join(argv)
        logger.info("[security_tools.nmap] exec: %s", audit_command)
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            return WrapperResult(
                ok=False,
                status="timeout",
                raw_stdout=exc.stdout or b"",
                raw_stderr=(exc.stderr or b"").decode("utf-8", errors="replace") if exc.stderr else "",
                command=audit_command,
                exec_ms=elapsed,
                reason=f"nmap exceeded {timeout_sec}s timeout",
            )
        except FileNotFoundError:
            elapsed = int((time.monotonic() - t0) * 1000)
            return WrapperResult(
                ok=False,
                status="failure",
                command=audit_command,
                exec_ms=elapsed,
                reason=f"nmap binary not found at {self.binary!r}",
            )
        elapsed = int((time.monotonic() - t0) * 1000)
        return WrapperResult(
            ok=(proc.returncode == 0),
            status="success" if proc.returncode == 0 else "failure",
            raw_stdout=proc.stdout or b"",
            raw_stderr=(proc.stderr or b"").decode("utf-8", errors="replace"),
            command=audit_command,
            exec_ms=elapsed,
            reason="" if proc.returncode == 0 else f"nmap exit code {proc.returncode}",
        )
