"""Append-only audit log for security tool invocations.

Every Kali wrapper invocation writes one JSON line to this log. The log is
the proof artifact that the LLM never issued a raw shell — every recorded
command was constructed from a fixed wrapper template.

Schema (one JSON object per line):
{
  "ts": "2026-05-17T07:35:12.345Z",
  "trace_id": "...", "turn_id": "...", "source": "voice|telegram|gui",
  "capability": "host_service_scan", "mode": "quick",
  "target": "127.0.0.1", "scope": "local",
  "args": {...}, "command": "nmap -sT --open -oX - ...",
  "status": "success|failure|timeout|refused",
  "exit_ms": 1234, "reason": ""
}
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import threading
from typing import Any

from core.logger import logger


_LOCK = threading.Lock()


class SecurityAuditLog:
    def __init__(self, path: str):
        self.path = path
        # Ensure parent dir exists.
        parent = os.path.dirname(self.path)
        if parent:
            try:
                os.makedirs(parent, exist_ok=True)
            except OSError as exc:
                logger.warning("[security_audit] cannot create %s: %s", parent, exc)

    def write(self, record: dict[str, Any]) -> None:
        record = dict(record or {})
        record.setdefault("ts", _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.") + f"{_dt.datetime.utcnow().microsecond // 1000:03d}Z")
        line = json.dumps(record, ensure_ascii=False, default=str)
        try:
            with _LOCK:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except OSError as exc:
            # Audit failure must never break execution; logger is enough.
            logger.error("[security_audit] write failed: %s", exc)
