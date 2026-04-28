from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from core.capability_broker import ToolPlan
from core.delegation import DelegationRequest


@dataclass
class ToolStepResult:
    ok: bool
    capability_name: str
    output: Any = ""
    error: str = ""
    duration_ms: float = 0.0
    memory_candidates: list[dict] = field(default_factory=list)


class OrderedToolExecutor:
    def __init__(self, app):
        self.app = app

    def execute(self, plan: ToolPlan, user_text: str, turn=None):
        if plan.mode in {"reply", "clarify"}:
            self.app.router._set_routing_decision("deterministic", tool_name="", args={})
            return plan.reply

        if plan.mode == "delegate":
            request = DelegationRequest(
                agent_type=plan.delegation.get("agent_type", "planner"),
                task=plan.delegation.get("task", user_text),
                context_bundle=dict(plan.delegation.get("context_bundle") or {}),
                timeout_ms=int(plan.delegation.get("timeout_ms", 3000)),
            )
            result = self.app.delegation_manager.delegate(request)
            self.app.router._set_routing_decision("workflow", tool_name=request.agent_type, args=result.structured_output)
            return result.summary

        if plan.mode == "planner":
            if turn is not None:
                self.app.turn_feedback.emit_llm_started(turn, lane="tool")
            return self.app.router.process_text(user_text)

        if plan.mode in {"tool", "chat"}:
            return self._execute_steps(plan, user_text, turn=turn)

        return "I need a bit more detail before I can do that."

    def _execute_steps(self, plan: ToolPlan, user_text: str, turn=None):
        responses = []
        for step in plan.steps:
            started_at = time.monotonic()
            if turn is not None:
                if step.capability_name == "llm_chat":
                    self.app.turn_feedback.emit_llm_started(turn, lane="chat")
                self.app.turn_feedback.emit_tool_started(turn, step.capability_name, step.args)
            result = self.app.capability_executor.execute(step.capability_name, step.raw_text or user_text, step.args)
            duration_ms = (time.monotonic() - started_at) * 1000
            if turn is not None:
                self.app.turn_feedback.emit_tool_finished(turn, step.capability_name, result.ok, duration_ms, error=result.error)
            if result.ok:
                self.app.router._remember_tool_use(step.capability_name, step.args)
                self.app.router._set_routing_decision("deterministic", tool_name=step.capability_name, args=step.args)
                responses.append(self.app.router._finalize_response(result.output))
                self.app.context_store.clear_pending_online(self.app.session_id)
            else:
                responses.append(f"Error running command: {result.error}")
        return "\n".join(str(item) for item in responses if item)
