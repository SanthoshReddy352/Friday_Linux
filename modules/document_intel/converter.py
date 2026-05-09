"""MarkItDown wrapper with error handling and format validation."""
from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt", ".html", ".csv"}


def convert_to_markdown(file_path: str | Path) -> str:
    """Convert a document to Markdown text using MarkItDown.

    Returns the Markdown string. Raises on unsupported formats or parse errors.
    enable_plugins=False keeps conversion offline and deterministic.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format: {path.suffix}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    from markitdown import MarkItDown
    md = MarkItDown(enable_plugins=False)
    result = md.convert(str(path))
    text = result.text_content or ""
    if not text.strip():
        raise ValueError(f"Document converted to empty content: {path}")
    return text
