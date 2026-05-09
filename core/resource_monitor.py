"""ResourceMonitor — lightweight hardware snapshot for adaptive policy decisions.

Snapshot is taken at most once per CACHE_TTL_S seconds (default 5 s).
Non-blocking: reads kernel counters only, no I/O.
Per-turn overhead: ~1 ms (cache hit) or ~3 ms (psutil read).

Usage:
    from core.resource_monitor import get_snapshot
    snap = get_snapshot()
    if snap.ram_available_mb < ResourceMonitor.VLM_MIN_RAM_MB:
        ...
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


@dataclass
class ResourceSnapshot:
    ram_total_mb: int = 0
    ram_used_mb: int = 0
    ram_available_mb: int = 0
    cpu_percent: float = 0.0
    timestamp: float = 0.0

    @property
    def ram_free_percent(self) -> float:
        if self.ram_total_mb == 0:
            return 100.0
        return round(self.ram_available_mb / self.ram_total_mb * 100, 1)


class ResourceMonitor:
    CACHE_TTL_S: float = 5.0

    # Policy thresholds — used by VisionService and Mem0 server startup
    VLM_MIN_RAM_MB: int = 3000    # refuse to load VLM if less than this free
    CHAT_ONLY_RAM_MB: int = 2000  # skip tool model if dangerously low

    def __init__(self):
        self._lock = threading.Lock()
        self._cached: ResourceSnapshot | None = None

    def snapshot(self) -> ResourceSnapshot:
        """Return a cached snapshot; refresh at most every CACHE_TTL_S seconds."""
        with self._lock:
            now = time.monotonic()
            if self._cached and (now - self._cached.timestamp) < self.CACHE_TTL_S:
                return self._cached
            snap = self._read()
            snap.timestamp = now
            self._cached = snap
            return snap

    def _read(self) -> ResourceSnapshot:
        if not _PSUTIL_AVAILABLE:
            # Fallback: assume a healthy 16 GB machine with 8 GB free
            return ResourceSnapshot(
                ram_total_mb=16000,
                ram_used_mb=8000,
                ram_available_mb=8000,
            )
        mem = psutil.virtual_memory()
        return ResourceSnapshot(
            ram_total_mb=mem.total // (1024 * 1024),
            ram_used_mb=mem.used // (1024 * 1024),
            ram_available_mb=mem.available // (1024 * 1024),
            cpu_percent=psutil.cpu_percent(interval=None),
        )


# Module-level singleton — one monitor shared across all callers.
_monitor = ResourceMonitor()


def get_snapshot() -> ResourceSnapshot:
    """Return the current cached resource snapshot."""
    return _monitor.snapshot()
