"""TurnOrchestrator — single control flow for a turn.

Phase 3 of the v2 architecture (docs/friday_architecture.md §8).

Replaces the five competing v1 paths (TaskRunner / direct _execute_turn /
fast_media_command / dictation early-exit / no-capabilities legacy) with
one method: `handle(TurnRequest) -> TurnResponse`.

Sequence (per §8 sequence diagram):

  1. Build a context bundle from MemoryBroker.
  2. Ask WorkflowCoordinator if an active workflow can absorb the input.
  3. If not, classify intent (IntentEngine).
  4. Build the plan (PlannerEngine — fast path for high-confidence
     intents, full pipeline otherwise).
  5. Execute via the configured executor (TaskGraphExecutor in parallel
     mode, OrderedToolExecutor otherwise).
  6. Curate memory and emit the structured TurnResponse.

The orchestrator does NOT own turn-feedback events, voice cancellation,
or the TurnContext lifecycle — those belong to TurnManager. The
orchestrator is invoked by TurnManager when the v2 dispatch flag is on
(`routing.orchestrator: "v2"`); the legacy path stays as the default.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from core.logger import logger
from core.planning.intent_engine import HIGH_THRESHOLD


SourceLiteral = Literal["voice", "text", "gui", "user", "task_runner"]


@dataclass
class TurnRequest:
    text: str
    source: str = "user"
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
    turn_id: str = ""

    def __post_init__(self):
        if not self.turn_id:
            self.turn_id = uuid.uuid4().hex


@dataclass
class TurnResponse:
    response: str
    spoken_ack: str | None = None
    source: str = "planner"        # "intent" | "planner" | "workflow" | "chat"
    trace_id: str = ""
    duration_ms: float = 0.0
    plan_mode: str = ""
    error: str | None = None


class TurnOrchestrator:
    """The v2 single-entrypoint turn handler."""

    def __init__(
        self,
        app,
        intent_engine,
        planner_engine,
        workflow_coordinator,
        memory_broker=None,
    ):
        self.app = app
        self._intent = intent_engine
        self._planner = planner_engine
        self._workflow = workflow_coordinator
        self._memory = memory_broker

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def handle(self, request: TurnRequest, ctx=None) -> TurnResponse:
        started = time.monotonic()
        trace_id = getattr(ctx, "trace_id", "") or request.turn_id
        session_id = request.session_id or getattr(self.app, "session_id", "")

        # 1. Context bundle
        bundle = self._build_context_bundle(request.text, session_id)
        if ctx is not None:
            try:
                ctx.context_bundle = bundle
            except AttributeError:
                pass

        # 2. Pending online confirmation check — must come before intent/workflow
        # so "yes" / "no" after an online-consent prompt resolves the pending
        # action rather than being misrouted to confirm_yes / confirm_no.
        pending_plan = self._check_pending_confirmation(request.text, request.turn_id, session_id)
        if pending_plan is not None:
            logger.info("[ROUTE] source=confirmation tool=%s", getattr(pending_plan, "tool_name", "") or "")
            response_text = self._execute(pending_plan, request.text)
            self._curate_memory(request.text, response_text, bundle, session_id)
            return TurnResponse(
                response=response_text,
                spoken_ack=getattr(pending_plan, "ack", None) or None,
                source="deterministic",
                trace_id=trace_id,
                duration_ms=(time.monotonic() - started) * 1000,
                plan_mode=getattr(pending_plan, "mode", ""),
            )

        # 3. Active workflow check
        wf = self._workflow.try_resume(request.text, session_id, context=bundle)
        if wf.handled:
            logger.info("[ROUTE] source=workflow elapsed_ms=%.0f", (time.monotonic() - started) * 1000)
            self._curate_memory(request.text, wf.response, bundle, session_id)
            return TurnResponse(
                response=wf.response,
                spoken_ack=None,
                source="workflow",
                trace_id=trace_id,
                duration_ms=(time.monotonic() - started) * 1000,
                plan_mode="workflow",
            )

        # 5. Intent classification
        intent = self._intent.classify(request.text, ctx=ctx)

        # 6. Plan construction
        try:
            plan = self._planner.plan(request.text, ctx=ctx, intent=intent)
        except Exception as exc:
            logger.exception("[turn_orch] plan() failed: %s", exc)
            return TurnResponse(
                response=f"I ran into a problem planning that: {exc}",
                source="planner",
                trace_id=trace_id,
                duration_ms=(time.monotonic() - started) * 1000,
                error=str(exc),
            )

        plan_source = self._plan_source(intent, plan)
        logger.info(
            "[ROUTE] source=%s tool=%s mode=%s intent_conf=%.2f elapsed_ms=%.0f",
            plan_source,
            getattr(plan, "tool_name", "") or "",
            getattr(plan, "mode", "") or "",
            getattr(intent, "confidence", 0.0) if intent else 0.0,
            (time.monotonic() - started) * 1000,
        )

        # 5. Execute
        try:
            response_text = self._execute(plan, request.text)
        except Exception as exc:
            logger.exception("[turn_orch] execute() failed: %s", exc)
            return TurnResponse(
                response=f"I ran into a problem running that: {exc}",
                spoken_ack=getattr(plan, "ack", None) or None,
                source=plan_source,
                trace_id=trace_id,
                duration_ms=(time.monotonic() - started) * 1000,
                plan_mode=getattr(plan, "mode", ""),
                error=str(exc),
            )

        # 7. Memory curation
        self._curate_memory(request.text, response_text, bundle, session_id)

        return TurnResponse(
            response=response_text,
            spoken_ack=getattr(plan, "ack", None) or None,
            source=plan_source,
            trace_id=trace_id,
            duration_ms=(time.monotonic() - started) * 1000,
            plan_mode=getattr(plan, "mode", ""),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_pending_confirmation(self, text: str, turn_id: str, session_id: str):
        """Return a ToolPlan if there's a pending online confirmation to resolve.

        Delegates to CapabilityBroker.check_pending_confirmation so the same
        logic handles yes/no in both the v1 (broker.build_plan) and v2 paths.
        Returns None when there is no pending confirmation or the text is not
        a confirmation gesture.
        """
        broker = getattr(self.app, "capability_broker", None)
        if broker is None:
            return None
        try:
            return broker.check_pending_confirmation(text, turn_id)
        except Exception:
            logger.debug("[turn_orch] pending confirmation check failed", exc_info=True)
            return None

    def _build_context_bundle(self, text: str, session_id: str) -> dict:
        broker = self._memory or getattr(self.app, "memory_broker", None)
        if broker is None or not session_id:
            return {}
        try:
            return broker.build_context_bundle(text, session_id) or {}
        except Exception:
            logger.debug("[turn_orch] memory bundle build failed", exc_info=True)
            return {}

    def _curate_memory(self, text: str, response: str, bundle: dict, session_id: str) -> None:
        if not session_id:
            return
        delegation = getattr(self.app, "delegation_manager", None)
        curator = getattr(delegation, "memory_curator", None) if delegation else None
        if curator is None:
            return
        persona = (bundle or {}).get("persona") or {}
        try:
            curator.curate(
                session_id=session_id,
                user_text=text,
                assistant_text=response,
                persona_id=persona.get("persona_id", ""),
            )
        except Exception:
            logger.debug("[turn_orch] memory curation failed", exc_info=True)

    def _execute(self, plan, text: str) -> str:
        """Pick the executor exactly like ConversationAgent does, then run.

        Reuses the existing conversation_agent dispatch so the v2 path
        doesn't drift from the v1 selection rule.
        """
        agent = getattr(self.app, "conversation_agent", None)
        if agent is not None and hasattr(agent, "_select_executor"):
            executor = agent._select_executor(plan)
        else:
            executor = self.app.ordered_tool_executor
        return executor.execute(plan, text, turn=None)

    @staticmethod
    def _plan_source(intent, plan) -> str:
        """Classify where the plan came from for telemetry."""
        if getattr(plan, "mode", "") in {"reply", "clarify"}:
            return "deterministic"
        if intent is not None and intent.confidence >= HIGH_THRESHOLD:
            return "intent"
        if getattr(plan, "mode", "") == "chat":
            return "chat"
        return "planner"
