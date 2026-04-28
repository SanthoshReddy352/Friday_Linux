from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ToolStep:
    capability_name: str
    args: dict = field(default_factory=dict)
    raw_text: str = ""
    side_effect_level: str = "read"
    connectivity: str = "local"
    timeout_ms: int = 8000
    parallel_safe: bool = False


@dataclass
class ToolPlan:
    turn_id: str
    mode: str
    ack: str = ""
    steps: list[ToolStep] = field(default_factory=list)
    requires_confirmation: bool = False
    estimated_latency: str = "interactive"
    final_style: str = ""
    reply: str = ""
    delegation: dict = field(default_factory=dict)


class CapabilityBroker:
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
    TOOL_ORIENTED_STARTERS = (
        "open", "launch", "start", "bring up", "run", "execute", "take", "capture",
        "find", "search", "locate", "set", "save", "read", "show", "list", "check",
        "summarize", "summary", "remind", "enable", "disable", "turn", "mute",
        "unmute", "increase", "decrease", "lower", "raise", "pause", "stop", "play",
    )

    def __init__(self, app):
        self.app = app

    def build_plan(self, text: str, turn_id: str, source: str = "user", context_bundle: dict | None = None, style_hint: str = ""):
        cleaned_text = self._clean(text, source=source)
        route_start = self._now()

        pending_plan = self._plan_pending_online(cleaned_text, turn_id, style_hint)
        if pending_plan:
            self._record_route_duration(route_start)
            return pending_plan

        workflow_result = self.app.router.continue_active_workflow(cleaned_text)
        if workflow_result is not None:
            self._record_route_duration(route_start)
            return ToolPlan(turn_id=turn_id, mode="reply", reply=workflow_result, final_style=style_hint)

        action_plan = self.app.router.plan_actions(cleaned_text)
        if action_plan:
            steps = [self._action_to_step(action, cleaned_text) for action in action_plan]
            online = self._first_online_confirmation_needed(steps, cleaned_text)
            if online:
                self._record_route_duration(route_start)
                return self._build_online_proposal(online, cleaned_text, turn_id, style_hint)
            self._record_route_duration(route_start)
            return ToolPlan(
                turn_id=turn_id,
                mode="tool",
                steps=steps,
                ack=self._ack_for_steps(steps),
                estimated_latency=self._estimated_latency(steps),
                final_style=style_hint,
            )

        best_route = self.app.router.find_best_route(cleaned_text, min_score=80)
        if best_route and best_route["spec"]["name"] != "llm_chat":
            step = self._route_to_step(best_route, cleaned_text, {})
            if self._requires_online_confirmation(step.capability_name, self.app.capability_registry.get_descriptor(step.capability_name), cleaned_text):
                self._record_route_duration(route_start)
                return self._build_online_proposal(step, cleaned_text, turn_id, style_hint)
            self._record_route_duration(route_start)
            return ToolPlan(
                turn_id=turn_id,
                mode="tool",
                steps=[step],
                ack=self._ack_for_steps([step]),
                estimated_latency=self._estimated_latency([step]),
                final_style=style_hint,
            )

        if self._looks_like_current_info_request(cleaned_text):
            online_capabilities = self.app.capability_registry.list_capabilities(connectivity="online")
            if online_capabilities and not self._is_explicit_online_request(cleaned_text):
                self.app.context_store.set_pending_online(
                    self.app.session_id,
                    {"tool_name": "", "args": {}, "text": cleaned_text, "ack": ""},
                )
                self._record_route_duration(route_start)
                return ToolPlan(
                    turn_id=turn_id,
                    mode="clarify",
                    reply="I can check that with an online skill if you want. Say yes and I'll go online for this request.",
                    requires_confirmation=True,
                    final_style=style_hint,
                )

        if self._should_use_planner(cleaned_text):
            self._record_route_duration(route_start)
            return ToolPlan(
                turn_id=turn_id,
                mode="planner",
                ack="Let me figure out the right tool for that.",
                estimated_latency="generative",
                final_style=style_hint,
            )

        if self.app.capability_registry.has_capability("llm_chat"):
            descriptor = self.app.capability_registry.get_descriptor("llm_chat")
            self._record_route_duration(route_start)
            return ToolPlan(
                turn_id=turn_id,
                mode="chat",
                ack=self._chat_ack(cleaned_text),
                steps=[ToolStep(
                    capability_name="llm_chat",
                    args={"query": cleaned_text},
                    raw_text=cleaned_text,
                    side_effect_level=getattr(descriptor, "side_effect_level", "read"),
                    connectivity=getattr(descriptor, "connectivity", "local"),
                    timeout_ms=self._tool_timeout_ms(),
                )],
                estimated_latency="generative",
                final_style=style_hint,
            )

        self._record_route_duration(route_start)
        return ToolPlan(turn_id=turn_id, mode="clarify", reply="I need a bit more detail before I can do that.", final_style=style_hint)

    def _plan_pending_online(self, cleaned_text: str, turn_id: str, style_hint: str):
        session_state = self.app.context_store.get_session_state(self.app.session_id) or {}
        pending = dict(session_state.get("pending_online") or {})
        if self._is_negative_confirmation(cleaned_text) and pending:
            self.app.context_store.log_online_permission(self.app.session_id, pending.get("tool_name", ""), "declined", reason="user_confirmation")
            self.app.context_store.clear_pending_online(self.app.session_id)
            return ToolPlan(
                turn_id=turn_id,
                mode="clarify",
                reply="Okay. I'll stay offline unless you want me to use an online skill.",
                final_style=style_hint,
            )
        if not self._is_positive_confirmation(cleaned_text):
            return None
        if not pending:
            return None
        self.app.context_store.log_online_permission(self.app.session_id, pending.get("tool_name", ""), "approved", reason="user_confirmation")
        tool_name = pending.get("tool_name", "")
        descriptor = self.app.capability_registry.get_descriptor(tool_name)
        if descriptor is not None:
            return ToolPlan(
                turn_id=turn_id,
                mode="tool",
                ack=pending.get("ack") or "I'll check that now.",
                steps=[ToolStep(
                    capability_name=tool_name,
                    args=dict(pending.get("args") or {}),
                    raw_text=pending.get("text", cleaned_text),
                    side_effect_level=descriptor.side_effect_level,
                    connectivity=descriptor.connectivity,
                    timeout_ms=self._tool_timeout_ms(),
                )],
                estimated_latency=descriptor.latency_class,
                final_style=style_hint,
            )
        return ToolPlan(
            turn_id=turn_id,
            mode="planner",
            ack="I'll check that online.",
            estimated_latency="generative",
            final_style=style_hint,
        )

    def _action_to_step(self, action: dict, fallback_text: str):
        route = action["route"]
        return self._route_to_step(route, action.get("text", fallback_text), dict(action.get("args", {})))

    def _route_to_step(self, route: dict, raw_text: str, args: dict):
        name = route["spec"]["name"]
        descriptor = self.app.capability_registry.get_descriptor(name)
        return ToolStep(
            capability_name=name,
            args=dict(args or {}),
            raw_text=raw_text,
            side_effect_level=getattr(descriptor, "side_effect_level", "read"),
            connectivity=getattr(descriptor, "connectivity", "local"),
            timeout_ms=self._tool_timeout_ms(),
        )

    def _first_online_confirmation_needed(self, steps: list[ToolStep], text: str):
        for step in steps:
            descriptor = self.app.capability_registry.get_descriptor(step.capability_name)
            if self._requires_online_confirmation(step.capability_name, descriptor, text):
                return step
        return None

    def _build_online_proposal(self, step: ToolStep, text: str, turn_id: str, style_hint: str):
        self.app.context_store.set_pending_online(
            self.app.session_id,
            {"tool_name": step.capability_name, "args": dict(step.args or {}), "text": step.raw_text or text, "ack": step.capability_name.replace("_", " ")},
        )
        descriptor = self.app.capability_registry.get_descriptor(step.capability_name)
        noun = (descriptor.description if descriptor else "") or step.capability_name.replace("_", " ")
        return ToolPlan(
            turn_id=turn_id,
            mode="clarify",
            reply=f"I can handle that with an online skill for {noun.lower()}. Say yes if you want me to go online for this request.",
            requires_confirmation=True,
            final_style=style_hint,
        )

    def _ack_for_steps(self, steps: list[ToolStep]):
        if not steps:
            return ""
        if len(steps) > 1:
            return "I'll handle that in steps."
        step = steps[0]
        descriptor = self.app.capability_registry.get_descriptor(step.capability_name)
        latency = getattr(descriptor, "latency_class", step.timeout_ms)
        if step.capability_name == "llm_chat":
            return self._chat_ack(step.raw_text)
        if step.connectivity == "online":
            return "I'll open that up."
        if latency in {"slow", "generative", "background"}:
            return "I'll work on that now."
        return ""

    def _chat_ack(self, text: str):
        if "?" in text or re.search(r"\b(?:what|why|how|when|where|who)\b", text):
            return "Let me think that through."
        return "I'm with you."

    def _estimated_latency(self, steps: list[ToolStep]):
        classes = []
        for step in steps:
            descriptor = self.app.capability_registry.get_descriptor(step.capability_name)
            classes.append(getattr(descriptor, "latency_class", "interactive"))
        if "generative" in classes:
            return "generative"
        if "slow" in classes or len(steps) > 1:
            return "slow"
        return "interactive"

    def _should_use_planner(self, text: str):
        if not getattr(self.app.router, "enable_llm_tool_routing", False):
            return False
        normalized = text.strip().lower()
        if not normalized:
            return False
        return normalized.startswith(self.TOOL_ORIENTED_STARTERS)

    def _requires_online_confirmation(self, tool_name: str, descriptor, text: str):
        if descriptor is None or descriptor.connectivity != "online":
            return False
        permission_mode = self._config_get("conversation.online_permission_mode", descriptor.permission_mode)
        if descriptor.permission_mode == "always_ok":
            return False
        if tool_name in {"play_youtube", "play_youtube_music"}:
            return False
        if self._is_explicit_online_request(text):
            return False
        return permission_mode == "ask_first"

    def _is_explicit_online_request(self, text: str):
        lowered = (text or "").strip().lower()
        return any(re.search(pattern, lowered) for pattern in self.EXPLICIT_ONLINE_PATTERNS)

    def _looks_like_current_info_request(self, text: str):
        lowered = (text or "").strip().lower()
        return any(re.search(pattern, lowered) for pattern in self.CURRENT_INFO_PATTERNS)

    def _is_positive_confirmation(self, text: str):
        normalized = (text or "").strip().lower().strip(" .!?")
        if not normalized:
            return False
        if any(re.search(pattern, normalized) for pattern in self.NEGATIVE_CONFIRMATION_PATTERNS):
            return False
        return any(re.search(pattern, normalized) for pattern in self.POSITIVE_CONFIRMATION_PATTERNS)

    def _is_negative_confirmation(self, text: str):
        normalized = (text or "").strip().lower().strip(" .!?")
        return any(re.search(pattern, normalized) for pattern in self.NEGATIVE_CONFIRMATION_PATTERNS)

    def _clean(self, text: str, source: str = "user"):
        assistant_context = getattr(self.app, "assistant_context", None)
        if assistant_context and hasattr(assistant_context, "clean_user_text"):
            cleaned = assistant_context.clean_user_text(text, source=source)
            if cleaned:
                return cleaned
        return text

    def _record_route_duration(self, started_at: float):
        feedback = getattr(self.app, "turn_feedback", None)
        active_turn = getattr(self.app, "_active_turn_record", None)
        if feedback and active_turn:
            active_turn.metrics["route_duration_ms"] = round((self._now() - started_at) * 1000, 1)

    def _tool_timeout_ms(self):
        return int(self._config_get("routing.tool_timeout_ms", 8000) or 8000)

    def _config_get(self, key, default=None):
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            return config.get(key, default)
        return default

    def _now(self):
        import time

        return time.monotonic()
