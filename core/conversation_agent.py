from __future__ import annotations

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
        executor = self._select_executor(plan)
        return executor.execute(plan, text, turn=turn)

    def _select_executor(self, plan):
        """Phase 4 (v2): pick the executor for *plan*.

        `routing.execution_engine: "parallel"` selects TaskGraphExecutor,
        which runs independent steps concurrently in waves. Any other value
        (default: "ordered") preserves the original single-threaded path.
        TaskGraphExecutor itself forwards single-step and non-tool plans
        back to OrderedToolExecutor, so the choice is safe even when no
        steps actually parallelise.
        """
        engine = str(self._config_get("routing.execution_engine", "ordered") or "ordered").lower()
        if engine == "parallel" and getattr(self.app, "task_graph_executor", None) is not None:
            return self.app.task_graph_executor
        return self.app.ordered_tool_executor

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
            self.app.routing_state.set_decision("deterministic", tool_name="", args={})
            return plan.reply

        if plan.mode == "delegate":
            request = DelegationRequest(
                agent_type=plan.delegation.get("agent_type", "planner"),
                task=plan.delegation.get("task", text),
                context_bundle=dict(plan.delegation.get("context_bundle") or {}),
                timeout_ms=int(plan.delegation.get("timeout_ms", 3000)),
            )
            result = self.app.delegation_manager.delegate(request)
            self.app.routing_state.set_decision("workflow", tool_name=request.agent_type, args=result.structured_output)
            return result.summary

        if plan.mode == "local_tool":
            responses = []
            for call in plan.tool_calls:
                name = call["name"]
                args = dict(call.get("args") or {})
                raw_text = call.get("text", text)
                result = self.app.capability_executor.execute(name, raw_text, args)
                if result.ok:
                    self.app.response_finalizer.remember_tool_use(name, args)
                    self.app.routing_state.set_decision("deterministic", tool_name=name, args=args)
                    responses.append(self.app.response_finalizer.finalize(result.output))
                    self._memory().clear_pending_online(self.app.session_id)
                else:
                    responses.append(f"Error running command: {result.error}")
            return "\n".join(str(item) for item in responses if item)

        return "I need a bit more detail before I can do that."

    def _memory(self):
        return getattr(self.app, "memory_service", None) or self.app.context_store

    def _build_online_proposal(self, tool_name: str, args: dict, text: str, descriptor, style_hint: str):
        self._memory().set_pending_online(
            self.app.session_id,
            {"tool_name": tool_name, "args": dict(args or {}), "text": text, "ack": ""},
        )
        reply = self.app.capability_broker._short_consent_question(tool_name, dict(args or {}))
        return TurnPlan(
            mode="clarify",
            reply=reply,
            online_required=True,
            final_response_style=style_hint,
        )

    def _config_get(self, key, default=None):
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            return config.get(key, default)
        return default
