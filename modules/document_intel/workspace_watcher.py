"""Background workspace watcher using watchdog.

Monitors configured folders for new/changed documents and queues them for indexing.
Indexing is gated: runs only when no active voice turn is in progress so it never
contends with inference or TTS.

Usage:
    watcher = WorkspaceWatcher(service, turn_feedback, folders=[...], extensions=[...])
    watcher.start()   # starts observer + drain thread
    watcher.stop()    # call on app shutdown
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from core.logger import logger

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    # Stub so the class definition below still compiles.
    class FileSystemEventHandler:  # type: ignore
        pass

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt"}
_INDEX_ONLY_SENTINEL = "_index_only_"


class WorkspaceWatcher:
    """Watches workspace folders and background-indexes new/changed files."""

    def __init__(
        self,
        service,
        turn_feedback,
        folders: list[str],
        extensions: list[str] | None = None,
    ):
        self._service = service
        self._feedback = turn_feedback
        self._folders = [Path(f).expanduser() for f in (folders or [])]
        self._extensions = set(extensions) if extensions else SUPPORTED_EXTENSIONS
        self._queue: queue.Queue[Path] = queue.Queue()
        self._observer = None
        self._worker: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        if not _WATCHDOG_AVAILABLE:
            logger.warning("[doc_intel] watchdog not installed — workspace auto-index disabled. "
                           "Run: pip install watchdog")
            return
        if not self._folders:
            logger.info("[doc_intel] No workspace_folders configured — watcher idle.")
            return

        handler = _QueueHandler(self._queue, self._extensions)
        self._observer = Observer()
        watched = 0
        for folder in self._folders:
            if folder.exists():
                self._observer.schedule(handler, str(folder), recursive=True)
                logger.info("[doc_intel] Watching folder: %s", folder)
                watched += 1
            else:
                logger.warning("[doc_intel] Workspace folder not found (skipped): %s", folder)

        if watched == 0:
            logger.warning("[doc_intel] No watchable folders found — observer not started.")
            return

        self._running = True
        self._observer.start()
        self._worker = threading.Thread(
            target=self._drain_loop, name="doc-indexer", daemon=True
        )
        self._worker.start()
        logger.info("[doc_intel] Workspace watcher started (%d folder(s)).", watched)

    def stop(self) -> None:
        self._running = False
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=3.0)
            except Exception:
                pass

    def enqueue(self, path: Path) -> None:
        """Manually queue a file for background indexing (e.g. at startup)."""
        if path.suffix.lower() in self._extensions and path.is_file():
            self._queue.put(path)

    # ------------------------------------------------------------------
    # Background drain loop
    # ------------------------------------------------------------------

    def _drain_loop(self) -> None:
        while self._running:
            try:
                path = self._queue.get(timeout=5.0)
            except queue.Empty:
                continue

            # Gate: wait until no active voice turn so inference lock is free
            while getattr(self._feedback, "active_turns", 0) > 0:
                time.sleep(1.0)
                if not self._running:
                    return

            try:
                n = self._service.index_document(str(path))
                if n > 0:
                    logger.info("[doc_intel] Background indexed %d chunks: %s", n, path.name)
            except Exception as exc:
                logger.warning("[doc_intel] Failed to index %s: %s", path, exc)


class _QueueHandler(FileSystemEventHandler):
    def __init__(self, q: "queue.Queue[Path]", extensions: set[str]):
        super().__init__()
        self._queue = q
        self._extensions = extensions

    def on_modified(self, event) -> None:
        self._maybe_queue(event)

    def on_created(self, event) -> None:
        self._maybe_queue(event)

    def _maybe_queue(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in self._extensions:
            self._queue.put(path)
