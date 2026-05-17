"""Awareness plugin — registers capabilities and wires the AwarenessService.

Capabilities:
  enable_awareness_mode   — start continuous screen capture (explicit opt-in)
  disable_awareness_mode  — stop capture
  awareness_status        — check if awareness mode is running
  recent_screen_activity  — show last N capture summaries

EventBus subscriptions:
  awareness_struggle → voice suggestion + optional comms notification
"""
from __future__ import annotations

from core.logger import logger
from core.plugin_manager import FridayPlugin
from .service import AwarenessService


class AwarenessPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "Awareness"
        self._service = AwarenessService(app.event_bus, config=app.config)
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "enable_awareness_mode",
            "description": (
                "Start continuous awareness mode: FRIDAY watches your screen "
                "and suggests help if you seem stuck. Requires awareness.enabled=true in config."
            ),
            "parameters": {},
        }, self.handle_enable)

        self.app.router.register_tool({
            "name": "disable_awareness_mode",
            "description": "Stop the continuous screen awareness capture loop.",
            "parameters": {},
        }, self.handle_disable)

        self.app.router.register_tool({
            "name": "awareness_status",
            "description": "Check whether awareness mode is currently running.",
            "parameters": {},
        }, self.handle_status)

        self.app.router.register_tool({
            "name": "recent_screen_activity",
            "description": "Show a summary of recently captured screen activity.",
            "parameters": {"limit": "integer – how many recent captures to show (default 5)"},
        }, self.handle_recent)

        self.app.event_bus.subscribe("awareness_struggle", self._on_struggle)

        logger.info("[Awareness] plugin loaded (service %s)",
                    "enabled" if self._service._enabled else "disabled — opt-in required")

    def handle_enable(self, text: str, args: dict) -> str:
        started = self._service.start()
        if started:
            return "Awareness mode enabled. I'll watch your screen and nudge you if you seem stuck."
        return (
            "Awareness mode is disabled in config. "
            "Set awareness.enabled=true in config.yaml and restart to opt in."
        )

    def handle_disable(self, text: str, args: dict) -> str:
        self._service.stop()
        return "Awareness mode disabled."

    def handle_status(self, text: str, args: dict) -> str:
        if self._service._running:
            return (
                f"Awareness mode is running "
                f"(capturing every {self._service._interval_s:.0f}s, "
                f"OCR {'on' if self._service._ocr_enabled else 'off'})."
            )
        return "Awareness mode is not running."

    def handle_recent(self, text: str, args: dict) -> str:
        limit = int(args.get("limit") or 5)
        captures = self._service.recent_captures(limit=limit)
        if not captures:
            return "No recent screen captures."
        lines = [f"Recent captures ({len(captures)}):"]
        for c in captures:
            stuck = f" ⚠ struggle={c['struggle_score']:.2f}" if c["struggle_score"] > 0 else ""
            lines.append(f"  • {c['window_title'] or 'unknown'}{stuck}")
        return "\n".join(lines)

    def _on_struggle(self, payload: dict) -> None:
        suggestion = payload.get("suggestion", "You seem stuck. Want me to help?")
        self.app.event_bus.publish("voice_response", suggestion)
        # Also notify via comms channels if available
        self.app.event_bus.publish("awareness_struggle_notify", payload)
