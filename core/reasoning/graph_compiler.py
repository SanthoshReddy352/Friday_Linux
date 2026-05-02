"""GraphCompiler — converts ToolPlan into an execution graph.

Phase 6: When routing.execution_engine == "graph", plans are compiled to a
LangGraph StateGraph instead of being handed to OrderedToolExecutor.

Feature flag: config `routing.execution_engine` controls the backend.
  "ordered"  → existing OrderedToolExecutor (default, always safe)
  "graph"    → LangGraph StateGraph with SqliteSaver checkpointing

If langgraph is not installed the compiler falls back to the ordered executor
regardless of the flag, and logs a warning on first use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.logger import logger

if TYPE_CHECKING:
    from core.capability_broker import ToolPlan, ToolStep


# ---------------------------------------------------------------------------
# Graph node contract (same shape whether LangGraph is present or not)
# ---------------------------------------------------------------------------

@dataclass
class GraphState:
    turn_id: str
    user_text: str
    remaining_steps: list = field(default_factory=list)
    completed: list = field(default_factory=list)
    responses: list[str] = field(default_factory=list)
    last_ok: bool = True
    error: str = ""


@dataclass
class GraphResult:
    response: str
    ok: bool
    state: GraphState


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

_LANGGRAPH_AVAILABLE: bool | None = None


def _check_langgraph() -> bool:
    global _LANGGRAPH_AVAILABLE
    if _LANGGRAPH_AVAILABLE is None:
        try:
            import langgraph  # noqa: F401

            _LANGGRAPH_AVAILABLE = True
        except ImportError:
            _LANGGRAPH_AVAILABLE = False
            logger.info(
                "[graph_compiler] langgraph not installed — "
                "routing.execution_engine='graph' will fall back to 'ordered'."
            )
    return _LANGGRAPH_AVAILABLE


class GraphCompiler:
    """Compile a ToolPlan into an execution graph or fall back to ordered execution.

    Usage:
        compiler = GraphCompiler(app)
        result = compiler.execute(plan, user_text, turn=turn)
    """

    def __init__(self, app):
        self._app = app

    def execute(self, plan: "ToolPlan", user_text: str, turn=None) -> str:
        """Execute *plan*, using the graph backend if available and enabled."""
        engine = self._execution_engine()

        if engine == "graph" and _check_langgraph():
            return self._execute_graph(plan, user_text, turn=turn)

        # Fallback: delegate to existing OrderedToolExecutor
        return self._app.ordered_tool_executor.execute(plan, user_text, turn=turn)

    # ------------------------------------------------------------------
    # Graph execution path (only reached when langgraph is installed)
    # ------------------------------------------------------------------

    def _execute_graph(self, plan: "ToolPlan", user_text: str, turn=None) -> str:
        from langgraph.graph import StateGraph, END  # noqa: PLC0415

        # Single-step fast path: skip graph overhead
        if len(getattr(plan, "steps", [])) <= 1:
            return self._app.ordered_tool_executor.execute(plan, user_text, turn=turn)

        state = GraphState(
            turn_id=getattr(plan, "turn_id", ""),
            user_text=user_text,
            remaining_steps=list(plan.steps),
        )

        workflow = StateGraph(GraphState)
        workflow.add_node("execute_step", self._node_execute_step)
        workflow.add_node("check_done", self._node_check_done)
        workflow.set_entry_point("execute_step")
        workflow.add_edge("execute_step", "check_done")
        workflow.add_conditional_edges(
            "check_done",
            lambda s: "execute_step" if s.remaining_steps else END,
        )

        compiled = workflow.compile()
        final_state = compiled.invoke(state)
        return "\n".join(r for r in final_state.get("responses", []) if r)

    def _node_execute_step(self, state: dict) -> dict:
        steps = list(state.get("remaining_steps", []))
        if not steps:
            return state
        step = steps.pop(0)
        result = self._app.capability_executor.execute(
            step.capability_name,
            step.raw_text or state.get("user_text", ""),
            step.args,
        )
        completed = list(state.get("completed", []))
        responses = list(state.get("responses", []))
        if result.ok:
            self._app.response_finalizer.remember_tool_use(step.capability_name, step.args)
            self._app.routing_state.set_decision("deterministic", tool_name=step.capability_name, args=step.args)
            finalized = self._app.response_finalizer.finalize(result.output)
            responses.append(finalized)
            (getattr(self._app, "memory_service", None) or self._app.context_store).clear_pending_online(self._app.session_id)
            completed.append({"name": step.capability_name, "ok": True})
        else:
            responses.append(f"Error running command: {result.error}")
            completed.append({"name": step.capability_name, "ok": False, "error": result.error})
        return {**state, "remaining_steps": steps, "completed": completed, "responses": responses, "last_ok": result.ok}

    def _node_check_done(self, state: dict) -> dict:
        return state

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _execution_engine(self) -> str:
        config = getattr(self._app, "config", None)
        if config and hasattr(config, "get"):
            return str(config.get("routing.execution_engine", "ordered") or "ordered").lower()
        return "ordered"
