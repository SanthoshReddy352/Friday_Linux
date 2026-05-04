"""Embedding infrastructure for FRIDAY memory stores.

Phase 7: Provides a real semantic embedder (BGESmallEmbedder) with
automatic fallback to a deterministic hash-based embedder when
sentence-transformers is not installed.

Usage:
    embedder = get_best_embedder()  # picks BGE or Hash automatically
    vectors = embedder.embed(["some text"])
"""
from __future__ import annotations

import hashlib
import struct
from abc import ABC, abstractmethod
from typing import List


class EmbedderProtocol(ABC):
    """Contract every embedder must satisfy."""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...


class HashEmbedder(EmbedderProtocol):
    """Deterministic SHA-256 based embedder — no model download required.

    Not semantically meaningful but provides consistent, stable vector
    identities for deduplication and approximate retrieval. Used as the
    low-memory fallback when sentence-transformers is unavailable.
    """

    def __init__(self, dimensions: int = 64):
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.encode()).digest()
        # Tile digest to cover requested dimensions
        tiled = digest * ((self._dimensions // len(digest)) + 1)
        return [(struct.unpack_from("B", tiled, i)[0] / 255.0) * 2.0 - 1.0 for i in range(self._dimensions)]


class BGESmallEmbedder(EmbedderProtocol):
    """Semantic embedder using BAAI/bge-small-en-v1.5 (~130 MB, CPU-capable).

    Requires:  pip install sentence-transformers
    The model is downloaded on first use to ~/.cache/huggingface/.

    Prefer get_best_embedder() over instantiating this directly so callers
    get the hash fallback automatically when the package is missing.
    """

    MODEL_NAME = "BAAI/bge-small-en-v1.5"
    _DIMENSIONS = 384

    def __init__(self):
        self._model = None

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self._model is None:
            self._load()
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def _load(self) -> None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self._model = SentenceTransformer(self.MODEL_NAME)


def get_best_embedder() -> EmbedderProtocol:
    """Return BGESmallEmbedder if sentence-transformers is available, else HashEmbedder."""
    try:
        import sentence_transformers  # noqa: F401

        return BGESmallEmbedder()
    except ImportError:
        return HashEmbedder(dimensions=64)
