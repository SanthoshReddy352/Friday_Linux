"""Lightweight text normalization for the routing layer (Batch 2 / Issues 2, 8).

Two operations, both kept conservative so they never corrupt valid input:

1. **STT typo correction** — a curated, full-token map of common
   Whisper / faster-whisper mis-transcriptions (``calender`` -> ``calendar``,
   ``evnet`` -> ``event``, ``recieve`` -> ``receive``). Applied once at the
   top of ``CommandRouter.process_text`` and ``IntentRecognizer.plan`` so
   downstream parsers see the cleaned form.

2. **Fuzzy command match** — ``fuzzy_command_match`` returns the closest
   canonical phrase (using rapidfuzz ``token_set_ratio``) above a threshold.
   Used by the router to accept "set voice to manual" when the registered
   canonical is "set voice mode to manual". Returns ``None`` gracefully when
   rapidfuzz is not installed (preflight will warn separately).

The misspelling table is intentionally small. Each entry must be a token
that does not appear as a valid English word. Substring replacement is
forbidden — we always work on word boundaries so we never break legitimate
text. Never add anything that might be a real word in some domain.
"""

from __future__ import annotations

import re
from typing import Iterable

# Conservative, full-token misspelling map. Order does not matter — we
# build one regex with all keys. Keep entries to common STT artefacts
# observed in real FRIDAY logs; speculative additions should land with a
# concrete log citation in the PR.
_STT_TYPOS: dict[str, str] = {
    # Calendar / events
    "calender": "calendar",
    "callender": "calendar",
    "calandar": "calendar",
    "evnet": "event",
    "evant": "event",
    "scheule": "schedule",
    "shedule": "schedule",
    "schduled": "scheduled",
    "shecdule": "schedule",
    # Time
    "tommorow": "tomorrow",
    "tommorrow": "tomorrow",
    "tomorow": "tomorrow",
    # Memory / reminders
    "remmber": "remember",
    "remeber": "remember",
    "rememer": "remember",
    "reminer": "reminder",
    # Misc frequent STT artefacts
    "recieve": "receive",
    "definately": "definitely",
    "wether": "weather",
    "wheather": "weather",
    "freind": "friend",
    "cancle": "cancel",
    "cancell": "cancel",
    # Wake-word transcription failures observed in logs
    "fridya": "friday",
    "fridey": "friday",
    "friady": "friday",
}


_TYPO_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _STT_TYPOS) + r")\b",
    re.IGNORECASE,
)


def normalize_for_routing(text: str) -> str:
    """Return ``text`` with known STT mis-transcriptions corrected.

    Case of the leading character is preserved so capitalised words remain
    capitalised. Words not in the typo table are returned unchanged — this
    function must never alter semantic content.
    """
    if not text:
        return text

    def _sub(match: re.Match[str]) -> str:
        original = match.group(0)
        replacement = _STT_TYPOS[original.lower()]
        if original[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    return _TYPO_RE.sub(_sub, text)


def fuzzy_command_match(
    text: str,
    canonical_phrases: Iterable[str],
    threshold: int = 85,
) -> str | None:
    """Return the canonical phrase most similar to ``text``, or ``None``.

    Similarity is rapidfuzz ``token_set_ratio`` which is order-insensitive
    and forgiving of dropped modifier words ("set voice manual" vs the
    canonical "set voice mode to manual" scores ~88). The default
    threshold (85) was tuned so that random short utterances do not
    spuriously match — e.g. "hello there" against any registered command
    scores well below 85.

    When ``rapidfuzz`` is unavailable the function returns ``None``; the
    deterministic regex layer and the embedding router both still work,
    so this is a soft degradation surfaced by the preflight LITE MODE
    badge rather than an outright failure.
    """
    try:
        from rapidfuzz import fuzz  # noqa: PLC0415
    except ImportError:
        return None
    if not text:
        return None
    phrases = list(canonical_phrases)
    if not phrases:
        return None
    text_l = text.lower().strip()
    best: str | None = None
    best_score = -1.0
    for phrase in phrases:
        if not phrase:
            continue
        score = fuzz.token_set_ratio(text_l, phrase.lower())
        if score > best_score:
            best, best_score = phrase, float(score)
    if best_score >= threshold:
        return best
    return None
