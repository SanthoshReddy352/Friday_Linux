"""Routing state — extracted from CommandRouter.

Holds the mutable per-request routing decision so that tool_execution.py,
conversation_agent.py, and the GUI can read it without importing the full
CommandRouter monolith.

Phase 1: CommandRouter delegates _set_routing_decision / _voice_already_spoken
management here. Callers switch from `app.router._set_routing_decision(...)` to
`app.routing_state.set_decision(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RoutingDecision:
    source: str
    tool_name: str = ""
    args: dict = field(default_factory=dict)
    spoken_ack: str = ""


class RoutingState:
    """Mutable state produced by a single routing cycle.

    Instantiated once on FridayApp and shared with CommandRouter (which
    writes to it) and OrderedToolExecutor / ConversationAgent (which read
    from it and write routing decisions after tool execution).
    """

    def __init__(self):
        self._idle = RoutingDecision(source="idle", args={})
        self.last_decision: RoutingDecision = self._idle
        self.current_route_source: str = "idle"
        self.current_model_lane: str = "idle"
        self.voice_already_spoken: bool = False

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------

    def set_decision(self, source: str, tool_name: str = "", args: dict | None = None, spoken_ack: str = "") -> None:
        self.current_route_source = source
        if source == "gemma_chat":
            self.current_model_lane = "chat"
        elif source in ("qwen_tool", "fallback_clarify"):
            self.current_model_lane = "tool"
        else:
            self.current_model_lane = "deterministic"
        self.last_decision = RoutingDecision(
            source=source,
            tool_name=tool_name or "",
            args=dict(args or {}),
            spoken_ack=spoken_ack or "",
        )

    def reset_for_turn(self) -> None:
        self.last_decision = self._idle
        self.current_route_source = "idle"
        self.current_model_lane = "idle"
        self.voice_already_spoken = False

    def mark_voice_spoken(self) -> None:
        self.voice_already_spoken = True

    def clear_voice_spoken(self) -> None:
        self.voice_already_spoken = False

    # ------------------------------------------------------------------
    # Convenience read
    # ------------------------------------------------------------------

    @property
    def last_tool_name(self) -> str:
        return self.last_decision.tool_name
