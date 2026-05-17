"""PlatformAdapter — abstract interface all OS adapters must implement.

Mirrors jarvis sidecar/types.go + src/actions/app-control/interface.ts.
Each method maps to a cross-platform operation; platform files implement
only their OS-specific variant (linux.py / windows.py / macos.py).
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    """One implementation per supported OS — selected at import time."""

    @abstractmethod
    def clipboard_read(self) -> str:
        """Return current clipboard text (empty string on failure)."""

    @abstractmethod
    def clipboard_write(self, text: str) -> None:
        """Write text to the system clipboard."""

    @abstractmethod
    def get_active_window(self) -> tuple[str, str]:
        """Return (app_name, window_title) for the currently focused window."""

    @abstractmethod
    def default_shell(self) -> str:
        """Return the preferred interactive shell executable path."""

    @abstractmethod
    def open_url(self, url: str) -> None:
        """Open a URL in the default browser."""

    @abstractmethod
    def list_running_processes(self) -> list[dict]:
        """Return a list of running processes: [{pid, name, cpu, mem}]."""
