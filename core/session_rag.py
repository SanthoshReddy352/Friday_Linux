"""Session-scoped in-memory RAG using BM25-style keyword retrieval.

No embedding model, no extra LLM calls. Converts documents via MarkItDown,
splits into chunks, and scores by BM25 at retrieval time. Cleared when the
session ends or the user loads a new file.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


def _tokenize(text: str) -> list[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in (text or ""))
    return [t for t in cleaned.split() if len(t) > 1]


@dataclass
class _Chunk:
    text: str
    heading: str
    index: int
    tf: Counter = field(default_factory=Counter)

    def __post_init__(self):
        self.tf = Counter(_tokenize(self.text))


def _split_chunks(markdown: str, max_chars: int = 600) -> list[_Chunk]:
    chunks: list[_Chunk] = []
    current_heading = ""
    index = 0

    # Split on markdown headings so each section stays together
    sections = re.split(r"(?m)^(#{1,3} .+)$", markdown)
    for part in sections:
        if re.match(r"^#{1,3} ", part):
            current_heading = part.strip()
            continue
        if not part.strip():
            continue
        paragraphs = re.split(r"\n{2,}", part)
        buffer = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(buffer) + len(para) > max_chars and buffer:
                chunks.append(_Chunk(text=buffer.strip(), heading=current_heading, index=index))
                index += 1
                buffer = para
            else:
                buffer = (buffer + "\n\n" + para).strip() if buffer else para
        if buffer.strip():
            chunks.append(_Chunk(text=buffer.strip(), heading=current_heading, index=index))
            index += 1

    # Safety net: if splitting produced nothing (e.g. flat CSV, no headings),
    # treat the entire document as one chunk — no truncation.
    return chunks or [_Chunk(text=markdown, heading="", index=0)]


class SessionRAG:
    """In-memory BM25 retriever for a single session document.

    Zero extra inference cost: no embedding model, no LLM calls.
    Retrieval is pure keyword scoring at query time (~1ms).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._chunks: list[_Chunk] = []
        self._df: Counter = Counter()
        self._source_name: str = ""
        self._total_chars: int = 0

    @property
    def is_active(self) -> bool:
        return bool(self._chunks)

    @property
    def source_name(self) -> str:
        return self._source_name

    # Formats readable without MarkItDown
    _PLAIN_SUFFIXES = {".txt", ".md", ".csv", ".html"}

    def load_file(self, path: str | Path) -> str:
        """Convert *path* to markdown, chunk it, and build the BM25 index.

        Returns a human-readable status message. Replaces any previously
        loaded document — only one file is active per session.
        """
        path = Path(path)
        markdown = self._convert(path)
        chunks = _split_chunks(markdown)

        df: Counter = Counter()
        for chunk in chunks:
            for term in set(chunk.tf.keys()):
                df[term] += 1

        with self._lock:
            self._chunks = chunks
            self._df = df
            self._source_name = path.name
            self._total_chars = sum(len(c.text) for c in chunks)

        return f"Loaded '{path.name}' — {len(chunks)} chunks indexed."

    def retrieve(self, query: str, top_k: int = 3) -> list[str]:
        """Return the top-k most relevant chunk texts for *query*."""
        if not self._chunks:
            return []
        query_terms = Counter(_tokenize(query))
        if not query_terms:
            return [c.text for c in self._chunks[:top_k]]

        with self._lock:
            n = len(self._chunks)
            scored: list[tuple[float, _Chunk]] = []
            k1, b = 1.5, 0.0
            for chunk in self._chunks:
                score = 0.0
                for term, _qf in query_terms.items():
                    tf = chunk.tf.get(term, 0)
                    if tf == 0:
                        continue
                    df = self._df.get(term, 1)
                    idf = math.log((n - df + 0.5) / (df + 0.5) + 1.0)
                    score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b))
                if score > 0:
                    scored.append((score, chunk))

            scored.sort(key=lambda x: -x[0])
            return [chunk.text for _, chunk in scored[:top_k]]

    def get_context_block(self, query: str, top_k: int = 3) -> str:
        """Return a formatted context string ready to inject into the LLM prompt."""
        chunks = self.retrieve(query, top_k=top_k)
        if not chunks:
            return ""
        joined = "\n\n---\n\n".join(chunks)
        return (
            f"[Relevant excerpts from '{self._source_name}' — use these to answer the user]\n"
            f"{joined}\n"
            f"[End of document excerpts]"
        )

    def clear(self):
        with self._lock:
            self._chunks = []
            self._df = Counter()
            self._source_name = ""
            self._total_chars = 0

    def _convert(self, path: Path) -> str:
        """Convert *path* to a markdown string.

        Uses MarkItDown when available. Falls back to direct UTF-8 read for
        plain-text formats so .txt / .md / .csv / .html work without MarkItDown.
        Raises a helpful ImportError for binary formats that require it.
        """
        try:
            from modules.document_intel.converter import convert_to_markdown
            return convert_to_markdown(path)
        except (ImportError, ModuleNotFoundError):
            suffix = path.suffix.lower()
            if suffix in self._PLAIN_SUFFIXES:
                text = path.read_text(encoding="utf-8", errors="replace")
                if not text.strip():
                    raise ValueError(f"File is empty: {path.name}")
                return text
            raise ImportError(
                f"MarkItDown is required to load {suffix} files. "
                f"Install it with: pip install markitdown"
            )
