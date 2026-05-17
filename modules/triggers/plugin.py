"""Trigger manager plugin — registers, starts, and stops all configured triggers.

Capabilities exposed:
  add_cron_trigger         — schedule a repeating trigger
  add_file_watch_trigger   — watch a path for changes
  add_clipboard_trigger    — fire when clipboard changes
  remove_trigger           — stop and remove a trigger by ID
  list_triggers            — show active triggers

Trigger events are published to EventBus as `trigger_fired` payloads.
WorkflowOrchestrator subscribes to these to drive workflow execution.
"""
from __future__ import annotations

import json

from core.logger import logger
from core.plugin_manager import FridayPlugin
from .cron import CronTrigger
from .file_watch import FileWatchTrigger
from .clipboard import ClipboardTrigger


class TriggerManagerPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "TriggerManager"
        self._triggers: dict[str, object] = {}
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "add_cron_trigger",
            "description": "Schedule a repeating trigger that fires every N seconds.",
            "parameters": {
                "trigger_id": "string – unique ID for this trigger",
                "name": "string – human-readable name",
                "interval_seconds": "number – how often to fire",
            },
        }, self.handle_add_cron)

        self.app.router.register_tool({
            "name": "add_file_watch_trigger",
            "description": "Watch a file or directory for changes and fire an event when anything changes.",
            "parameters": {
                "trigger_id": "string – unique ID for this trigger",
                "name": "string – human-readable name",
                "path": "string – path to watch (supports ~)",
            },
        }, self.handle_add_file_watch)

        self.app.router.register_tool({
            "name": "add_clipboard_trigger",
            "description": "Monitor the clipboard and fire an event when its content changes.",
            "parameters": {
                "trigger_id": "string – unique ID for this trigger",
                "name": "string – human-readable name",
            },
        }, self.handle_add_clipboard)

        self.app.router.register_tool({
            "name": "remove_trigger",
            "description": "Stop and remove an active trigger.",
            "parameters": {"trigger_id": "string – the trigger to remove"},
        }, self.handle_remove)

        self.app.router.register_tool({
            "name": "list_triggers",
            "description": "List all currently active triggers.",
            "parameters": {},
        }, self.handle_list)

        # Subscribe to trigger_fired events so they can be forwarded to workflows
        self.app.event_bus.subscribe("trigger_fired", self._on_trigger_fired)

        logger.info("[TriggerManager] loaded")

    def _on_trigger_fired(self, payload: dict) -> None:
        logger.info(
            "[trigger_fired] %s / %s",
            payload.get("name"), payload.get("trigger_type"),
        )
        # WorkflowOrchestrator may subscribe separately; also emit to HUD
        self.app.event_bus.publish("assistant_progress", {
            "text": f"Trigger fired: {payload.get('name', 'unknown')}",
            "turn_id": "",
        })

    def handle_add_cron(self, text: str, args: dict) -> str:
        tid = args.get("trigger_id") or "cron_default"
        name = args.get("name") or tid
        interval = float(args.get("interval_seconds") or 60)
        self._add(CronTrigger(tid, name, interval, self.app.event_bus))
        return f"Cron trigger '{name}' scheduled every {interval}s."

    def handle_add_file_watch(self, text: str, args: dict) -> str:
        tid = args.get("trigger_id") or "file_watch"
        name = args.get("name") or tid
        path = args.get("path") or "~/Documents"
        self._add(FileWatchTrigger(tid, name, path, self.app.event_bus))
        return f"File watch trigger '{name}' watching {path}."

    def handle_add_clipboard(self, text: str, args: dict) -> str:
        tid = args.get("trigger_id") or "clipboard"
        name = args.get("name") or tid
        self._add(ClipboardTrigger(tid, name, self.app.event_bus))
        return f"Clipboard trigger '{name}' started."

    def handle_remove(self, text: str, args: dict) -> str:
        tid = args.get("trigger_id", "")
        trigger = self._triggers.pop(tid, None)
        if trigger is None:
            return f"No trigger with ID '{tid}'."
        trigger.stop()
        return f"Trigger '{tid}' stopped."

    def handle_list(self, text: str, args: dict) -> str:
        if not self._triggers:
            return "No active triggers."
        lines = [f"Active triggers ({len(self._triggers)}):"]
        for tid, t in self._triggers.items():
            lines.append(f"  • {t.name} [{t.trigger_type}] id={tid}")
        return "\n".join(lines)

    def _add(self, trigger) -> None:
        old = self._triggers.pop(trigger.trigger_id, None)
        if old is not None:
            old.stop()
        self._triggers[trigger.trigger_id] = trigger
        trigger.start()

    def stop_all(self) -> None:
        for t in list(self._triggers.values()):
            try:
                t.stop()
            except Exception:
                pass
        self._triggers.clear()
