from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.capability_broker import CapabilityBroker
from core.delegation import DelegationRequest
from core.tool_execution import OrderedToolExecutor


@dataclass
class TurnPlan:
    mode: str
    tool_calls: list[dict] = field(default_factory=list)
    delegation: dict = field(default_factory=dict)
    online_required: bool = False
    user_ack: str = ""
    final_response_style: str = ""
    reply: str = ""


class ConversationAgent:
    EXPLICIT_ONLINE_PATTERNS = (
        r"\bsearch (?:the )?(?:web|internet|online)\b",
        r"\blook (?:it|this|that) up\b",
        r"\bgo online\b",
        r"\bcheck (?:online|the web|the internet)\b",
        r"\bbrowse\b",
        r"\bopen (?:youtube|youtube music|website|browser)\b",
        r"\bplay\b.+\b(?:on|in)\s+youtube(?:\s+music)?\b",
    )

    POSITIVE_CONFIRMATION_PATTERNS = (
        r"\byes\b",
        r"\byeah\b",
        r"\byep\b",
        r"\bsure\b",
        r"\bok(?:ay)?\b",
        r"\bdo it\b",
        r"\bgo ahead\b",
        r"\bgo online\b",
    )

    NEGATIVE_CONFIRMATION_PATTERNS = (
        r"\bno\b",
        r"\bnope\b",
        r"\bcancel\b",
        r"\bstop\b",
        r"\bstay offline\b",
        r"\bdon't\b",
        r"\bdo not\b",
    )

    CURRENT_INFO_PATTERNS = (
        r"\bweather\b",
        r"\bnews\b",
        r"\blatest\b",
        r"\bcurrent\b",
        r"\btoday'?s\b",
        r"\bprice of\b",
        r"\bwhat'?s happening\b",
    )

    def __init__(self, app):
        self.app = app
        if not getattr(app, "capability_broker", None):
            app.capability_broker = CapabilityBroker(app)
        if not getattr(app, "ordered_tool_executor", None):
            app.ordered_tool_executor = OrderedToolExecutor(app)

    def process_turn(self, text: str, source: str = "user", turn=None):
        plan, context_bundle = self.build_tool_plan(text, source=source, turn=turn)
        response = self.execute_tool_plan(plan, text, turn=turn)
        self.curate_memory(text, response, context_bundle)
        return response

    def build_tool_plan(self, text: str, source: str = "user", turn=None):
        session_id = self.app.session_id
        context_bundle = self.app.memory_broker.build_context_bundle(text, session_id)
        style_result = self.app.delegation_manager.delegate(
            DelegationRequest(
                agent_type="persona_stylist",
                task=text,
                context_bundle=context_bundle,
                timeout_ms=500,
            )
        )
        plan = self.app.capability_broker.build_plan(
            text,
            turn_id=getattr(turn, "turn_id", "") or "",
            source=source,
            context_bundle=context_bundle,
            style_hint=style_result.summary,
        )
        return plan, context_bundle

    def execute_tool_plan(self, plan, text: str, turn=None):
        return self.app.ordered_tool_executor.execute(plan, text, turn=turn)

    def curate_memory(self, text: str, response: str, context_bundle: dict | None = None):
        context_bundle = context_bundle or {}
        session_id = self.app.session_id
        persona = context_bundle.get("persona") or {}
        self.app.delegation_manager.memory_curator.curate(
            session_id=session_id,
            user_text=text,
            assistant_text=response,
            persona_id=persona.get("persona_id", ""),
        )

    def plan_turn(self, text: str, source: str = "user", context_bundle: dict | None = None, style_hint: str = ""):
        tool_plan = self.app.capability_broker.build_plan(
            text,
            turn_id="",
            source=source,
            context_bundle=context_bundle or {},
            style_hint=style_hint,
        )
        return self._legacy_turn_plan(tool_plan)

    def _legacy_turn_plan(self, tool_plan):
        if tool_plan.mode in {"tool", "chat"}:
            return TurnPlan(
                mode="local_tool",
                tool_calls=[
                    {"name": step.capability_name, "args": dict(step.args), "text": step.raw_text}
                    for step in tool_plan.steps
                ],
                user_ack=tool_plan.ack,
                final_response_style=tool_plan.final_style,
            )
        if tool_plan.mode == "planner":
            return TurnPlan(
                mode="delegate",
                delegation={"agent_type": "planner", "task": ""},
                user_ack=tool_plan.ack,
                final_response_style=tool_plan.final_style,
            )
        return TurnPlan(
            mode="reply" if tool_plan.mode == "reply" else "clarify",
            reply=tool_plan.reply,
            online_required=tool_plan.requires_confirmation,
            user_ack=tool_plan.ack,
            final_response_style=tool_plan.final_style,
        )

    def _execute_plan(self, plan: TurnPlan, text: str):
        if plan.user_ack:
            self.app.event_bus.publish("voice_response", plan.user_ack)

        if plan.mode == "reply" or plan.mode == "clarify":
            self.app.router._set_routing_decision("deterministic", tool_name="", args={})
            return plan.reply

        if plan.mode == "delegate":
            request = DelegationRequest(
                agent_type=plan.delegation.get("agent_type", "planner"),
                task=plan.delegation.get("task", text),
                context_bundle=dict(plan.delegation.get("context_bundle") or {}),
                timeout_ms=int(plan.delegation.get("timeout_ms", 3000)),
            )
            result = self.app.delegation_manager.delegate(request)
            self.app.router._set_routing_decision("workflow", tool_name=request.agent_type, args=result.structured_output)
            return result.summary

        if plan.mode == "local_tool":
            responses = []
            for call in plan.tool_calls:
                name = call["name"]
                args = dict(call.get("args") or {})
                raw_text = call.get("text", text)
                result = self.app.capability_executor.execute(name, raw_text, args)
                if result.ok:
                    self.app.router._remember_tool_use(name, args)
                    self.app.router._set_routing_decision("deterministic", tool_name=name, args=args)
                    responses.append(self.app.router._finalize_response(result.output))
                    self.app.context_store.clear_pending_online(self.app.session_id)
                else:
                    responses.append(f"Error running command: {result.error}")
            return "\n".join(str(item) for item in responses if item)

        return "I need a bit more detail before I can do that."

    def _build_online_proposal(self, tool_name: str, args: dict, text: str, descriptor, style_hint: str):
        self.app.context_store.set_pending_online(
            self.app.session_id,
            {"tool_name": tool_name, "args": dict(args or {}), "text": text, "ack": ""},
        )
        noun = descriptor.description or tool_name.replace("_", " ")
        return TurnPlan(
            mode="clarify",
            reply=f"I can handle that with an online skill for {noun.lower()}. Say yes if you want me to go online for this request.",
            online_required=True,
            final_response_style=style_hint,
        )

    def _is_explicit_online_request(self, text: str):
        lowered = (text or "").strip().lower()
        return any(re.search(pattern, lowered) for pattern in self.EXPLICIT_ONLINE_PATTERNS)

    def _looks_like_current_info_request(self, text: str):
        lowered = (text or "").strip().lower()
        return any(re.search(pattern, lowered) for pattern in self.CURRENT_INFO_PATTERNS)

    def _requires_online_confirmation(self, tool_name: str, descriptor, text: str):
        if descriptor.connectivity != "online":
            return False
        permission_mode = self._config_get("conversation.online_permission_mode", descriptor.permission_mode)
        if descriptor.permission_mode == "always_ok":
            return False
        if tool_name in {"play_youtube", "play_youtube_music"}:
            return False
        if self._is_explicit_online_request(text):
            return False
        return permission_mode == "ask_first"

    def _resolve_pending_online_permission(self, text: str):
        normalized = (text or "").strip().lower().strip(" .!?")
        if not normalized:
            return False
        if any(re.search(pattern, normalized) for pattern in self.NEGATIVE_CONFIRMATION_PATTERNS):
            return False
        return any(re.search(pattern, normalized) for pattern in self.POSITIVE_CONFIRMATION_PATTERNS)

    def _is_negative_confirmation(self, text: str):
        normalized = (text or "").strip().lower().strip(" .!?")
        return any(re.search(pattern, normalized) for pattern in self.NEGATIVE_CONFIRMATION_PATTERNS)

    def _config_get(self, key, default=None):
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            return config.get(key, default)
        return default
