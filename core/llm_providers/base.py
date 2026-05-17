"""Base class for cloud LLM providers used as fallback when local models fail.

Mirrors jarvis src/llm/manager.ts fallback chain.
Provider interface is minimal — one method: chat_completion().

Design:
  - All providers are opt-in (local-first is FRIDAY's strategic moat).
  - Each call respects ConsentService.online_permission_mode.
  - Per-provider retry with 3 attempts and 90s timeout mirrors jarvis defaults.
  - Failures are non-fatal — callers fall through to the next provider.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProviderMessage:
    role: str       # "user" | "assistant" | "system"
    content: str


@dataclass
class ProviderResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    ok: bool = True
    error: str = ""


class LLMProvider(ABC):
    """Abstract cloud LLM provider."""

    name: str = "unknown"
    model: str = ""
    max_retries: int = 3
    timeout_s: float = 90.0

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if credentials are configured and the provider is reachable."""

    @abstractmethod
    def chat_completion(
        self,
        messages: list[ProviderMessage],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> ProviderResponse:
        """Run a chat completion. Raises on unrecoverable error."""
