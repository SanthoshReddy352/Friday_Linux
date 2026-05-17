"""Anthropic Claude provider (cloud fallback).

Requires: pip install anthropic
Credentials: ANTHROPIC_API_KEY env var.

Respects FRIDAY's local-first stance — only used when:
  1. Local model fails or is unavailable.
  2. cloud_fallback.enabled = true in config.yaml.
  3. ConsentService approves the online request.
"""
from __future__ import annotations

import os
import time

from core.logger import logger
from .base import LLMProvider, ProviderMessage, ProviderResponse


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    model = "claude-haiku-4-5-20251001"  # cheapest Claude model as default fallback

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or self.__class__.model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def chat_completion(
        self,
        messages: list[ProviderMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        import anthropic

        system_msgs = [m for m in messages if m.role == "system"]
        conv_msgs = [m for m in messages if m.role != "system"]
        system_text = "\n".join(m.content for m in system_msgs) or None
        api_messages = [{"role": m.role, "content": m.content} for m in conv_msgs]

        client = anthropic.Anthropic(api_key=self._api_key)
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_text or anthropic.NOT_GIVEN,
                    messages=api_messages,
                    timeout=self.timeout_s,
                )
                text = response.content[0].text if response.content else ""
                return ProviderResponse(
                    text=text,
                    provider=self.name,
                    model=self.model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    ok=True,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning("[anthropic] attempt %d failed: %s", attempt + 1, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)

        return ProviderResponse(
            text="",
            provider=self.name,
            model=self.model,
            ok=False,
            error=str(last_exc),
        )
