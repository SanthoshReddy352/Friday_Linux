"""Heading-first chunker for Markdown documents.

Strategy:
  1. Split on Markdown headings (## Section, ### Subsection)
  2. If a section exceeds max_tokens: split on paragraph boundaries
  3. If a paragraph exceeds max_tokens: hard split with overlap
  4. Prepend parent heading to each chunk for retrieval context

Heading-prefixed chunks improve retrieval because the semantic model can
match questions to section labels without reading content.
"""
from __future__ import annotations

import re

MAX_TOKENS = 400
OVERLAP_TOKENS = 80
HEADING_PATTERN = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def _rough_token_count(text: str) -> int:
    return int(len(text.split()) * 1.3)


def _split_by_overlap(text: str, max_tokens: int, overlap: int) -> list[str]:
    words = text.split()
    chunks = []
    step = max(1, max_tokens - overlap)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + max_tokens])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def chunk_markdown(
    text: str,
    max_tokens: int = MAX_TOKENS,
    overlap: int = OVERLAP_TOKENS,
    source_path: str = "",
) -> list[dict]:
    """Chunk Markdown text into retrieval-ready fragments.

    Returns a list of dicts: {"text": str, "heading": str, "chunk_index": int, "source": str}
    """
    chunks: list[dict] = []
    chunk_index = 0

    def _emit(content: str, heading: str) -> None:
        nonlocal chunk_index
        content = content.strip()
        if not content:
            return
        if _rough_token_count(content) <= max_tokens:
            prefix = f"{heading}\n\n" if heading else ""
            chunks.append({
                "text": prefix + content,
                "heading": heading,
                "chunk_index": chunk_index,
                "source": source_path,
            })
            chunk_index += 1
        else:
            paragraphs = re.split(r"\n{2,}", content)
            buf = ""
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                candidate = buf + "\n\n" + para if buf else para
                if _rough_token_count(candidate) > max_tokens:
                    if buf:
                        prefix = f"{heading}\n\n" if heading else ""
                        chunks.append({
                            "text": prefix + buf.strip(),
                            "heading": heading,
                            "chunk_index": chunk_index,
                            "source": source_path,
                        })
                        chunk_index += 1
                    buf = para
                else:
                    buf = candidate
            if buf.strip():
                if _rough_token_count(buf) > max_tokens:
                    for sub in _split_by_overlap(buf, max_tokens, overlap):
                        prefix = f"{heading}\n\n" if heading else ""
                        chunks.append({
                            "text": prefix + sub,
                            "heading": heading,
                            "chunk_index": chunk_index,
                            "source": source_path,
                        })
                        chunk_index += 1
                else:
                    prefix = f"{heading}\n\n" if heading else ""
                    chunks.append({
                        "text": prefix + buf.strip(),
                        "heading": heading,
                        "chunk_index": chunk_index,
                        "source": source_path,
                    })
                    chunk_index += 1

    raw_parts = HEADING_PATTERN.split(text)

    # raw_parts = [pre_heading_text, group1(#), group2(heading), body, group1, group2, body, ...]
    # When text starts with a heading, pre_heading_text is '' — emit it either way (no-op if empty).
    if raw_parts:
        _emit(raw_parts[0], "")
        raw_parts = raw_parts[1:]

    # Process heading sections — each iteration consumes (level_hashes, heading_text, body)
    it = iter(raw_parts)
    for level in it:
        heading_text = next(it, "")
        body = next(it, "")
        hashes = "#" * len(level) if level else ""
        current_heading = f"{hashes} {heading_text}".strip()
        _emit(body, current_heading)

    return chunks
