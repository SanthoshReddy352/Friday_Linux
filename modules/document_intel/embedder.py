"""Embedder — reuses the all-MiniLM-L6-v2 model already in the project.

Holds a module-level singleton to avoid double-loading when both
EmbeddingRouter and DocumentIntelService are active.
"""
from __future__ import annotations

from core.logger import logger

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_shared_model = None


def _get_model():
    global _shared_model
    if _shared_model is not None:
        return _shared_model
    try:
        from sentence_transformers import SentenceTransformer
        logger.info("[doc_intel] Loading embedding model %s…", _MODEL_NAME)
        _shared_model = SentenceTransformer(_MODEL_NAME)
        return _shared_model
    except ImportError:
        raise RuntimeError(
            "sentence-transformers is not installed. Run: pip install sentence-transformers"
        )


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns a 384-dimensional float vector."""
    vec = _get_model().encode(text, convert_to_numpy=True)
    return vec.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. More efficient than calling embed_text in a loop."""
    vecs = _get_model().encode(texts, convert_to_numpy=True, batch_size=32)
    return [v.tolist() for v in vecs]
