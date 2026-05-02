"""ProceduralMemory — capability success rates, bandit-style.

Phase 7: Tracks (capability, context_features) → success% so the routing
layer can prefer capabilities that have historically worked for this user
and context.  Never deleted — rates decay naturally via the bandit update.
"""
from __future__ import annotations

import json
import threading
from typing import Dict, Tuple


class ProceduralMemory:
    """Track capability success rates using a simple Thompson-sampling-inspired model.

    Records are kept in-memory (resetting on restart) backed optionally by
    ContextStore's facts table for persistence across sessions.
    """

    def __init__(self, context_store=None):
        self._store = context_store
        self._lock = threading.Lock()
        # key: (capability_name, context_key) → {"successes": int, "total": int}
        self._rates: Dict[Tuple[str, str], dict] = {}
        self._load_from_store()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record_outcome(self, capability_name: str, context_features: dict | None, success: bool) -> None:
        """Record a success (True) or failure (False) for *capability_name*.

        *context_features* is an arbitrary dict whose sorted repr is used as
        the context key.  Pass None or {} for context-free rates.
        """
        ctx_key = self._ctx_key(context_features)
        key = (capability_name, ctx_key)
        with self._lock:
            if key not in self._rates:
                self._rates[key] = {"successes": 0, "total": 0}
            self._rates[key]["total"] += 1
            if success:
                self._rates[key]["successes"] += 1
        self._persist(capability_name, ctx_key)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def success_rate(self, capability_name: str, context_features: dict | None = None) -> float:
        """Return estimated success probability for *capability_name*.

        Returns 0.5 (uninformative prior) when no observations exist.
        """
        ctx_key = self._ctx_key(context_features)
        with self._lock:
            entry = self._rates.get((capability_name, ctx_key))
            if entry is None:
                # Try without context
                entry = self._rates.get((capability_name, ""))
            if entry is None or entry["total"] == 0:
                return 0.5
            return entry["successes"] / entry["total"]

    def top_capabilities(self, limit: int = 5) -> list[dict]:
        """Return capabilities ranked by success rate (most reliable first)."""
        with self._lock:
            aggregated: Dict[str, dict] = {}
            for (name, _ctx), rates in self._rates.items():
                if name not in aggregated:
                    aggregated[name] = {"successes": 0, "total": 0}
                aggregated[name]["successes"] += rates["successes"]
                aggregated[name]["total"] += rates["total"]
        ranked = [
            {
                "capability": name,
                "success_rate": d["successes"] / d["total"] if d["total"] else 0.5,
                "observations": d["total"],
            }
            for name, d in aggregated.items()
            if d["total"] > 0
        ]
        return sorted(ranked, key=lambda r: r["success_rate"], reverse=True)[:limit]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ctx_key(self, features: dict | None) -> str:
        if not features:
            return ""
        try:
            return json.dumps(features, sort_keys=True, separators=(",", ":"))
        except Exception:
            return ""

    def _persist(self, capability_name: str, ctx_key: str) -> None:
        if self._store is None:
            return
        store_fn = getattr(self._store, "store_fact", None)
        if not callable(store_fn):
            return
        key = (capability_name, ctx_key)
        with self._lock:
            entry = self._rates.get(key, {})
        try:
            store_fn(
                key=f"proc:{capability_name}:{ctx_key[:32]}",
                value=json.dumps(entry),
                session_id=None,
                namespace="procedural",
            )
        except Exception:
            pass

    def _load_from_store(self) -> None:
        if self._store is None:
            return
        load_fn = getattr(self._store, "get_facts_by_namespace", None)
        if not callable(load_fn):
            return
        try:
            facts = load_fn(namespace="procedural") or []
            for fact in facts:
                raw_key = fact.get("key", "")
                if not raw_key.startswith("proc:"):
                    continue
                parts = raw_key[5:].split(":", 1)
                capability_name = parts[0]
                ctx_key = parts[1] if len(parts) > 1 else ""
                try:
                    entry = json.loads(fact.get("value", "{}"))
                    if isinstance(entry, dict):
                        self._rates[(capability_name, ctx_key)] = entry
                except Exception:
                    pass
        except Exception:
            pass
