"""DocumentRetriever — orchestrates embed → query → context budget enforcement."""
from __future__ import annotations

MAX_RETRIEVAL_CHUNKS = 4
MAX_CONTEXT_TOKENS = 1500


class DocumentRetriever:
    def __init__(self, document_store):
        self._store = document_store

    def query(
        self,
        question: str,
        top_k: int = MAX_RETRIEVAL_CHUNKS,
        workspace: str | None = None,
    ) -> list[dict]:
        from modules.document_intel.embedder import embed_text
        embedding = embed_text(question)
        return self._store.query(embedding, top_k=top_k, workspace=workspace)

    def build_context_for_llm(self, chunks: list[dict]) -> str:
        """Format retrieved chunks for LLM context injection.

        Enforces the 1500-token hard limit so the chat model context is not blown.
        """
        parts = []
        token_count = 0
        for chunk in chunks:
            chunk_tokens = int(len(chunk["text"].split()) * 1.3)
            if token_count + chunk_tokens > MAX_CONTEXT_TOKENS:
                break
            source = chunk.get("source_file", "")
            heading = chunk.get("heading", "")
            label = f"[{source}]" + (f" {heading}" if heading else "")
            parts.append(f"{label}\n{chunk['text']}")
            token_count += chunk_tokens
        return "\n\n---\n\n".join(parts)
