"""Linux platform adapter.

Install:
  Ubuntu/Debian: sudo apt install xclip xdotool
  Fedora:        sudo dnf install xclip xdotool
  Arch:          sudo pacman -S xclip xdotool
"""
from __future__ import annotations

import os
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


class LinuxAdapter(PlatformAdapter):
    def clipboard_read(self) -> str:
        if shutil.which("xclip"):
            return _run(["xclip", "-selection", "clipboard", "-o"])
        if shutil.which("xsel"):
            return _run(["xsel", "--clipboard", "--output"])
        if shutil.which("wl-paste"):
            return _run(["wl-paste"])
        return ""

    def clipboard_write(self, text: str) -> None:
        if shutil.which("xclip"):
            _run(["xclip", "-selection", "clipboard"], input_text=text)
        elif shutil.which("xsel"):
            _run(["xsel", "--clipboard", "--input"], input_text=text)
        elif shutil.which("wl-copy"):
            _run(["wl-copy"], input_text=text)

    def get_active_window(self) -> tuple[str, str]:
        if shutil.which("xdotool"):
            wid = _run(["xdotool", "getactivewindow"])
            if wid:
                title = _run(["xdotool", "getwindowname", wid])
                pid_str = _run(["xdotool", "getwindowpid", wid])
                app = ""
                if pid_str.isdigit():
                    app = _run(["ps", "-p", pid_str, "-o", "comm="])
                return (app or "unknown", title or "")
        return ("", "")

    def default_shell(self) -> str:
        return os.environ.get("SHELL") or shutil.which("bash") or "/bin/sh"

    def open_url(self, url: str) -> None:
        for cmd in ("xdg-open", "sensible-browser", "firefox", "chromium"):
            if shutil.which(cmd):
                subprocess.Popen(
                    [cmd, url],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

    def list_running_processes(self) -> list[dict]:
        out = _run(["ps", "aux", "--no-headers"])
        processes = []
        for line in out.splitlines():
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
