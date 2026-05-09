"""DocumentIntelService — orchestrates the full document pipeline."""
from __future__ import annotations

from pathlib import Path

from core.logger import logger
from modules.document_intel.converter import convert_to_markdown
from modules.document_intel.chunker import chunk_markdown
from modules.document_intel.document_store import DocumentStore
from modules.document_intel.retriever import DocumentRetriever


class DocumentIntelService:
    def __init__(self, config: dict):
        chroma_path = config.get("chroma_path", "data/chroma")
        db_path = config.get("db_path", "data/friday.db")
        self._store = DocumentStore(chroma_path=chroma_path, db_path=db_path)
        self._retriever = DocumentRetriever(self._store)
        self._max_chunks = int(config.get("max_chunks", 4))

    def index_document(self, file_path: str, workspace: str = "default") -> int:
        """Index a document without running a retrieval query.

        Used by the background workspace watcher. Returns chunk count (0 if already indexed).
        """
        path = Path(file_path).expanduser().resolve()
        if self._store.is_indexed(str(path)):
            return 0
        logger.info("[doc_intel] Background indexing: %s", path)
        markdown = convert_to_markdown(str(path))
        chunks = chunk_markdown(markdown, source_path=str(path))
        self._store.add_chunks(str(path), chunks, workspace=workspace)
        logger.info("[doc_intel] Indexed %d chunks from %s", len(chunks), path.name)
        return len(chunks)

    def query_document(self, file_path: str, question: str, workspace: str = "default") -> str:
        """Index file if needed, then retrieve context for the question."""
        path = Path(file_path).expanduser().resolve()

        if not self._store.is_indexed(str(path)):
            logger.info("[doc_intel] Indexing: %s", path)
            markdown = convert_to_markdown(str(path))
            chunks = chunk_markdown(markdown, source_path=str(path))
            self._store.add_chunks(str(path), chunks, workspace=workspace)
            logger.info("[doc_intel] Indexed %d chunks from %s", len(chunks), path.name)

        chunks = self._retriever.query(question, top_k=self._max_chunks)
        if not chunks:
            return f"No relevant content found in {path.name} for: {question}"
        return self._retriever.build_context_for_llm(chunks)

    def search_workspace(self, query: str, workspace: str | None = None) -> str:
        """Search across all indexed documents in a workspace."""
        chunks = self._retriever.query(query, top_k=self._max_chunks, workspace=workspace)
        if not chunks:
            return "No results found. Make sure documents are indexed first."
        return self._retriever.build_context_for_llm(chunks)
