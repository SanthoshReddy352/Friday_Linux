"""DocumentIntelPlugin — registers query_document and search_workspace capabilities."""
from __future__ import annotations

import re as _re

from core.logger import logger
from core.plugin_manager import FridayPlugin


class DocumentIntelPlugin(FridayPlugin):
    name = "document_intel"

    def __init__(self, app):
        super().__init__(app)
        self.name = "document_intel"
        self._service = None
        self._watcher = None
        self.on_load()

    def on_load(self) -> None:
        cfg = self._get_cfg()
        if not cfg.get("enabled", False):
            logger.info("[doc_intel] Plugin disabled in config (document_intel.enabled: false).")
            return

        self._lite_mode = False
        try:
            from modules.document_intel.service import DocumentIntelService
            self._service = DocumentIntelService(cfg)
        except ImportError as exc:
            # chromadb / sentence-transformers missing — fall back to MarkItDown-only lite mode.
            # query_document still works (converts + reads the file directly).
            # search_workspace is skipped (requires vector store).
            logger.info(
                "[doc_intel] Vector store unavailable (%s) — running in lite mode "
                "(MarkItDown conversion only, no cross-document search). "
                "Run: pip install chromadb sentence-transformers to enable full RAG.", exc
            )
            self._service = None
            self._lite_mode = True

        _QUERY_DOC_SPEC = {
            "name": "query_document",
            "description": (
                "Ask a question about a specific document file (PDF, DOCX, PPTX, XLSX, TXT, MD). "
                "Summarizes the file or retrieves specific information from it."
            ),
            "parameters": {
                "file_path": "string — absolute or relative path to the document",
                "question": "string — what to find or summarize in the document",
            },
            "aliases": [
                "summarize this pdf", "summarize this document", "summarize document",
                "what does this document say", "read this pdf", "read this document",
                "what are the key points of", "analyze this document",
                "what is in this document", "explain this document",
            ],
            "patterns": [
                r"\b(?:summarize|explain|analyze|read)\s+(?:this\s+|the\s+)?(?:pdf|docx?|document|file)\b",
                r"\bwhat(?:'s|\s+are|\s+is)\s+(?:the\s+)?(?:key\s+points?|summary|main\s+points?)\s+(?:of|in)\b",
                r"\bwhat\s+does\s+(?:this\s+|the\s+)?(?:document|file|pdf)\s+(?:say|contain)\b",
            ],
            "context_terms": [
                "summarize", "what does", "explain", "search document",
                "read file", "key points", "what is in", "document",
                "summarize this pdf", "what does this document say",
            ],
        }
        self.app.router.register_tool(_QUERY_DOC_SPEC, self._handle_query_document)

        if not self._lite_mode:
            self.app.router.register_tool(
                {
                    "name": "search_workspace",
                    "description": (
                        "Search across all indexed documents and notes in the workspace. "
                        "Finds relevant content from any previously indexed file."
                    ),
                    "parameters": {
                        "query": "string — what to search for",
                        "workspace": "string — optional workspace filter (default: all)",
                    },
                    "aliases": [
                        "search my notes", "search my documents",
                        "search workspace", "find in my documents",
                        "look through my files", "what did I write about",
                    ],
                    "patterns": [
                        r"\bsearch\s+(?:my\s+)?(?:notes|documents|workspace|files)\b",
                        r"\bfind\s+(?:anything\s+)?about\s+.+\s+in\s+(?:my\s+)?(?:notes|documents|workspace)\b",
                    ],
                    "context_terms": [
                        "search my notes", "find in docs", "what did I write",
                        "search workspace", "find anything about", "in my notes",
                        "search my documents", "look through my files",
                    ],
                },
                self._handle_search_workspace,
            )

            # Phase 5: start workspace watcher if auto_index is enabled
            if cfg.get("auto_index", False):
                folders = cfg.get("workspace_folders", [])
                if folders:
                    try:
                        from modules.document_intel.workspace_watcher import WorkspaceWatcher
                        extensions = cfg.get("index_extensions", [".pdf", ".docx", ".md", ".txt"])
                        self._watcher = WorkspaceWatcher(
                            service=self._service,
                            turn_feedback=getattr(self.app, "turn_feedback", None),
                            folders=folders,
                            extensions=extensions,
                        )
                        self._watcher.start()
                        logger.info("[doc_intel] Workspace watcher started for %d folder(s).", len(folders))
                    except Exception as exc:
                        logger.warning("[doc_intel] Workspace watcher failed to start: %s", exc)

        mode = "lite (MarkItDown only)" if self._lite_mode else "full (MarkItDown + ChromaDB RAG)"
        registered = 1 if self._lite_mode else 2
        logger.info("[doc_intel] Plugin loaded in %s mode — %d tool(s) registered.", mode, registered)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_query_document(self, raw_text: str, args: dict):
        from core.capability_registry import CapabilityExecutionResult
        file_path = args.get("file_path", "")
        question = args.get("question") or raw_text

        # Phase 5: detect active_document injected by IntentRecognizer for follow-up turns
        injected = _re.search(r"\[active_document=([^\]]+)\]", raw_text)
        if injected and not file_path:
            file_path = injected.group(1).strip()
            clean_text = _re.sub(r"\[active_document=[^\]]+\]\s*", "", raw_text).strip()
            question = args.get("question") or clean_text or raw_text

        if not file_path:
            return CapabilityExecutionResult(
                ok=False,
                name="query_document",
                error="No file path provided. Example: 'summarize ~/Documents/report.pdf'",
            )

        if self._lite_mode:
            return self._handle_query_document_lite(file_path, question)

        try:
            context = self._service.query_document(file_path, question)
            result = CapabilityExecutionResult(
                ok=True, name="query_document",
                output=context, output_type="document",
            )
            # Save active_document so the next follow-up turn can omit the file path
            store = getattr(self.app, "context_store", None)
            session_id = getattr(self.app, "session_id", "")
            if store and session_id:
                try:
                    store.save_reference(session_id, "active_document", file_path)
                except Exception:
                    pass
            return result
        except Exception as exc:
            logger.error("[doc_intel] query_document failed: %s", exc)
            return CapabilityExecutionResult(ok=False, name="query_document", error=str(exc))

    def _handle_query_document_lite(self, file_path: str, question: str):
        """Lite-mode handler: MarkItDown conversion with no vector indexing."""
        from core.capability_registry import CapabilityExecutionResult
        import os
        resolved = os.path.expanduser(file_path)
        try:
            from modules.document_intel.converter import convert_to_markdown
            content = convert_to_markdown(resolved)
        except Exception as exc:
            return CapabilityExecutionResult(ok=False, name="query_document", error=str(exc))

        max_chars = 6000
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[… content truncated …]"

        store = getattr(self.app, "context_store", None)
        session_id = getattr(self.app, "session_id", "")
        if store and session_id:
            try:
                store.save_reference(session_id, "active_document", file_path)
            except Exception:
                pass

        return CapabilityExecutionResult(
            ok=True, name="query_document",
            output=content, output_type="document",
        )

    def _handle_search_workspace(self, raw_text: str, args: dict):
        from core.capability_registry import CapabilityExecutionResult
        query = args.get("query") or raw_text
        workspace = args.get("workspace")
        try:
            context = self._service.search_workspace(query, workspace=workspace)
            return CapabilityExecutionResult(
                ok=True, name="search_workspace",
                output=context, output_type="document",
            )
        except Exception as exc:
            logger.error("[doc_intel] search_workspace failed: %s", exc)
            return CapabilityExecutionResult(ok=False, name="search_workspace", error=str(exc))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_cfg(self) -> dict:
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            return config.get("document_intel") or {}
        return {}
