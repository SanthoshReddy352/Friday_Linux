"""Embedding-based tool router (cosine match on sentence-transformer embeddings).

Sits between the deterministic router (cheap regex / keyword match) and the
LLM-based tool model (~3-4s on a 4B). When the deterministic layer comes up
empty, this layer compares the utterance against every registered tool's
embedded description + canonical phrasings. If the top-1 cosine similarity
is above the dispatch threshold, we route directly without invoking the LLM,
catching paraphrases that the regex layer missed.

Latency on CPU with all-MiniLM-L6-v2: ~10-20 ms per route call after warmup.
First-call cost includes a one-time ~90 MB model download (cached afterward).

Design notes:
* Lazy initialization — the model only loads when the router is asked for a
  match, so cold start of FRIDAY isn't slowed by it.
* Embeddings are L2-normalized at index-build time, so similarity is a single
  matrix-vector dot product (no per-query normalization in the hot path).
* We index tools as a UNION of (name, description, context_terms) so a tool
  that registers `context_terms=["weather", "forecast", "rain"]` becomes
  reachable from "is it going to rain tomorrow" without needing the LLM.
* Args are NOT extracted by this layer. We dispatch with empty args and rely
  on each tool handler's own text-parsing logic (which Friday's handlers
  already use as a fallback). If a tool needs strict structured args, set its
  `embeddable=False` flag in capability_meta and the embedding router will
  skip it.
"""
from __future__ import annotations

import os
import threading
from typing import Iterable

import numpy as np

from core.logger import logger


# Lightweight sentence transformer — 22M params, ~90 MB on disk, 384-dim
# embeddings. Trades a few accuracy points vs. larger MPNet models for ~3x
# the throughput on CPU.
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Minimum cosine similarity to dispatch directly without consulting the LLM
# router. Tuned empirically — below ~0.55 we see too many false positives on
# short utterances ("yes", "stop", etc.).
DISPATCH_THRESHOLD = 0.62

# Tools we never want to route to via embeddings, regardless of score —
# usually because they need structured args that only the LLM can produce.
_DEFAULT_BLOCKLIST = frozenset({
    "llm_chat",                # the chat fallback owns the no-tool case
    "create_calendar_event",   # consent + timestamp parsing
    "set_reminder",            # time parsing
    "save_note",               # raw content capture
    "manage_file",             # multi-mode (create/write/append) — needs LLM
    "write_file",
    "set_voice_mode",          # mode arg required
    "set_volume",              # value arg required
})


class EmbeddingRouter:
    """Cosine-similarity router over registered tool descriptors."""

    def __init__(self, model_name: str = DEFAULT_MODEL,
                 dispatch_threshold: float = DISPATCH_THRESHOLD,
                 blocklist: Iterable[str] = _DEFAULT_BLOCKLIST):
        self.model_name = model_name
        self.dispatch_threshold = dispatch_threshold
        self.blocklist = frozenset(blocklist)
        self._model = None
        self._model_lock = threading.Lock()
        self._index_lock = threading.Lock()
        self._tool_names: list[str] = []
        self._tool_phrases: list[str] = []     # parallel to embedding rows
        self._phrase_to_tool: list[int] = []   # row index -> tool index
        self._embeddings: np.ndarray | None = None
        self._index_signature = ""             # hash of names; rebuild on change

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def build_index(self, tools_by_name: dict) -> None:
        """Rebuild the embedding index from the current tool registry.

        ``tools_by_name`` is the router's ``_tools_by_name`` mapping
        ({name: route_dict}). Each route_dict has a 'spec' with name +
        description + (optional) context_terms.
        """
        sig = ",".join(sorted(tools_by_name.keys()))
        if sig == self._index_signature and self._embeddings is not None:
            return

        with self._index_lock:
            if sig == self._index_signature and self._embeddings is not None:
                return

            tool_names: list[str] = []
            phrases: list[str] = []
            phrase_to_tool: list[int] = []

            for name, route in tools_by_name.items():
                if name in self.blocklist:
                    continue
                spec = route.get("spec", {}) if isinstance(route, dict) else {}
                meta = route.get("capability_meta") or {}
                if meta.get("embeddable") is False:
                    continue

                tool_idx = len(tool_names)
                tool_names.append(name)

                # Each tool gets several embedded "phrases" — the more, the
                # better the semantic surface area. Top-1 over all phrases
                # gives the tool's best match against the query.
                description = (spec.get("description") or "").strip()
                if description:
                    phrases.append(description[:280])
                    phrase_to_tool.append(tool_idx)

                # Tool name itself, lightly humanised
                phrases.append(name.replace("_", " "))
                phrase_to_tool.append(tool_idx)

                for term in (spec.get("context_terms") or []):
                    term = (term or "").strip()
                    if not term:
                        continue
                    phrases.append(term)
                    phrase_to_tool.append(tool_idx)

            if not phrases:
                self._tool_names = []
                self._tool_phrases = []
                self._phrase_to_tool = []
                self._embeddings = None
                self._index_signature = sig
                return

            model = self._get_model()
            if model is None:
                logger.warning("[embed-router] Sentence-transformer unavailable; "
                               "router disabled.")
                return

            try:
                embeddings = model.encode(
                    phrases,
                    normalize_embeddings=True,
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )
            except Exception as exc:
                logger.error("[embed-router] Failed to embed tool phrases: %s", exc)
                self._embeddings = None
                return

            self._tool_names = tool_names
            self._tool_phrases = phrases
            self._phrase_to_tool = phrase_to_tool
            self._embeddings = embeddings.astype(np.float32, copy=False)
            self._index_signature = sig
            logger.info("[embed-router] Indexed %d phrases across %d tools.",
                        len(phrases), len(tool_names))

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(self, text: str) -> dict | None:
        """Return {'tool': str, 'score': float} if a confident match exists."""
        if not text or not text.strip():
            return None
        if self._embeddings is None:
            return None

        model = self._get_model()
        if model is None:
            return None

        try:
            query_emb = model.encode(
                [text.strip()],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )[0]
        except Exception as exc:
            logger.warning("[embed-router] Encode failed for %r: %s", text, exc)
            return None

        # Cosine similarity = dot product when both sides L2-normalized.
        scores = self._embeddings @ query_emb.astype(np.float32, copy=False)
        # Aggregate per-tool: max over the tool's phrases (best of N).
        per_tool: dict[int, float] = {}
        for i, score in enumerate(scores):
            tool_idx = self._phrase_to_tool[i]
            cur = per_tool.get(tool_idx, -1.0)
            if score > cur:
                per_tool[tool_idx] = float(score)

        if not per_tool:
            return None
        best_tool_idx, best_score = max(per_tool.items(), key=lambda kv: kv[1])
        if best_score < self.dispatch_threshold:
            return None
        return {
            "tool": self._tool_names[best_tool_idx],
            "score": best_score,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_model(self):
        if self._model is not None:
            return self._model
        with self._model_lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            except ImportError:
                logger.warning("[embed-router] sentence-transformers not installed.")
                return None

            cache_dir = os.environ.get("FRIDAY_ST_CACHE") or os.path.join(
                os.path.expanduser("~"), ".cache", "huggingface"
            )
            try:
                self._model = SentenceTransformer(
                    self.model_name,
                    cache_folder=cache_dir,
                    device="cpu",  # tiny model — GPU launch overhead > inference
                )
                logger.info("[embed-router] Loaded %s.", self.model_name)
            except Exception as exc:
                logger.error("[embed-router] Could not load %s: %s",
                             self.model_name, exc)
                self._model = None
        return self._model

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        return {
            "indexed_tools": len(self._tool_names),
            "indexed_phrases": len(self._tool_phrases),
            "model": self.model_name,
            "loaded": self._model is not None,
            "threshold": self.dispatch_threshold,
        }
