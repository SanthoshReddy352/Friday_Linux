"""Gemma 270M intent router (A/B candidate vs. the current pipeline).

This is the experimental router the plan calls out as Research Task 4 —
a tiny, dedicated intent model running on CPU. Loaded only when the
benchmark script wants it; not wired into the live turn flow.

Design notes
------------
* The model is ``unsloth/gemma-3-270m-it`` quantized to Q4_K_M (~240 MB
  on disk). At 270M parameters it loads in ~150 ms and answers a short
  prompt in ~120–250 ms on i5-12th gen CPU — fast enough that *if* it
  improves accuracy over the existing fuzzy+regex+embed router, the
  voice-first latency budget can absorb the cost.
* The prompt is deliberately short. Long context blows up the
  generation budget on a 270M and harms accuracy. We surface up to ~30
  registered tools with one-line descriptions and a single example
  phrasing each.
* The model is asked to return *only* JSON; we parse the first
  ``{...}`` substring with ``json.loads`` and reject anything else.
  Refusing partial / malformed output is a feature — better to fall
  back to the deterministic router than route on garbage.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass

from core.logger import logger


DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "gemma-3-270m-it-Q4_K_M.gguf",
)


@dataclass
class GemmaRouterDecision:
    tool: str | None
    args: dict
    latency_ms: float
    raw_output: str
    error: str = ""


class GemmaIntentRouter:
    """Lazily-loaded Gemma 270M intent classifier.

    Two prompt styles are supported:

    * ``mode="chat"`` (default) — system + user messages asking for a
      one-line JSON answer. Works with the plain ``gemma-3-270m-it``
      base and with any chat-tuned GGUF (Qwen, etc.).
    * ``mode="function"`` — emits Google's Function-Gemma tool-call
      format: tools serialized as a numbered list in the system
      message, output parsed from ``<start_function_call> … <end_function_call>``
      blocks (the model's native tool-call sequence).
    """

    def __init__(
        self,
        model_path: str | None = None,
        *,
        n_ctx: int = 2048,
        n_threads: int | None = None,
        max_tokens: int = 16,   # tool name is ≤6 tokens; cap kills latency outliers
        temperature: float = 0.0,
        mode: str = "chat",
    ):
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.n_ctx = int(n_ctx)
        self.n_threads = n_threads
        self.max_tokens = int(max_tokens)
        self.temperature = float(temperature)
        self.mode = mode if mode in ("chat", "function") else "chat"
        self._llm = None
        self._lock = threading.Lock()
        # Stats for benchmark reports — caller decides whether to read them.
        self.last_load_ms: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return os.path.exists(self.model_path)

    def load(self) -> bool:
        """Load the GGUF model (idempotent). Returns True on success."""
        if self._llm is not None:
            return True
        if not self.is_available():
            logger.warning("[gemma-router] model missing at %s", self.model_path)
            return False
        with self._lock:
            if self._llm is not None:
                return True
            try:
                from llama_cpp import Llama  # noqa: PLC0415
            except ImportError as exc:
                logger.error("[gemma-router] llama-cpp-python not installed: %s", exc)
                return False
            t0 = time.perf_counter()
            kwargs = {
                "model_path": self.model_path,
                "n_ctx": self.n_ctx,
                "verbose": False,
            }
            if self.n_threads:
                kwargs["n_threads"] = int(self.n_threads)
            try:
                self._llm = Llama(**kwargs)
            except Exception as exc:
                logger.error("[gemma-router] load failed: %s", exc)
                return False
            self.last_load_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                "[gemma-router] loaded %s in %.0f ms",
                os.path.basename(self.model_path), self.last_load_ms,
            )
        return True

    def unload(self) -> None:
        with self._lock:
            self._llm = None

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(self, utterance: str, tools: list[dict]) -> GemmaRouterDecision:
        """Classify ``utterance`` against the supplied ``tools``.

        The prompt is built as raw bytes that mirror what the LoRA was
        trained on (``scripts/format_for_finetune.py``) — same system
        text, same tool-list format, same Gemma chat-template markers.
        We then call ``create_completion`` (NOT ``create_chat_completion``)
        so llama.cpp doesn't re-apply its own chat template on top. Any
        drift between training and inference prompts collapses the
        LoRA's accuracy to near-base, so do not edit these strings
        without also retraining.
        """
        text = (utterance or "").strip()
        if not text:
            return GemmaRouterDecision(tool=None, args={}, latency_ms=0.0, raw_output="", error="empty input")
        if not self.load():
            return GemmaRouterDecision(tool=None, args={}, latency_ms=0.0, raw_output="", error="model unavailable")

        if self.mode == "function":
            prompt = self._build_function_prompt(text, tools)
        else:
            prompt = self._build_chat_prompt(text, tools)

        t0 = time.perf_counter()
        try:
            with self._lock:
                response = self._llm.create_completion(  # type: ignore[union-attr]
                    prompt,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=1.0,
                    stop=["<end_of_turn>", "<|endoftext|>"],
                )
        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return GemmaRouterDecision(
                tool=None, args={}, latency_ms=elapsed,
                raw_output="", error=f"inference failed: {exc}",
            )
        elapsed = (time.perf_counter() - t0) * 1000.0

        raw = (response.get("choices", [{}])[0].get("text") or "").strip()

        if self.mode == "function":
            parsed = self._parse_function_call(raw)
            tool = parsed.get("tool")
            args = parsed.get("args") or {}
            err = "" if parsed else "unparseable model output"
        else:
            # Chat mode — output is the bare tool name on its own line.
            tool = raw.splitlines()[0].strip() if raw else None
            if tool and tool.lower() in {"null", "none", ""}:
                tool = None
            args = {}
            err = "" if tool else "empty model output"

        return GemmaRouterDecision(
            tool=tool, args=args, latency_ms=elapsed,
            raw_output=raw, error=err,
        )

    # ------------------------------------------------------------------
    # Prompts — MUST match scripts/format_for_finetune.py byte-for-byte.
    # ------------------------------------------------------------------

    # Match envelope tokens emitted by the FN-Gemma tune.
    _FUNCTION_CALL_RE = re.compile(
        r"<start_function_call>(.*?)<end_function_call>", re.DOTALL,
    )

    def _build_chat_prompt(self, utterance: str, tools: list[dict]) -> str:
        """Standard Gemma intent-classifier prompt.

        Output target during training was the bare tool name (e.g.
        ``get_time``) so we cut the model off at the first ``<end_of_turn>``.
        """
        tool_list = ", ".join(
            (t.get("name") or "").strip() for t in tools if t.get("name")
        )
        user_content = (
            "You are an intent classifier. Reply with only the tool name.\n\n"
            f"Tools: {tool_list}\n\n"
            f"Utterance: {utterance.strip()}"
        )
        # No literal <bos> — llama.cpp auto-prepends it (avoids the
        # "duplicate leading <bos>" warning and the small accuracy hit
        # that comes with double-BOS).
        return (
            f"<start_of_turn>user\n{user_content}<end_of_turn>\n"
            "<start_of_turn>model\n"
        )

    def _build_function_prompt(self, utterance: str, tools: list[dict]) -> str:
        """Function-Gemma developer-role prompt + JSON tool schema.

        Output target during training was the literal envelope:
        ``<start_function_call>{"tool":"X","args":{}}<end_function_call>``.
        """
        schemas = [{
            "name": t["name"],
            "description": (t.get("description") or "")[:120],
            "parameters": t.get("parameters") or {},
        } for t in tools if t.get("name")]
        schema_json = json.dumps(schemas, separators=(",", ":"))
        developer = (
            "You are a function-calling assistant. Choose at most one tool "
            'from this list. If none fit, return {"tool": null}.\n\n'
            f"{schema_json}"
        )
        # No literal <bos> — llama.cpp auto-prepends it.
        return (
            f"<start_of_turn>developer\n{developer}<end_of_turn>\n"
            f"<start_of_turn>user\n{utterance.strip()}<end_of_turn>\n"
            "<start_of_turn>model\n"
        )

    def _parse_function_call(self, raw: str) -> dict:
        if not raw:
            return {}
        # Try the envelope first; fall back to bare JSON parsing.
        match = self._FUNCTION_CALL_RE.search(raw)
        if match:
            inner = match.group(1).strip()
            # Strip the leading "call" keyword that Function Gemma
            # sometimes prepends (``call{"tool": ...}``).
            inner = re.sub(r"^call\b", "", inner).strip()
            parsed = self._parse_response(inner)
            if parsed:
                return parsed
        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # Optional: normalize a returned tool name back to a registered one
    # ------------------------------------------------------------------

    @staticmethod
    def normalize_tool_name(predicted: str | None, allowed: list[str]) -> str | None:
        """Map a model-predicted name (which may be a shortened form like
        "time" or "weather") to an exact registered tool name.

        Strategy: case-insensitive exact match → suffix match
        (``time`` → ``get_time``) → substring match. Returns the original
        ``predicted`` value unchanged when no allowed tool exists, so
        callers can still see what the model said.
        """
        if not predicted:
            return predicted
        lowered = predicted.strip().lower()
        if not lowered:
            return predicted
        allowed_lower = {a.lower(): a for a in allowed}
        if lowered in allowed_lower:
            return allowed_lower[lowered]
        # suffix: predicted="time" → "get_time"
        for low, real in allowed_lower.items():
            if low.endswith("_" + lowered) or low == "get_" + lowered:
                return real
        # substring
        for low, real in allowed_lower.items():
            if lowered in low.split("_"):
                return real
        return predicted

    # Matches balanced-ish JSON objects of the form {...} so nested args
    # like ``{"tool": "x", "args": {"k": "v"}}`` aren't truncated at the
    # first inner closing brace.
    _JSON_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
    _JSON_OBJECT_RE = re.compile(r"\{(?:[^{}]|\{[^{}]*\})*\}", re.DOTALL)

    def _parse_response(self, raw: str) -> dict:
        """Pull the first JSON object out of the model's output.

        Handles three observed formats from the 270M:
          1. Bare JSON: ``{"tool": "x"}``
          2. Markdown-fenced JSON: ```` ```json\n{...}\n``` ````
          3. Pseudo-XML wrapper: ``<response>{...}</response>``
        """
        if not raw:
            return {}
        cleaned = raw.replace("<response>", "").replace("</response>", "").strip()
        # Unwrap markdown fences if present.
        fence_match = self._JSON_FENCE_RE.search(cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        candidates: list[str] = [cleaned, *self._JSON_OBJECT_RE.findall(cleaned)]
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            tool = payload.get("tool")
            if isinstance(tool, str) and tool.lower() in {"null", "none", ""}:
                tool = None
            args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
            return {"tool": tool, "args": args}
        return {}
