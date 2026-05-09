"""ModelRouter — LLM-based tool selection.

Phase 5: Extracted from CommandRouter._run_tool_model_request.
Used by CapabilityBroker when deterministic routing is insufficient
and a tool-oriented LLM should resolve the ambiguity.
"""
from __future__ import annotations

import difflib
import json
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any

from core.logger import logger


class ModelRouter:
    """Wraps tool-LLM inference for capability selection.

    Stateless w.r.t. application — the model manager is injected so this
    can be tested without a live FridayApp. CapabilityBroker holds the
    only reference and calls select() when deterministic routing scores
    below the confidence threshold.
    """

    def __init__(
        self,
        model_manager,
        *,
        timeout_ms: int = 8000,
        max_tokens: int = 96,
        target_max_tokens: int = 64,
        top_p: float = 0.2,
        json_response: bool = True,
    ):
        self._model_manager = model_manager
        self._timeout_ms = timeout_ms
        self._max_tokens = max_tokens
        self._target_max_tokens = target_max_tokens
        self._top_p = top_p
        self._json_response = json_response
        self._tool_llm = None
        self._lock = threading.Lock()
        self._failed = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(
        self,
        text: str,
        candidates: list[dict],
        *,
        target_tool: str | None = None,
        dialog_state=None,
        assistant_context=None,
    ) -> dict | None:
        """Run LLM inference to select the best tool for *text*.

        Args:
            text: cleaned user utterance.
            candidates: list of {"name", "description", "parameters"} dicts.
            target_tool: if known, constrain inference to this tool for arg extraction.
            dialog_state: optional, passed to prompt builder for context.
            assistant_context: optional, used to build the prompt via its
                               build_router_prompt() method.

        Returns:
            {"name": str, "args": dict} on success, or None if inference
            fails, times out, or returns an unknown tool name.
        """
        llm = self._get_tool_llm()
        if llm is None:
            return None

        prompt = self._build_prompt(text, candidates, target_tool=target_tool, dialog_state=dialog_state, assistant_context=assistant_context)
        output_tokens = self._target_max_tokens if target_tool else self._max_tokens

        def _call():
            messages = [{"role": "user", "content": prompt}]
            if hasattr(llm, "create_chat_completion"):
                kwargs: dict[str, Any] = {
                    "messages": messages,
                    "max_tokens": output_tokens,
                    "temperature": self._model_manager.profile("tool").temperature,
                    "top_p": self._top_p,
                }
                if self._json_response:
                    kwargs["response_format"] = {"type": "json_object"}
                try:
                    return llm.create_chat_completion(**kwargs)
                except TypeError:
                    kwargs.pop("response_format", None)
                    return llm.create_chat_completion(**kwargs)
            # Legacy completion API
            return {
                "choices": [{
                    "message": {
                        "content": llm(
                            prompt,
                            max_tokens=output_tokens,
                            temperature=self._model_manager.profile("tool").temperature,
                        )["choices"][0]["text"]
                    }
                }]
            }

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            try:
                raw = future.result(timeout=max(1, self._timeout_ms) / 1000)
            except FutureTimeout:
                logger.warning("[model_router] tool-LLM timed out after %dms", self._timeout_ms)
                return None
            except Exception as exc:
                logger.warning("[model_router] tool-LLM error: %s", exc)
                return None

        return self._parse(raw, candidates)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_tool_llm(self):
        if self._tool_llm is not None:
            return self._tool_llm
        if self._failed:
            return None
        # Don't block the turn waiting for model loading from disk.
        if not self._model_manager.is_loaded("tool"):
            return None
        with self._lock:
            if self._tool_llm is not None:
                return self._tool_llm
            model = self._model_manager.get_tool_model()
            if model is None:
                self._failed = True
                return None
            self._tool_llm = model
        return self._tool_llm

    def _build_prompt(self, text, candidates, *, target_tool=None, dialog_state=None, assistant_context=None):
        if assistant_context and hasattr(assistant_context, "build_router_prompt"):
            return assistant_context.build_router_prompt(
                text,
                candidates,
                dialog_state=dialog_state,
                target_tool=target_tool,
            )
        tools_json = json.dumps(
            [{"name": c.get("name"), "description": c.get("description"), "parameters": c.get("parameters", {})} for c in candidates],
            separators=(",", ":"),
        )
        constraint = f" Use tool '{target_tool}'." if target_tool else ""
        return (
            f"You are a tool selector. Given the user message and available tools, "
            f"output a JSON object with 'name' (string) and 'args' (object).{constraint}\n\n"
            f"Tools: {tools_json}\n\nUser: {text}\n\nJSON:"
        )

    def _parse(self, raw_result: dict, candidates: list[dict]) -> dict | None:
        try:
            content = raw_result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None

        content = (content or "").strip()
        start = content.find("{")
        end = content.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(content[start:end])
        except json.JSONDecodeError:
            return None

        name = parsed.get("name") or parsed.get("tool") or parsed.get("function")
        if not name:
            return None

        valid_names = {c.get("name") for c in candidates if c.get("name")}
        if name not in valid_names:
            matches = difflib.get_close_matches(str(name), valid_names, n=1, cutoff=0.6)
            if not matches:
                logger.debug("[model_router] unknown tool '%s' from LLM", name)
                return None
            name = matches[0]

        args = parsed.get("args") or parsed.get("parameters") or parsed.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}

        return {"name": name, "args": args}
