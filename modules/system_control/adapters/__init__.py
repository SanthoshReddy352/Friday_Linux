"""Platform adapter factory — returns the right adapter for the current OS."""
from __future__ import annotations

import platform

from ._interface import PlatformAdapter

_adapter: PlatformAdapter | None = None


def get_adapter() -> PlatformAdapter:
    global _adapter
    if _adapter is not None:
        return _adapter
    system = platform.system()
    if system == "Linux":
        from .linux import LinuxAdapter
        _adapter = LinuxAdapter()
    elif system == "Windows":
        from .windows import WindowsAdapter
        _adapter = WindowsAdapter()
    elif system == "Darwin":
        from .macos import MacOSAdapter
        _adapter = MacOSAdapter()
    else:
        from .linux import LinuxAdapter
        _adapter = LinuxAdapter()
    return _adapter
