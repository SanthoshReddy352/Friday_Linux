from __future__ import annotations


class TurnManager:
    def __init__(self, app, conversation_agent):
        self.app = app
        self.conversation_agent = conversation_agent

    def handle_turn(self, text: str, source: str = "user"):
        feedback = getattr(self.app, "turn_feedback", None)
        turn = feedback.start_turn(text, source=source) if feedback else None
        self.app._active_turn_record = turn
        session_id = self.app.session_id
        state = self.app.context_store.get_session_state(session_id) or {}
        state["last_source"] = source
        self.app.context_store.save_session_state(session_id, state)
        try:
            if not self.app.capability_registry.list_capabilities():
                response = self.app.router.process_text(text)
            else:
                plan, context_bundle = self.conversation_agent.build_tool_plan(text, source=source, turn=turn)
                if feedback and turn and plan.ack:
                    feedback.emit_ack(turn, plan.ack)
                if feedback and turn and plan.estimated_latency in {"slow", "generative", "background"}:
                    feedback.start_progress_timers(turn)
                response = self.conversation_agent.execute_tool_plan(plan, text, turn=turn)
                self.conversation_agent.curate_memory(text, response, context_bundle)
            speak_final = not getattr(self.app.router, "_voice_already_spoken", False)
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
