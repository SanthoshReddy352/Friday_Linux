"""macOS platform adapter.

Uses pbpaste/pbcopy for clipboard, osascript for window info.
All binaries are built into macOS — no install required.
"""
from __future__ import annotations

import shutil
import subprocess

from ._interface import PlatformAdapter


def _run(cmd: list[str], input_text: str | None = None, timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            input=input_text,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _osa(script: str) -> str:
    return _run(["osascript", "-e", script])


class MacOSAdapter(PlatformAdapter):
    def clipboard_read(self) -> str:
        return _run(["pbpaste"])

    def clipboard_write(self, text: str) -> None:
        _run(["pbcopy"], input_text=text)

    def get_active_window(self) -> tuple[str, str]:
        app = _osa(
            'tell application "System Events" to '
            'get name of first process whose frontmost is true'
        )
        title = _osa(
            'tell application "System Events" to '
            'get title of front window of (first process whose frontmost is true)'
        )
        return (app or "", title or "")

    def default_shell(self) -> str:
        import os
        return os.environ.get("SHELL") or shutil.which("zsh") or "/bin/zsh"

    def open_url(self, url: str) -> None:
        _run(["open", url])

    def list_running_processes(self) -> list[dict]:
        out = _run(["ps", "aux"])
        processes = []
        for line in out.splitlines()[1:]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                try:
                    processes.append({
                        "pid": int(parts[1]),
                        "name": parts[10].split("/")[-1][:40],
                        "cpu": float(parts[2]),
                        "mem": float(parts[3]),
                    })
                except (ValueError, IndexError):
                    continue
        return processes[:50]
