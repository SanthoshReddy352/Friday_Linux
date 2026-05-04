"""ResultCache — TTL-based capability result cache.

Phase 10: Caches results keyed on (capability_name, args_hash) with TTLs
sourced from CapabilityDescriptor.  Eliminates redundant round-trips for
read-only online capabilities (e.g. weather, news) within their TTL window.

TTL policy:
  - connectivity == "local",  side_effect_level == "read"  → 300 s
  - connectivity == "online", side_effect_level == "read"  → 120 s
  - anything with side_effect_level in {"write", "critical"} → 0 s (no cache)
"""
from __future__ import annotations

import hashlib
import json
import time
from threading import Lock
from typing import Any


_DEFAULT_TTL_LOCAL = 300
_DEFAULT_TTL_ONLINE = 120


class ResultCache:
    """Thread-safe, in-memory TTL cache for capability execution results.

    The cache is keyed by a hash of (capability_name, sorted-args JSON,
    raw_text).  Entries expire silently; get() returns None on miss or expiry.
    """

    def __init__(self):
        self._entries: dict[str, dict] = {}
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, capability_name: str, args: dict, raw_text: str = "") -> Any | None:
        """Return cached result or None on cache miss / expiry."""
        key = _make_key(capability_name, args, raw_text)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry["expires_at"]:
                del self._entries[key]
                return None
            return entry["result"]

    def set(
        self,
        capability_name: str,
        args: dict,
        result: Any,
        *,
        descriptor=None,
        raw_text: str = "",
    ) -> None:
        """Store *result* under the (capability_name, args, raw_text) key.

        TTL is derived from *descriptor* if provided; otherwise from defaults.
        A TTL of 0 means "do not cache".
        """
        ttl = _ttl_for(descriptor)
        if ttl <= 0:
            return
        key = _make_key(capability_name, args, raw_text)
        with self._lock:
            self._entries[key] = {
                "result": result,
                "expires_at": time.monotonic() + ttl,
            }

    def invalidate(self, capability_name: str | None = None) -> int:
        """Invalidate entries for *capability_name*, or all entries if None.

        Returns the number of entries removed.
        """
        with self._lock:
            if capability_name is None:
                count = len(self._entries)
                self._entries.clear()
                return count
            keys_to_remove = [k for k, v in self._entries.items() if v.get("capability") == capability_name]
            for k in keys_to_remove:
                del self._entries[k]
            return len(keys_to_remove)

    def evict_expired(self) -> int:
        """Remove all stale entries. Returns count evicted."""
        now = time.monotonic()
        with self._lock:
            stale = [k for k, v in self._entries.items() if now > v["expires_at"]]
            for k in stale:
                del self._entries[k]
            return len(stale)

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            now = time.monotonic()
            total = len(self._entries)
            live = sum(1 for v in self._entries.values() if now <= v["expires_at"])
        return {"total": total, "live": live, "stale": total - live}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _make_key(capability_name: str, args: dict, raw_text: str) -> str:
    args_str = json.dumps(dict(args or {}), sort_keys=True, separators=(",", ":"))
    content = f"{capability_name}\x00{args_str}\x00{raw_text}"
    return hashlib.sha256(content.encode()).hexdigest()[:24]


def _ttl_for(descriptor) -> int:
    if descriptor is None:
        return _DEFAULT_TTL_LOCAL
    side_effect = getattr(descriptor, "side_effect_level", "read") or "read"
    if side_effect in ("write", "critical"):
        return 0
    connectivity = getattr(descriptor, "connectivity", "local") or "local"
    return _DEFAULT_TTL_ONLINE if connectivity == "online" else _DEFAULT_TTL_LOCAL
