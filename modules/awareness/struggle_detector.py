"""StruggleDetector — detects when the user is stuck.

Mirrors jarvis src/awareness/struggle-detector.ts (342 lines).
Maintains a rolling window of screen snapshots and computes 4 weighted signals:
  - trial_and_error (0.30) — content changes but no apparent progress
  - undo_revert     (0.25) — content oscillates back to a previous state
  - repeated_output (0.25) — OCR output is nearly identical across snapshots
  - low_progress    (0.20) — content barely changes at all

Composite score ≥ STRUGGLE_THRESHOLD with GRACE_S elapsed and COOLDOWN_S since
last suggestion fires a "struggle_detected" EventBus event.
"""
from __future__ import annotations

import hashlib
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque


WINDOW_S = 3.5 * 60          # 3.5-minute rolling window
MAX_SNAPSHOTS = 30
STRUGGLE_THRESHOLD = 0.5     # composite score above this is a struggle
GRACE_S = 2 * 60             # don't fire within first 2 minutes
COOLDOWN_S = 3 * 60          # min gap between struggle events
_SIMILARITY_THRESHOLD = 0.85  # text diff ratio to count as "same"


@dataclass
class Snapshot:
    ts: float
    ocr_text: str
    ocr_hash: str
    window_title: str


def _text_hash(text: str) -> str:
    return hashlib.md5((text or "").encode(), usedforsecurity=False).hexdigest()


def _similarity(a: str, b: str) -> float:
    """Rough similarity ratio — Jaccard on words."""
    if not a and not b:
        return 1.0
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa and not wb:
        return 1.0
    return len(wa & wb) / len(wa | wb)


class StruggleDetector:
    def __init__(self, event_bus):
        self._bus = event_bus
        self._snapshots: Deque[Snapshot] = deque(maxlen=MAX_SNAPSHOTS)
        self._session_start = time.monotonic()
        self._last_struggle_ts: float = 0.0

    def push(self, ocr_text: str, window_title: str = "") -> dict | None:
        """Add a new snapshot. Returns a struggle dict if detected, else None."""
        ts = time.monotonic()
        snap = Snapshot(
            ts=ts,
            ocr_text=(ocr_text or "").strip(),
            ocr_hash=_text_hash(ocr_text),
            window_title=window_title,
        )
        self._snapshots.append(snap)
        return self._evaluate(ts)

    def _evaluate(self, now: float) -> dict | None:
        snaps = list(self._snapshots)
        if len(snaps) < 3:
            return None

        elapsed = now - self._session_start
        if elapsed < GRACE_S:
            return None

        since_last = now - self._last_struggle_ts
        if self._last_struggle_ts > 0 and since_last < COOLDOWN_S:
            return None

        # Prune snapshots outside the rolling window
        cutoff = now - WINDOW_S
        recent = [s for s in snaps if s.ts >= cutoff]
        if len(recent) < 3:
            return None

        # Signal 1: trial_and_error — content changes but no net progress
        #   proxy: high pairwise diff variance (changes a lot but comes back)
        texts = [s.ocr_text for s in recent]
        hashes = [s.ocr_hash for s in recent]
        unique = len(set(hashes))
        change_rate = unique / len(hashes)
        # Changes a lot but oscillates → trial and error
        oscillation = change_rate > 0.4 and _similarity(texts[0], texts[-1]) > _SIMILARITY_THRESHOLD
        trial_and_error = 0.6 if oscillation else (0.3 if change_rate > 0.5 else 0.0)

        # Signal 2: undo_revert — text comes back to an earlier state
        undo_revert = 0.0
        for i in range(1, len(recent)):
            if recent[i].ocr_hash in [s.ocr_hash for s in recent[:i]]:
                undo_revert += 1
        undo_revert = min(undo_revert / max(len(recent) - 1, 1), 1.0)

        # Signal 3: repeated_output — last N snapshots nearly identical
        last_n = recent[-5:]
        if len(last_n) >= 2:
            pairs = [
                _similarity(last_n[i].ocr_text, last_n[i+1].ocr_text)
                for i in range(len(last_n) - 1)
            ]
            avg_sim = sum(pairs) / len(pairs)
            repeated_output = avg_sim if avg_sim > _SIMILARITY_THRESHOLD else 0.0
        else:
            repeated_output = 0.0

        # Signal 4: low_progress — content barely changed at all
        overall_sim = _similarity(texts[0], texts[-1])
        low_progress = overall_sim if overall_sim > 0.9 else 0.0

        composite = (
            0.30 * trial_and_error
            + 0.25 * undo_revert
            + 0.25 * repeated_output
            + 0.20 * low_progress
        )

        if composite >= STRUGGLE_THRESHOLD:
            self._last_struggle_ts = now
            return {
                "score": composite,
                "signals": {
                    "trial_and_error": trial_and_error,
                    "undo_revert": undo_revert,
                    "repeated_output": repeated_output,
                    "low_progress": low_progress,
                },
                "window_title": recent[-1].window_title,
            }
        return None
