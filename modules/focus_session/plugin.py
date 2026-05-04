"""Voice-tool wrapper around the FocusModeWorkflow.

The workflow does the real work (DND, media pause, timer). This plugin just
exposes start/end/status as deterministic tools so the intent recognizer
can dispatch them like any other capability.
"""
from __future__ import annotations

from core.logger import logger
from core.plugin_manager import FridayPlugin


class FocusSessionPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "FocusSession"
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "start_focus_session",
            "description": (
                "Start a focus / pomodoro session. Mutes notifications, pauses media, "
                "and announces when the session ends. Default 25 minutes."
            ),
            "parameters": {
                "minutes": "integer – session length in minutes (1–240)",
            },
            "context_terms": [
                "focus session", "pomodoro", "do not disturb", "focus mode", "concentrate",
            ],
        }, self.handle_start, capability_meta={
            "connectivity": "local",
            "latency_class": "interactive",
            "permission_mode": "always_ok",
            "side_effect_level": "write",
        })

        self.app.router.register_tool({
            "name": "end_focus_session",
            "description": "End the active focus session early.",
            "parameters": {},
            "context_terms": ["end focus", "stop focus", "exit focus", "cancel focus"],
        }, self.handle_end, capability_meta={
            "connectivity": "local",
            "latency_class": "interactive",
            "permission_mode": "always_ok",
            "side_effect_level": "write",
        })

        self.app.router.register_tool({
            "name": "focus_session_status",
            "description": "Report whether a focus session is active and how much time is left.",
            "parameters": {},
            "context_terms": ["focus status", "focus left", "focus remaining"],
        }, self.handle_status, capability_meta={
            "connectivity": "local",
            "latency_class": "interactive",
            "permission_mode": "always_ok",
            "side_effect_level": "read",
        })

        logger.info("FocusSessionPlugin loaded.")

    # ------------------------------------------------------------------
    # Handlers — delegate to the FocusModeWorkflow instance owned by the
    # orchestrator so all state lives in one place.
    # ------------------------------------------------------------------

    def _workflow(self):
        orchestrator = getattr(self.app, "workflow_orchestrator", None)
        if orchestrator is None:
            return None
        return orchestrator.workflows.get("focus_mode")

    def handle_start(self, text, args):
        workflow = self._workflow()
        if workflow is None:
            return "Focus mode isn't available in this build."
        minutes = self._coerce_minutes(args.get("minutes"))
        synthesized = f"focus for {minutes} minutes" if minutes else (text or "start focus")
        result = workflow.run(synthesized, getattr(self.app, "session_id", "") or "")
        return getattr(result, "response", "")

    def handle_end(self, text, args):
        workflow = self._workflow()
        if workflow is None:
            return "Focus mode isn't available in this build."
        result = workflow.run("end focus", getattr(self.app, "session_id", "") or "")
        return getattr(result, "response", "")

    def handle_status(self, text, args):
        workflow = self._workflow()
        if workflow is None:
            return "Focus mode isn't available in this build."
        result = workflow.run("focus status", getattr(self.app, "session_id", "") or "")
        return getattr(result, "response", "")

    @staticmethod
    def _coerce_minutes(value):
        if value is None:
            return 0
        try:
            return max(1, min(int(value), 240))
        except Exception:
            return 0


def setup(app):
    return FocusSessionPlugin(app)
