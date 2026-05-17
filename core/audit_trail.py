"""AuditTrail — structured log of every capability execution.

Mirrors jarvis's `audit_trail` table (src/vault/schema.ts:367-389) and
`src/authority/audit.ts`. Every CapabilityExecutor.execute call writes a row
so you can retrospectively answer "why did FRIDAY do X yesterday".

Usage:
    # Injected at boot by FridayApp
    app.audit_trail.log(tool_name="web_search", ok=True, exec_ms=340, ...)

    # Query
    events = app.audit_trail.query(tool_name="web_search", limit=10)
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from core.logger import logger

if TYPE_CHECKING:
    from core.memory_service import MemoryService


class AuditTrail:
    """Thin facade over MemoryService.log_audit_event for structured event logging."""

    def __init__(self, memory_service: "MemoryService", session_id: str = ""):
        self._memory = memory_service
        self._session_id = session_id

    def log(
        self,
        tool_name: str,
        ok: bool,
        args_summary: str = "",
        output_summary: str = "",
        exec_ms: int = 0,
        agent_id: str = "friday",
        authority_decision: str = "allowed",
        session_id: str = "",
    ) -> None:
        self._memory.log_audit_event(
            tool_name=tool_name,
            ok=ok,
            args_summary=args_summary[:400],
            output_summary=output_summary[:400],
            exec_ms=exec_ms,
            session_id=session_id or self._session_id,
            agent_id=agent_id,
            authority_decision=authority_decision,
        )

    def query(
        self, tool_name: str = "", limit: int = 50, session_id: str = ""
    ) -> list[dict]:
        return self._memory.query_audit_events(
            tool_name=tool_name,
            limit=limit,
            session_id=session_id or self._session_id,
        )

    def timed_execute(self, name: str, fn, args_summary: str = "", session_id: str = ""):
        """Execute fn() and log the result with timing. Returns fn's return value."""
        t0 = time.monotonic()
        ok = True
        result = None
        output_summary = ""
        try:
            result = fn()
            output_summary = str(result)[:400] if result is not None else ""
        except Exception as exc:
            ok = False
            output_summary = str(exc)[:400]
            logger.debug("[audit] %s raised: %s", name, exc)
            raise
        finally:
            exec_ms = int((time.monotonic() - t0) * 1000)
            self.log(
                tool_name=name,
                ok=ok,
                args_summary=args_summary,
                output_summary=output_summary,
                exec_ms=exec_ms,
                session_id=session_id,
            )
        return result
