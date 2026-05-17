"""Windows platform adapter.

Requires: PowerShell (built-in on Windows 10+).
Optional:  pywin32 (pip install pywin32) for richer window info.
"""
from __future__ import annotations

import shutil
import subprocess

from ._interface import PlatformAdapter


def _ps(cmd: str, timeout: int = 5) -> str:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""


class WindowsAdapter(PlatformAdapter):
    def clipboard_read(self) -> str:
        return _ps("Get-Clipboard")

    def clipboard_write(self, text: str) -> None:
        escaped = text.replace("'", "''")
        _ps(f"Set-Clipboard -Value '{escaped}'")

    def get_active_window(self) -> tuple[str, str]:
        script = (
            "Add-Type @'\n"
            "using System; using System.Runtime.InteropServices;\n"
            "public class FW {\n"
            "  [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
            "  [DllImport(\"user32.dll\")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder sb, int l);\n"
            "  [DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);\n"
            "}\n"
            "'@\n"
            "$h = [FW]::GetForegroundWindow()\n"
            "$sb = New-Object System.Text.StringBuilder 256\n"
            "[FW]::GetWindowText($h, $sb, 256) | Out-Null\n"
            "$pid = [uint32]0\n"
            "[FW]::GetWindowThreadProcessId($h, [ref]$pid) | Out-Null\n"
            "$proc = Get-Process -Id $pid -ErrorAction SilentlyContinue\n"
            "\"$($proc.Name)|$($sb.ToString())\""
        )
        out = _ps(script)
        if "|" in out:
            app, title = out.split("|", 1)
            return (app.strip(), title.strip())
        return ("", out)

    def default_shell(self) -> str:
        ps = shutil.which("pwsh") or shutil.which("powershell")
        return ps or "cmd.exe"

    def open_url(self, url: str) -> None:
        import os  # noqa
        os.startfile(url)  # type: ignore[attr-defined]

    def list_running_processes(self) -> list[dict]:
        out = _ps(
            "Get-Process | Select-Object -First 50 | "
            "ForEach-Object { \"$($_.Id),$($_.ProcessName),$($_.CPU),$($_.WorkingSet64)\" }"
        )
        processes = []
        for line in out.splitlines():
            parts = line.split(",", 3)
            if len(parts) == 4:
                try:
                    processes.append({
                        "pid": int(parts[0]),
                        "name": parts[1][:40],
                        "cpu": float(parts[2] or 0),
                        "mem": int(parts[3] or 0) // 1024 // 1024,
                    })
                except (ValueError, IndexError):
                    continue
        return processes
