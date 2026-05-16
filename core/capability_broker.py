"""CapabilityBroker — convert user intent into a ToolPlan.

Phase 5: No longer depends on CommandRouter for routing decisions.
Uses app.route_scorer (RouteScorer), app.intent_recognizer (IntentRecognizer),
and app.workflow_orchestrator (WorkflowOrchestrator) directly.
CommandRouter is still alive but CapabilityBroker is fully decoupled from it.
"""
from __future__ import annotations

import re
import time
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
    # Phase 4 (v2): DAG metadata used by TaskGraphExecutor.
    # node_id is the identifier other steps reference in `depends_on`.
    # If left blank the executor assigns "step{idx}" at runtime.
    # An empty depends_on means the step has no inputs — it lands in wave 0
    # and runs in parallel with every other unconstrained step.
    node_id: str = ""
    depends_on: list[str] = field(default_factory=list)
    retries: int = 0
    fallback_capability: str = ""


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
    TOOL_ORIENTED_STARTERS = (
        "open", "launch", "start", "bring up", "run", "execute", "take", "capture",
        "find", "search", "locate", "set", "save", "read", "show", "list", "check",
        "summarize", "summary", "remind", "enable", "disable", "turn", "mute",
        "unmute", "increase", "decrease", "lower", "raise", "pause", "stop", "play",
    )

    def __init__(self, app):
        self.app = app
        self._consent_preapproved = False

    def _memory(self):
        """Return MemoryService when wired (production); fall back to the
        raw ContextStore for ad-hoc test apps. Both surfaces expose the
        pending-online / session-state / log_online_permission methods we
        call below."""
        return getattr(self.app, "memory_service", None) or self.app.context_store

    def build_plan(
        self,
        text: str,
        turn_id: str,
        source: str = "user",
        context_bundle: dict | None = None,
        style_hint: str = "",
    ) -> ToolPlan:
        cleaned_text = self._clean(text, source=source)
        route_start = self._now()

        # --- 1. Pending online confirmation ---
        pending_plan = self._plan_pending_online(cleaned_text, turn_id, style_hint)
        if pending_plan:
            self._record_route_duration(route_start)
            return pending_plan

        # --- 2. Active workflow continuation (Phase 5: use orchestrator directly) ---
        workflow_result = self._try_continue_workflow(cleaned_text)
        if workflow_result is not None:
            self._record_route_duration(route_start)
            return ToolPlan(turn_id=turn_id, mode="reply", reply=workflow_result, final_style=style_hint)

        # --- 3. Multi-action planning (Phase 5: use intent_recognizer directly) ---
        action_plan = self._plan_actions(cleaned_text)
        if action_plan:
            steps = [self._action_to_step(action, cleaned_text) for action in action_plan]
            online = None if self._consent_preapproved else self._first_online_confirmation_needed(steps, cleaned_text)
            if online:
                self._record_route_duration(route_start)
                return self._build_online_proposal(online, cleaned_text, turn_id, style_hint)
            self._record_route_duration(route_start)
            return ToolPlan(
                turn_id=turn_id,
                mode="tool",
                steps=steps,
                ack=self._ack_for_steps(steps, cleaned_text),
                estimated_latency=self._estimated_latency(steps),
                final_style=style_hint,
            )

        # --- 4. Deterministic best-route (Phase 5: use route_scorer directly) ---
        best_route = self._find_best_route(cleaned_text, min_score=80)
        if best_route and best_route["spec"]["name"] != "llm_chat":
            step = self._route_to_step(best_route, cleaned_text, {})
            descriptor = self.app.capability_registry.get_descriptor(step.capability_name)
            if not self._consent_preapproved and self.app.consent_service.evaluate(step.capability_name, descriptor, cleaned_text).needs_confirmation:
                self._record_route_duration(route_start)
                return self._build_online_proposal(step, cleaned_text, turn_id, style_hint)
            self._record_route_duration(route_start)
            return ToolPlan(
                turn_id=turn_id,
                mode="tool",
                steps=[step],
                ack=self._ack_for_steps([step], cleaned_text),
                estimated_latency=self._estimated_latency([step]),
                final_style=style_hint,
            )

        # --- 5. Online/current-info detection ---
        if self.app.consent_service.is_current_info_request(cleaned_text) and not self._consent_preapproved:
            online_capabilities = self.app.capability_registry.list_capabilities(connectivity="online")
            if online_capabilities and not self.app.consent_service.is_explicit_online_request(cleaned_text):
                self._memory().set_pending_online(
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

        # --- 6. LLM planner fallback ---
        if self._should_use_planner(cleaned_text):
            self._record_route_duration(route_start)
            return ToolPlan(
                turn_id=turn_id,
                mode="planner",
                ack="Let me work that out.",
                estimated_latency="generative",
                final_style=style_hint,
            )

        # --- 7. Chat fallback ---
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
        return ToolPlan(
            turn_id=turn_id,
            mode="clarify",
            reply="I need a bit more detail before I can do that.",
            final_style=style_hint,
        )

    # ------------------------------------------------------------------
    # Phase 5: decoupled routing primitives
    # ------------------------------------------------------------------

    def _try_continue_workflow(self, text: str):
        """Continue an active workflow using WorkflowOrchestrator directly.

        Phase 5: was self.app.router.continue_active_workflow(text).
        Falls back to router method if orchestrator is unavailable.
        """
        orchestrator = getattr(self.app, "workflow_orchestrator", None)
        session_id = getattr(self.app, "session_id", None)
        if orchestrator and session_id:
            try:
                result = orchestrator.continue_active(
                    text, session_id, context={}
                )
                if result and getattr(result, "handled", False):
                    return getattr(result, "response", None)
            except Exception:
                pass
        # Compatibility fallback: router still alive during Phase 5
        router = getattr(self.app, "router", None)
        if router and hasattr(router, "continue_active_workflow"):
            return router.continue_active_workflow(text)
        return None

    def _plan_actions(self, text: str) -> list[dict]:
        """Plan multi-step actions using IntentRecognizer directly.

        Phase 5: was self.app.router.plan_actions(text).
        """
        recognizer = getattr(self.app, "intent_recognizer", None)
        if recognizer:
            try:
                return recognizer.plan(text) or []
            except Exception:
                pass
        # Compatibility fallback
        router = getattr(self.app, "router", None)
        if router and hasattr(router, "plan_actions"):
            return router.plan_actions(text) or []
        return []

    def _find_best_route(self, text: str, min_score: int = 20) -> dict | None:
        """Find the best matching route using RouteScorer directly.

        Phase 5: was self.app.router.find_best_route(text, min_score).
        """
        scorer = getattr(self.app, "route_scorer", None)
        if scorer:
            return scorer.find_best_route(text, min_score=min_score)
        # Compatibility fallback
        router = getattr(self.app, "router", None)
        if router and hasattr(router, "find_best_route"):
            return router.find_best_route(text, min_score=min_score)
        return None

    # ------------------------------------------------------------------
    # Pending-online state management
    # ------------------------------------------------------------------

    # Batch 5 / Issue 8 confirmation-bleed: pending_online entries auto-
    # expire after this many seconds. If the user takes longer than this
    # before answering, a "yes" must NOT resolve a stale online proposal
    # — typical breakage was "yes" being applied to the wrong workflow
    # because the file workflow had advanced in the meantime.
    _PENDING_ONLINE_TTL_S = 60.0

    def _plan_pending_online(self, cleaned_text: str, turn_id: str, style_hint: str):
        session_state = self._memory().get_session_state(self.app.session_id) or {}
        pending = dict(session_state.get("pending_online") or {})
        # Drop expired entries before evaluating yes/no — protects against
        # confirmation cross-talk where "yes" to an unrelated later
        # prompt would resurrect a long-stale online tool.
        if pending and self._is_pending_expired(pending):
            self._memory().clear_pending_online(self.app.session_id)
            pending = {}
        if self.app.consent_service.is_negative_confirmation(cleaned_text) and pending:
            self._memory().log_online_permission(self.app.session_id, pending.get("tool_name", ""), "declined", reason="user_confirmation")
            self._memory().clear_pending_online(self.app.session_id)
            return ToolPlan(
                turn_id=turn_id,
                mode="clarify",
                reply="Okay. I'll stay offline unless you want me to use an online skill.",
                final_style=style_hint,
            )
        if not self.app.consent_service.is_positive_confirmation(cleaned_text):
            return None
        if not pending:
            return None
        self._memory().log_online_permission(self.app.session_id, pending.get("tool_name", ""), "approved", reason="user_confirmation")
        tool_name = pending.get("tool_name", "")
        descriptor = self.app.capability_registry.get_descriptor(tool_name) if tool_name else None
        if descriptor is not None:
            self._memory().clear_pending_online(self.app.session_id)
            return ToolPlan(
                turn_id=turn_id,
                mode="tool",
                ack=pending.get("ack") or "",
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
        # No specific online tool was captured — re-route the *original*
        # request text with consent pre-approved so the online detection
        # step in build_plan() won't re-prompt.
        self._memory().clear_pending_online(self.app.session_id)
        original_text = (pending.get("text") or "").strip()
        if original_text:
            self._consent_preapproved = True
            try:
                return self.build_plan(original_text, turn_id, style_hint=style_hint)
            finally:
                self._consent_preapproved = False
        return None

    # ------------------------------------------------------------------
    # Step builders
    # ------------------------------------------------------------------

    def _action_to_step(self, action: dict, fallback_text: str) -> ToolStep:
        # Old router format: {"route": {...}, "args": {...}, "text": "..."}
        # New IntentRecognizer format: {"tool": "...", "args": {...}, "text": "..."}
        if "route" in action:
            route = action["route"]
        else:
            tool_name = action.get("tool", "")
            route = self._find_best_route(tool_name, min_score=0)
            if route is None:
                # Build a minimal route from the tool name
                route = {"spec": {"name": tool_name}, "callback": None, "score": 0}
        return self._route_to_step(route, action.get("text", fallback_text), dict(action.get("args", {})))

    def _route_to_step(self, route: dict, raw_text: str, args: dict) -> ToolStep:
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
            if self.app.consent_service.evaluate(step.capability_name, descriptor, text).needs_confirmation:
                return step
        return None

    def check_pending_confirmation(self, text: str, turn_id: str, style_hint: str = "") -> "ToolPlan | None":
        """Public wrapper — used by v2 TurnOrchestrator to handle pending consent before routing."""
        return self._plan_pending_online(text, turn_id, style_hint)

    def _is_pending_expired(self, pending: dict) -> bool:
        """Return True iff the pending_online entry has crossed its TTL.

        Missing ``proposed_at`` is treated as fresh — legacy entries
        written before the TTL was introduced still resolve once, after
        which any further user input will populate the new timestamp.
        """
        proposed_at = pending.get("proposed_at")
        if not proposed_at:
            return False
        try:
            from datetime import datetime  # noqa: PLC0415
            ts = datetime.fromisoformat(proposed_at)
            age_s = (datetime.now() - ts).total_seconds()
        except Exception:
            return False
        return age_s > self._PENDING_ONLINE_TTL_S

    def _build_online_proposal(self, step: ToolStep, text: str, turn_id: str, style_hint: str) -> ToolPlan:
        from datetime import datetime  # noqa: PLC0415
        slot_signature = f"{step.capability_name}|{sorted((step.args or {}).items())!r}"
        self._memory().set_pending_online(
            self.app.session_id,
            {
                "tool_name": step.capability_name,
                "args": dict(step.args or {}),
                "text": step.raw_text or text,
                "ack": step.capability_name.replace("_", " "),
                # Batch 5 / Issue 8 confirmation-bleed: timestamp + slot
                # signature lets _plan_pending_online drop entries the
                # user wandered away from before answering yes/no.
                "proposed_at": datetime.now().isoformat(),
                "slot_signature": slot_signature,
                "turn_id": turn_id,
            },
        )
        reply = self._short_consent_question(step.capability_name, dict(step.args or {}))
        return ToolPlan(
            turn_id=turn_id,
            mode="clarify",
            reply=reply,
            requires_confirmation=True,
            final_style=style_hint,
        )

    def _short_consent_question(self, tool_name: str, args: dict) -> str:
        """Generate a short yes/no consent question instead of reading the full description."""
        # Tool-specific short labels with key arg substituted where available
        topic = (args.get("topic") or args.get("query") or args.get("search") or "").strip()
        if tool_name == "research_topic":
            subject = f" '{topic}'" if topic else ""
            return f"Research{subject} online? Say yes or no."
        if tool_name in {"play_youtube", "play_youtube_music"}:
            subject = f" '{topic}'" if topic else ""
            return f"Play{subject} online? Say yes or no."
        if tool_name.startswith("weather"):
            return "Check the weather online? Say yes or no."
        if "search" in tool_name or "web" in tool_name:
            subject = f" '{topic}'" if topic else ""
            return f"Search{subject} online? Say yes or no."
        label = tool_name.replace("_", " ")
        return f"Go online for {label}? Say yes or no."

    # ------------------------------------------------------------------
    # Ack / latency helpers
    # ------------------------------------------------------------------

    def _ack_for_steps(self, steps: list[ToolStep], user_text: str = "") -> str:
        if not steps:
            return ""
        if len(steps) > 1:
            return "On it."
        step = steps[0]
        descriptor = self.app.capability_registry.get_descriptor(step.capability_name)
        latency = getattr(descriptor, "latency_class", step.timeout_ms)
        if step.capability_name == "llm_chat":
            return self._chat_ack(step.raw_text or user_text)
        # Phase 9: contextual ack via DialogueManager
        dialogue_manager = getattr(self.app, "dialogue_manager", None)
        if dialogue_manager and (step.connectivity == "online" or latency in {"slow", "generative", "background"}):
            ack = dialogue_manager._ack_from_text(user_text or step.raw_text)
            if ack:
                return ack
        if step.connectivity == "online":
            return "On it."
        if latency in {"slow", "generative", "background"}:
            return "One moment."
        return ""

    def _chat_ack(self, text: str) -> str:
        return ""

    def _estimated_latency(self, steps: list[ToolStep]) -> str:
        classes = []
        for step in steps:
            descriptor = self.app.capability_registry.get_descriptor(step.capability_name)
            classes.append(getattr(descriptor, "latency_class", "interactive"))
        if "generative" in classes:
            return "generative"
        if "slow" in classes or len(steps) > 1:
            return "slow"
        return "interactive"

    def _should_use_planner(self, text: str) -> bool:
        router = getattr(self.app, "router", None)
        if not getattr(router, "enable_llm_tool_routing", False):
            return False
        normalized = (text or "").strip().lower()
        if not normalized:
            return False
        return normalized.startswith(self.TOOL_ORIENTED_STARTERS)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _clean(self, text: str, source: str = "user") -> str:
        assistant_context = getattr(self.app, "assistant_context", None)
        if assistant_context and hasattr(assistant_context, "clean_user_text"):
            cleaned = assistant_context.clean_user_text(text, source=source)
            if cleaned:
                return cleaned
        return text

    def _record_route_duration(self, started_at: float) -> None:
        feedback = getattr(self.app, "turn_feedback", None)
        active_turn = getattr(self.app, "_active_turn_record", None)
        if feedback and active_turn:
            active_turn.metrics["route_duration_ms"] = round((self._now() - started_at) * 1000, 1)

    def _tool_timeout_ms(self) -> int:
        return int(self._config_get("routing.tool_timeout_ms", 8000) or 8000)

    def _config_get(self, key, default=None):
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            return config.get(key, default)
        return default

    def _now(self) -> float:
        return time.monotonic()
