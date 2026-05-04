"""WorkflowCoordinator — multi-turn workflow lifecycle facade.

Phase 3 of the v2 architecture (docs/friday_architecture.md §6, §15.2).

A thin facade over the existing `WorkflowOrchestrator` (which owns the
state machines for file / browser-media / reminder / calendar / research
/ focus workflows) and `ContextStore.get_active_workflow` (which is the
TTL-aware persistent state — Phase 1 added the 24 h auto-expiry).

The coordinator gives `TurnOrchestrator` a single question to ask at the
top of each turn — *is there an active workflow that can absorb this
input?* — and a single action to take if so — *resume it and return the
response*. The legacy CapabilityBroker-based path keeps its own
workflow check; v1 and v2 both ride on the same WorkflowOrchestrator
underneath, so behaviour is identical regardless of which dispatcher
the turn went through.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkflowResume:
    """Outcome of `WorkflowCoordinator.try_resume()`.

    `handled` is True when a workflow consumed the user input and
    produced a response. `response` is the user-facing text. `name` is
    the workflow that ran, or "" when none did.
    """

    handled: bool
    response: str = ""
    name: str = ""
    state: dict | None = None


class WorkflowCoordinator:
    """Facade over WorkflowOrchestrator + persistent workflow state."""

    def __init__(self, workflow_orchestrator, context_store):
        self._orchestrator = workflow_orchestrator
        self._store = context_store

    def get_active(self, session_id: str, name: str | None = None) -> dict | None:
        """Return the active workflow row for *session_id*, or None.

        `ContextStore.get_active_workflow` already enforces the Phase 1
        24-hour TTL, so callers don't have to duplicate the check.
        """
        if not session_id:
            return None
        return self._store.get_active_workflow(session_id, workflow_name=name)

    def try_resume(self, text: str, session_id: str, context=None) -> WorkflowResume:
        """If an active workflow can absorb *text*, run it and return the
        response. Otherwise return WorkflowResume(handled=False)."""
        if not session_id:
            return WorkflowResume(handled=False)
        try:
            result = self._orchestrator.continue_active(text, session_id, context=context)
        except Exception:
            return WorkflowResume(handled=False)
        if result is None or not getattr(result, "handled", False):
            return WorkflowResume(
                handled=False, name=getattr(result, "workflow_name", "") if result else ""
            )
        return WorkflowResume(
            handled=True,
            response=getattr(result, "response", "") or "",
            name=getattr(result, "workflow_name", "") or "",
            state=dict(getattr(result, "state", {}) or {}),
        )
