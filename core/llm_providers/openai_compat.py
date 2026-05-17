"""OpenAI-compatible provider (cloud fallback).

Works with OpenAI, Groq, NVIDIA NIM, and any OpenAI-compatible endpoint.
Credentials: OPENAI_API_KEY (or GROQ_API_KEY / NVIDIA_API_KEY).

Usage in config.yaml:
  cloud_fallback:
    enabled: true
    providers:
      - name: openai
        model: gpt-4o-mini
      - name: groq
        model: llama-3.1-8b-instant
        base_url: https://api.groq.com/openai/v1
        api_key_env: GROQ_API_KEY
"""
from __future__ import annotations

import os
import time

from core.logger import logger
from .base import LLMProvider, ProviderMessage, ProviderResponse


class OpenAICompatProvider(LLMProvider):
    name = "openai"
    model = "gpt-4o-mini"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        provider_name: str | None = None,
    ):
        self.model = model or self.__class__.model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url
        if provider_name:
            self.name = provider_name

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            from openai import OpenAI  # noqa: F401
            return True
        except ImportError:
            return False

    def chat_completion(
        self,
        messages: list[ProviderMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        from openai import OpenAI

        client_kwargs: dict = {"api_key": self._api_key, "timeout": self.timeout_s}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        client = OpenAI(**client_kwargs)
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                text = response.choices[0].message.content or ""
                usage = response.usage or type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()
                return ProviderResponse(
                    text=text,
                    provider=self.name,
                    model=self.model,
                    input_tokens=getattr(usage, "prompt_tokens", 0),
                    output_tokens=getattr(usage, "completion_tokens", 0),
                    ok=True,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning("[%s] attempt %d failed: %s", self.name, attempt + 1, exc)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)

        return ProviderResponse(
            text="", provider=self.name, model=self.model,
            ok=False, error=str(last_exc),
        )
