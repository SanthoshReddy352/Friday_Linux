"""Preflight checks — detect available capabilities before registering them.

Mirrors jarvis sidecar/preflight.go and sidecar/preflight_linux.go.
The plugin's on_load runs these checks and skips registering any capability
whose binary/API is unavailable, so the LLM tool selector never picks a
tool that will fail on this host.
"""
from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass


@dataclass
class CapabilityAvailability:
    name: str
    available: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.available


def check_clipboard() -> CapabilityAvailability:
    system = platform.system()
    if system == "Linux":
        for tool in ("xclip", "xsel", "wl-paste"):
            if shutil.which(tool):
                return CapabilityAvailability("clipboard", True)
        return CapabilityAvailability(
            "clipboard", False,
            "xclip, xsel, or wl-paste not found — "
            "install xclip: sudo apt install xclip",
        )
    if system == "Windows":
        if shutil.which("powershell") or shutil.which("pwsh"):
            return CapabilityAvailability("clipboard", True)
        return CapabilityAvailability("clipboard", False, "PowerShell not found")
    if system == "Darwin":
        if shutil.which("pbpaste"):
            return CapabilityAvailability("clipboard", True)
        return CapabilityAvailability("clipboard", False, "pbpaste not found")
    return CapabilityAvailability("clipboard", False, f"unsupported OS: {system}")


def check_active_window() -> CapabilityAvailability:
    system = platform.system()
    if system == "Linux":
        if shutil.which("xdotool"):
            return CapabilityAvailability("active_window", True)
        return CapabilityAvailability(
            "active_window", False,
            "xdotool not found — install: sudo apt install xdotool",
        )
    if system == "Windows":
        return CapabilityAvailability("active_window", True)  # powershell Add-Type
    if system == "Darwin":
        if shutil.which("osascript"):
            return CapabilityAvailability("active_window", True)
        return CapabilityAvailability("active_window", False, "osascript not found")
    return CapabilityAvailability("active_window", False, f"unsupported OS: {system}")


def check_open_url() -> CapabilityAvailability:
    system = platform.system()
    if system == "Linux":
        for tool in ("xdg-open", "sensible-browser", "firefox", "chromium"):
            if shutil.which(tool):
                return CapabilityAvailability("open_url", True)
        return CapabilityAvailability("open_url", False, "no browser launcher found")
    if system in ("Windows", "Darwin"):
        return CapabilityAvailability("open_url", True)
    return CapabilityAvailability("open_url", False, f"unsupported OS: {system}")


def run_all() -> dict[str, CapabilityAvailability]:
    return {
        "clipboard": check_clipboard(),
        "active_window": check_active_window(),
        "open_url": check_open_url(),
    }
