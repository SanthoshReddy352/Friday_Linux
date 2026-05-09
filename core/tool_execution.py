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
            self.app.routing_state.set_decision("deterministic", tool_name="", args={})
            return plan.reply

        if plan.mode == "delegate":
            request = DelegationRequest(
                agent_type=plan.delegation.get("agent_type", "planner"),
                task=plan.delegation.get("task", user_text),
                context_bundle=dict(plan.delegation.get("context_bundle") or {}),
                timeout_ms=int(plan.delegation.get("timeout_ms", 3000)),
            )
            result = self.app.delegation_manager.delegate(request)
            self.app.routing_state.set_decision("workflow", tool_name=request.agent_type, args=result.structured_output)
            return result.summary

        if plan.mode == "planner":
            if turn is not None:
                self.app.turn_feedback.emit_llm_started(turn, lane="tool")
            return self.app.router.process_text(user_text)

        if plan.mode in {"tool", "chat"}:
            return self._execute_steps(plan, user_text, turn=turn)

        return "I need a bit more detail before I can do that."

    def _execute_steps(self, plan: ToolPlan, user_text: str, turn=None):
        cache = getattr(self.app, "result_cache", None)
        memory = getattr(self.app, "memory_service", None) or self.app.context_store
        responses = []
        for step in plan.steps:
            # Phase 10: check cache before executing
            cached_output = None
            if cache is not None:
                descriptor = getattr(self.app.capability_registry, "get_descriptor", lambda n: None)(step.capability_name)
                cached_output = cache.get(step.capability_name, step.args, step.raw_text or user_text)

            if cached_output is not None:
                self.app.response_finalizer.remember_tool_use(step.capability_name, step.args)
                self.app.routing_state.set_decision("deterministic", tool_name=step.capability_name, args=step.args)
                responses.append(self.app.response_finalizer.finalize(cached_output))
                memory.clear_pending_online(self.app.session_id)
                continue

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
                # Save working artifact for pronoun resolution ("save that", "use this")
                self._save_artifact(step, result)
                # Phase 10: cache successful read results
                if cache is not None:
                    descriptor = getattr(self.app.capability_registry, "get_descriptor", lambda n: None)(step.capability_name)
                    cache.set(step.capability_name, step.args, result.output, descriptor=descriptor, raw_text=step.raw_text or user_text)
                self.app.response_finalizer.remember_tool_use(step.capability_name, step.args)
                self.app.routing_state.set_decision("deterministic", tool_name=step.capability_name, args=step.args)
                responses.append(self.app.response_finalizer.finalize(result.output))
                memory.clear_pending_online(self.app.session_id)
                # Phase 7: record procedural outcome
                memory_broker = getattr(self.app, "memory_broker", None)
                if memory_broker and hasattr(memory_broker, "record_capability_outcome"):
                    memory_broker.record_capability_outcome(step.capability_name, None, True)
            else:
                responses.append(f"Error running command: {result.error}")
                memory_broker = getattr(self.app, "memory_broker", None)
                if memory_broker and hasattr(memory_broker, "record_capability_outcome"):
                    memory_broker.record_capability_outcome(step.capability_name, None, False)
        return "\n".join(str(item) for item in responses if item)

    def _save_artifact(self, step, result) -> None:
        """Persist the tool result as the session's working artifact."""
        output = getattr(result, "output", "")
        if not output:
            return
        try:
            from core.context_store import WorkingArtifact
            artifact = WorkingArtifact(
                content=str(output),
                output_type=getattr(result, "output_type", "text"),
                capability_name=step.capability_name,
                artifact_type=getattr(result, "output_type", "text"),
            )
            memory = getattr(self.app, "memory_service", None)
            session_id = getattr(self.app, "session_id", "")
            if memory and session_id:
                memory.save_artifact(session_id, artifact)
        except Exception:
            pass
