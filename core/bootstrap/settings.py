"""Typed settings wrapper built on top of ConfigManager.

Exposes a flat, typed surface for the values that the core pipeline reads
most often, avoiding scattered config.get() calls with string keys and no
type guarantees. Backed by the existing YAML ConfigManager — no new file
format is introduced.

Phase 2 scope: read-only view. Writes still go through ConfigManager/app.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSettings:
    chat_path: str = "models/Qwen3.5-0.8B-Q4_K_M.gguf"
    tool_path: str = "models/Qwen3.5-4B-Q4_K_M.gguf"
    chat_n_ctx: int = 4096
    tool_n_ctx: int = 2048
    chat_temperature: float = 0.7
    tool_temperature: float = 0.1


@dataclass(frozen=True)
class RoutingSettings:
    policy: str = "selective_executor"
    tool_timeout_ms: int = 2500
    tool_max_tokens: int = 96
    tool_target_max_tokens: int = 64
    tool_top_p: float = 0.2
    tool_json_response: bool = True


@dataclass(frozen=True)
class ConversationSettings:
    listening_mode: str = "manual"
    online_permission_mode: str = "ask_first"
    wake_session_timeout_s: int = 12
    assistant_echo_window_s: float = 1.8
    delegate_multi_action_threshold: int = 2


@dataclass(frozen=True)
class FridaySettings:
    app_name: str = "FRIDAY"
    version: str = "0.1"
    models: ModelSettings = field(default_factory=ModelSettings)
    routing: RoutingSettings = field(default_factory=RoutingSettings)
    conversation: ConversationSettings = field(default_factory=ConversationSettings)

    @classmethod
    def from_config(cls, config) -> "FridaySettings":
        """Build a FridaySettings snapshot from a live ConfigManager instance."""
        def _get(key, default):
            if config and hasattr(config, "get"):
                val = config.get(key, default)
                return val if val is not None else default
            return default

        return cls(
            app_name=_get("app.name", "FRIDAY"),
            version=_get("app.version", "0.1"),
            models=ModelSettings(
                chat_path=_get("models.chat.path", "models/Qwen3.5-0.8B-Q4_K_M.gguf"),
                tool_path=_get("models.tool.path", "models/Qwen3.5-4B-Q4_K_M.gguf"),
                chat_n_ctx=int(_get("models.chat.n_ctx", 4096)),
                tool_n_ctx=int(_get("models.tool.n_ctx", 2048)),
                chat_temperature=float(_get("models.chat.temperature", 0.7)),
                tool_temperature=float(_get("models.tool.temperature", 0.1)),
            ),
            routing=RoutingSettings(
                policy=_get("routing.policy", "selective_executor"),
                tool_timeout_ms=int(_get("routing.tool_timeout_ms", 2500)),
                tool_max_tokens=int(_get("routing.tool_max_tokens", 96)),
                tool_target_max_tokens=int(_get("routing.tool_target_max_tokens", 64)),
                tool_top_p=float(_get("routing.tool_top_p", 0.2)),
                tool_json_response=bool(_get("routing.tool_json_response", True)),
            ),
            conversation=ConversationSettings(
                listening_mode=_get("conversation.listening_mode", "manual"),
                online_permission_mode=_get("conversation.online_permission_mode", "ask_first"),
                wake_session_timeout_s=int(_get("conversation.wake_session_timeout_s", 12)),
                assistant_echo_window_s=float(_get("conversation.assistant_echo_window_s", 1.8)),
                delegate_multi_action_threshold=int(_get("conversation.delegate_multi_action_threshold", 2)),
            ),
        )
