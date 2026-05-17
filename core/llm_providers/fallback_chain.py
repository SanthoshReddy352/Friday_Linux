"""FallbackChain — tries providers in order until one succeeds.

Mirrors jarvis src/llm/manager.ts LLMManager fallback logic.
Must be used with ConsentService to ensure online calls are approved.

Config (config.yaml):
  cloud_fallback:
    enabled: false        # opt-in; off by default to preserve local-first
    providers:
      - name: anthropic
        model: claude-haiku-4-5-20251001
      - name: openai
        model: gpt-4o-mini
      - name: groq
        model: llama-3.1-8b-instant
        base_url: https://api.groq.com/openai/v1
        api_key_env: GROQ_API_KEY

Usage:
    chain = FallbackChain.from_config(config)
    if chain.enabled:
        response = chain.chat_completion(messages)
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from core.logger import logger
from .base import LLMProvider, ProviderMessage, ProviderResponse
from .anthropic_provider import AnthropicProvider
from .openai_compat import OpenAICompatProvider

if TYPE_CHECKING:
    pass


class FallbackChain:
    def __init__(self, providers: list[LLMProvider], enabled: bool = False):
        self._providers = providers
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._providers)

    @classmethod
    def from_config(cls, config) -> "FallbackChain":
        if config is None:
            return cls([], enabled=False)

        def _get(key, default=None):
            if hasattr(config, "get"):
                return config.get(key, default)
            return default

        enabled = bool(_get("cloud_fallback.enabled", False))
        if not enabled:
            return cls([], enabled=False)

        provider_cfgs = _get("cloud_fallback.providers", [])
        providers: list[LLMProvider] = []
        for pcfg in (provider_cfgs or []):
            name = (pcfg.get("name") or "").lower()
            model = pcfg.get("model") or None
            api_key_env = pcfg.get("api_key_env") or None
            api_key = os.environ.get(api_key_env, "") if api_key_env else None
            base_url = pcfg.get("base_url") or None

            if name == "anthropic":
                p = AnthropicProvider(model=model, api_key=api_key)
            elif name in ("openai", "groq", "nvidia", "openrouter"):
                p = OpenAICompatProvider(
                    model=model, api_key=api_key, base_url=base_url, provider_name=name
                )
            else:
                logger.warning("[FallbackChain] unknown provider: %s", name)
                continue
            providers.append(p)

        logger.info(
            "[FallbackChain] loaded %d provider(s): %s",
            len(providers),
            [p.name for p in providers],
        )
        return cls(providers, enabled=True)

    def chat_completion(
        self,
        messages: list[ProviderMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> ProviderResponse | None:
        """Try each provider in order. Returns first successful response or None."""
        if not self.enabled:
            return None
        for provider in self._providers:
            if not provider.is_available():
                logger.debug("[FallbackChain] %s not available, skipping", provider.name)
                continue
            try:
                response = provider.chat_completion(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
                if response.ok:
                    logger.info(
                        "[FallbackChain] %s responded (%d tokens out)",
                        provider.name, response.output_tokens,
                    )
                    return response
                logger.warning("[FallbackChain] %s failed: %s", provider.name, response.error)
            except Exception as exc:
                logger.warning("[FallbackChain] %s raised: %s", provider.name, exc)
        return None

    def is_any_available(self) -> bool:
        return self.enabled and any(p.is_available() for p in self._providers)
