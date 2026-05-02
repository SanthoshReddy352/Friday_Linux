from __future__ import annotations

import uuid

from core.planning import TurnRequest
from core.tracing import trace_scope
from core.turn_context import TurnContext, turn_scope


class TurnManager:
    def __init__(self, app, conversation_agent):
        self.app = app
        self.conversation_agent = conversation_agent

    def handle_turn(self, text: str, source: str = "user"):
        feedback = getattr(self.app, "turn_feedback", None)
        turn = feedback.start_turn(text, source=source) if feedback else None
        # Reuse the TurnRecord's uuid as the trace_id so logs/events line up
        # with metrics records without a second correlation column.
        turn_id = getattr(turn, "turn_id", None) or uuid.uuid4().hex
        ctx = TurnContext(
            turn_id=turn_id,
            session_id=self.app.session_id,
            trace_id=turn_id,
            source=source,
            text=text,
            _routing_state=getattr(self.app, "routing_state", None),
            _dialog_state=getattr(self.app, "dialog_state", None),
        )
        self.app.current_turn_context = ctx
        with trace_scope(turn_id), turn_scope(ctx):
            self.app._active_turn_record = turn
            session_id = self.app.session_id
            memory = getattr(self.app, "memory_service", None) or self.app.context_store
            state = memory.get_session_state(session_id) or {}
            state["last_source"] = source
            memory.save_session_state(session_id, state)
            try:
                if self._use_v2_orchestrator():
                    response = self._handle_via_orchestrator(
                        ctx, text, source, turn, feedback
                    )
                elif not self.app.capability_registry.list_capabilities():
                    response = self.app.router.process_text(text)
                else:
                    plan, context_bundle = self.conversation_agent.build_tool_plan(text, source=source, turn=turn)
                    if feedback and turn and plan.ack:
                        feedback.emit_ack(turn, plan.ack)
                    if feedback and turn and plan.estimated_latency in {"slow", "generative", "background"}:
                        feedback.start_progress_timers(turn)
                    response = self.conversation_agent.execute_tool_plan(plan, text, turn=turn)
                    self.conversation_agent.curate_memory(text, response, context_bundle)
                speak_final = not self.app.routing_state.voice_already_spoken
                if feedback and turn:
                    feedback.complete_turn(turn, response, speak_final=speak_final, ok=True)
                    self.app._last_turn_speech_managed = True
                return response
            except Exception as exc:
                if feedback and turn:
                    feedback.fail_turn(turn, str(exc))
                    self.app._last_turn_speech_managed = True
                raise
            finally:
                self.app._active_turn_record = None
                self.app.current_turn_context = None

    # ------------------------------------------------------------------
    # Phase 3 (v2): single-flow dispatch through TurnOrchestrator
    # ------------------------------------------------------------------

    def _use_v2_orchestrator(self) -> bool:
        """True when the v2 single-flow orchestrator should handle this turn.

        Opted into via `routing.orchestrator: "v2"` in config.yaml. Falls
        back to the legacy path when the orchestrator was never wired
        (e.g. tests that mount a partial app).
        """
        if getattr(self.app, "turn_orchestrator", None) is None:
            return False
        config = getattr(self.app, "config", None)
        if config is None or not hasattr(config, "get"):
            return False
        value = str(config.get("routing.orchestrator", "v1") or "v1").lower()
        return value == "v2"

    def _handle_via_orchestrator(self, ctx, text, source, turn, feedback):
        """Run the turn through TurnOrchestrator while preserving the
        feedback / progress / acknowledgement events the legacy path
        emits, so external observers (TTS, GUI, metrics) see no
        difference between the two dispatch modes."""
        request = TurnRequest(
            text=text,
            source=source,
            session_id=self.app.session_id,
            turn_id=ctx.turn_id,
        )
        response = self.app.turn_orchestrator.handle(request, ctx=ctx)
        if feedback and turn:
            if response.spoken_ack:
                feedback.emit_ack(turn, response.spoken_ack)
            if response.plan_mode in {"tool", "chat"} and response.duration_ms > 1500:
                # Mirror the legacy "slow/generative/background" timer
                # heuristic so any progress chimes still fire.
                feedback.start_progress_timers(turn)
        if response.error:
            raise RuntimeError(response.error)
        return response.response
