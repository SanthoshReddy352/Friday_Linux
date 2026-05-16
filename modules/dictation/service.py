"""Dictation session service.

Owns a single in-progress memo at a time. The STT plugin consults
``is_active()`` and routes raw transcripts to ``append()`` instead of the
normal command pipeline. ``stop()`` flushes the buffer to disk.
"""
from __future__ import annotations

import os
import re
import threading
from datetime import datetime
from dataclasses import dataclass

from core.logger import logger


END_PHRASES = (
    "end memo",
    "end the memo",
    "end dictation",
    "end the dictation",
    "stop memo",
    "stop the memo",
    "stop dictation",
    "stop the dictation",
    "stop dictating",
    "finish memo",
    "finish dictation",
    "save memo",
    "save the memo",
    "save dictation",
    "save the dictation",
    "close memo",
    "close the memo",
)

CANCEL_PHRASES = (
    "cancel memo",
    "cancel the memo",
    "cancel dictation",
    "cancel the dictation",
    "discard memo",
    "discard the memo",
    "throw away the memo",
)


@dataclass
class DictationSession:
    label: str
    started_at: datetime
    file_path: str
    chunks: list[str]


class DictationService:
    DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "friday-memos")

    def __init__(self, app):
        self.app = app
        self._lock = threading.Lock()
        self._session: DictationSession | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        return self._session is not None

    def current_label(self) -> str:
        return self._session.label if self._session else ""

    def start(self, label: str = "", target_path: str = "") -> tuple[bool, str]:
        """Begin a dictation session.

        When ``target_path`` is non-empty the captured content is written to
        that exact file on ``stop()`` instead of an auto-built memo path —
        used by the file-creation workflow's "dictate the content" branch
        (Issue 4). Otherwise we fall back to a timestamped memo in
        ``~/Documents/friday-memos``.
        """
        with self._lock:
            if self._session is not None:
                return False, f"Dictation is already active — saying things like '{self._session.label}' lands in that memo."
            label = self._sanitize_label(label) or "memo"
            now = datetime.now()
            file_path = target_path.strip() or self._build_path(label, now)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            session = DictationSession(label=label, started_at=now, file_path=file_path, chunks=[])
            self._session = session
        logger.info("[dictation] Started session '%s' → %s", session.label, session.file_path)
        return True, (
            f"Dictation started. I'm capturing everything you say into {os.path.basename(session.file_path)}. "
            "Say 'Friday end memo' when you're done, or 'Friday cancel memo' to throw it away."
        )

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            session = self._session
            self._session = None
        if session is None:
            return False, "I'm not in a dictation session right now."
        text = self._compose_text(session)
        try:
            with open(session.file_path, "w", encoding="utf-8") as handle:
                handle.write(text)
        except Exception as exc:
            logger.error("[dictation] Failed to save memo to %s: %s", session.file_path, exc)
            return False, f"Couldn't save the memo: {exc}"
        word_count = len(text.split())
        logger.info("[dictation] Saved %d-word memo to %s", word_count, session.file_path)
        # Issue 7: register the just-saved memo as the working artifact so the
        # next "read it" / "open it" / "summarize it" pronoun resolves to this
        # file and not the previously-active artifact (e.g. ideas.md). Best-
        # effort — if the session/memory services aren't available (tests),
        # the dictation still succeeds.
        self._publish_artifact(session, text)
        return True, (
            f"Saved your {word_count}-word memo to {os.path.basename(session.file_path)} "
            f"in the friday-memos folder."
        )

    def cancel(self) -> tuple[bool, str]:
        with self._lock:
            session = self._session
            self._session = None
        if session is None:
            return False, "There's no active dictation to cancel."
        logger.info("[dictation] Cancelled session '%s'", session.label)
        return True, "Dictation cancelled. Nothing was saved."

    def append(self, text: str) -> bool:
        """Add a raw transcript chunk. Returns True if accepted."""
        chunk = (text or "").strip()
        if not chunk:
            return False
        with self._lock:
            if self._session is None:
                return False
            self._session.chunks.append(chunk)
        return True

    # ------------------------------------------------------------------
    # End / cancel detection — exposed so STT can match phrases without
    # reaching into END_PHRASES directly.
    # ------------------------------------------------------------------

    def detect_control_phrase(self, text: str) -> str:
        """Return 'end' / 'cancel' / '' for the given transcript."""
        normalized = re.sub(r"[^a-z\s]", " ", (text or "").lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return ""
        for phrase in CANCEL_PHRASES:
            if phrase in normalized:
                return "cancel"
        for phrase in END_PHRASES:
            if phrase in normalized:
                return "end"
        return ""

    def strip_control_phrase(self, text: str) -> str:
        normalized = (text or "").strip()
        for phrase in END_PHRASES + CANCEL_PHRASES:
            normalized = re.sub(rf"\bfriday\s+{re.escape(phrase)}\b", " ", normalized, flags=re.IGNORECASE)
            normalized = re.sub(rf"\b{re.escape(phrase)}\b", " ", normalized, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", normalized).strip(" .,!?'\"")

    def _publish_artifact(self, session: DictationSession, text: str) -> None:
        """Make the saved memo the active WorkingArtifact (Issue 7).

        Marks scope=explicit so subsequent "read it" pronoun resolution lands
        on the memo even if some other tool sets an auto-scope artifact in
        the same session afterwards.
        """
        session_id = getattr(self.app, "session_id", None)
        memory = getattr(self.app, "memory_service", None) or getattr(self.app, "context_store", None)
        if not session_id or memory is None or not hasattr(memory, "save_artifact"):
            return
        try:
            from core.context_store import WorkingArtifact  # noqa: PLC0415
            preview = (text or "").strip()[:500]
            artifact = WorkingArtifact(
                content=preview,
                output_type="text",
                capability_name="dictation",
                artifact_type="memo",
                source_path=session.file_path,
                scope="explicit",
            )
            memory.save_artifact(session_id, artifact)
        except Exception as exc:
            logger.debug("[dictation] save_artifact skipped: %s", exc)
        # Update DialogState.selected_file too so the WorkspaceFileController's
        # "use_selected_file" path lights up for "open it" / "read it".
        dialog_state = getattr(self.app, "dialog_state", None)
        if dialog_state is not None and hasattr(dialog_state, "remember_file"):
            try:
                dialog_state.remember_file(session.file_path)
            except Exception as exc:
                logger.debug("[dictation] remember_file skipped: %s", exc)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _sanitize_label(self, label: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9 _\-]+", " ", (label or "").strip())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned[:64]

    def _build_path(self, label: str, when: datetime) -> str:
        slug = re.sub(r"\s+", "-", label.lower())
        slug = re.sub(r"[^a-z0-9\-_]", "", slug) or "memo"
        filename = f"{when.strftime('%Y-%m-%d_%H%M')}_{slug}.md"
        return os.path.join(self.DEFAULT_DIR, filename)

    def _compose_text(self, session: DictationSession) -> str:
        header = (
            f"# {session.label.title()}\n"
            f"_Recorded {session.started_at.strftime('%Y-%m-%d %H:%M')}_\n\n"
        )
        body = " ".join(chunk.strip() for chunk in session.chunks if chunk.strip())
        # Capitalize start, add trailing period if missing.
        body = body.strip()
        if body:
            body = body[0].upper() + body[1:]
            if body[-1] not in ".!?":
                body += "."
        return f"{header}{body}\n"
