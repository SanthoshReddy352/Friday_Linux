"""Goals plugin — OKR-style goal hierarchy.

Mirrors jarvis src/goals/{service,rhythm,accountability}.ts + `goals` table.
Adds a 5-level goal hierarchy (objective → key_result → milestone → task →
daily_action) with health tracking, escalation, and morning/evening rhythm.

Tables (via MemoryService facade → ContextStore):
  goals         — id, title, level, parent_id, score, health, status, …
  goal_progress — per-score-change history

Capabilities exposed:
  create_goal      — add a goal to the hierarchy
  update_goal      — advance score / change status
  list_goals       — show active goals (optionally filtered by level/health)
  get_goal_detail  — deep-dive on a single goal
  complete_goal    — mark a goal done
  pause_goal       — pause a goal

Rhythm:
  GoalRhythmService starts two daemon threads at boot:
  - Morning check-in (configurable hour, default 08:00)
  - Evening review  (configurable hour, default 21:00)
  Both publish voice events so FRIDAY can prompt the user.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone

from core.logger import logger
from core.plugin_manager import FridayPlugin


VALID_LEVELS = ("objective", "key_result", "milestone", "task", "daily_action")
VALID_STATUSES = ("active", "paused", "completed", "failed", "draft")
VALID_HORIZONS = ("life", "yearly", "quarterly", "monthly", "weekly", "daily")


def _health_label(score: float) -> str:
    if score >= 0.7:
        return "on_track"
    if score >= 0.4:
        return "at_risk"
    return "behind"


class GoalRhythmService:
    """Fires morning / evening check-in events on a daily rhythm."""

    def __init__(self, event_bus, morning_hour: int = 8, evening_hour: int = 21):
        self._bus = event_bus
        self._morning_hour = morning_hour
        self._evening_hour = evening_hour
        self._stop = threading.Event()

    def start(self) -> None:
        t = threading.Thread(target=self._loop, daemon=True, name="goals-rhythm")
        t.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        last_morning = -1
        last_evening = -1
        while not self._stop.is_set():
            now = datetime.now()
            day = now.date().toordinal()
            hour = now.hour
            if hour == self._morning_hour and day != last_morning:
                last_morning = day
                self._bus.publish("goal_morning_checkin", {"hour": hour})
                logger.info("[goals] morning check-in fired")
            if hour == self._evening_hour and day != last_evening:
                last_evening = day
                self._bus.publish("goal_evening_review", {"hour": hour})
                logger.info("[goals] evening review fired")
            self._stop.wait(60)  # check every minute


class GoalsPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "Goals"
        self._rhythm = GoalRhythmService(app.event_bus)
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "create_goal",
            "description": (
                "Create a new goal in the OKR hierarchy. "
                "Levels: objective, key_result, milestone, task, daily_action. "
                "Time horizons: life, yearly, quarterly, monthly, weekly, daily."
            ),
            "parameters": {
                "title": "string – goal title",
                "description": "string – optional description",
                "level": "string – one of objective/key_result/milestone/task/daily_action",
                "parent_id": "string – optional parent goal ID",
                "time_horizon": "string – one of life/yearly/quarterly/monthly/weekly/daily",
                "tags": "array[string] – optional tags",
            },
        }, self.handle_create)

        self.app.router.register_tool({
            "name": "update_goal",
            "description": "Advance a goal's score (0.0-1.0) or update its status.",
            "parameters": {
                "goal_id": "string – goal to update",
                "score": "number – new score between 0.0 and 1.0",
                "note": "string – optional progress note",
                "status": "string – optional new status",
            },
        }, self.handle_update)

        self.app.router.register_tool({
            "name": "list_goals",
            "description": "List active goals, optionally filtered by level or health.",
            "parameters": {
                "status": "string – filter by status (default: active)",
                "level": "string – optional level filter",
                "health": "string – optional health filter (on_track/at_risk/behind)",
            },
        }, self.handle_list)

        self.app.router.register_tool({
            "name": "get_goal_detail",
            "description": "Get detailed information about a specific goal including progress history.",
            "parameters": {"goal_id": "string – goal ID to detail"},
        }, self.handle_detail)

        self.app.router.register_tool({
            "name": "complete_goal",
            "description": "Mark a goal as completed.",
            "parameters": {"goal_id": "string – goal ID to complete"},
        }, self.handle_complete)

        self.app.router.register_tool({
            "name": "pause_goal",
            "description": "Pause a goal temporarily.",
            "parameters": {"goal_id": "string – goal ID to pause"},
        }, self.handle_pause)

        # Subscribe to rhythm events to prompt the user
        self.app.event_bus.subscribe("goal_morning_checkin", self._morning)
        self.app.event_bus.subscribe("goal_evening_review", self._evening)

        self._rhythm.start()
        logger.info("[Goals] plugin loaded")

    def _memory(self):
        return getattr(self.app, "memory_service", self.app.context_store)

    def handle_create(self, text: str, args: dict) -> str:
        title = (args.get("title") or text or "").strip()
        if not title:
            return "Please provide a goal title."
        level = args.get("level") or "task"
        if level not in VALID_LEVELS:
            level = "task"
        horizon = args.get("time_horizon") or "weekly"
        if horizon not in VALID_HORIZONS:
            horizon = "weekly"
        tags_raw = args.get("tags") or []
        tags = tags_raw if isinstance(tags_raw, list) else [str(tags_raw)]
        goal_id = self._memory().create_goal(
            title=title,
            description=args.get("description") or "",
            level=level,
            parent_id=args.get("parent_id") or "",
            time_horizon=horizon,
            tags=tags,
            session_id=self.app.session_id,
        )
        return f"Goal created: '{title}' [{level}] — ID: {goal_id[:8]}"

    def handle_update(self, text: str, args: dict) -> str:
        goal_id = args.get("goal_id", "").strip()
        if not goal_id:
            return "Please specify a goal_id."
        score_raw = args.get("score")
        status_raw = args.get("status", "").strip()
        updated = []
        if score_raw is not None:
            try:
                score = max(0.0, min(1.0, float(score_raw)))
                note = args.get("note") or ""
                self._memory().update_goal_score(goal_id, score, note=note)
                updated.append(f"score → {score:.0%} ({_health_label(score)})")
            except (ValueError, TypeError):
                return "Invalid score — must be 0.0–1.0."
        if status_raw in VALID_STATUSES:
            self._memory().update_goal_status(goal_id, status_raw)
            updated.append(f"status → {status_raw}")
        if not updated:
            return "Nothing to update — provide score or status."
        return f"Goal {goal_id[:8]} updated: {', '.join(updated)}."

    def handle_list(self, text: str, args: dict) -> str:
        status = args.get("status") or "active"
        goals = self._memory().list_goals(
            session_id=self.app.session_id, status=status
        )
        if not goals:
            return f"No {status} goals."
        level_filter = (args.get("level") or "").strip()
        health_filter = (args.get("health") or "").strip()
        if level_filter:
            goals = [g for g in goals if g.get("level") == level_filter]
        if health_filter:
            goals = [g for g in goals if g.get("health") == health_filter]
        if not goals:
            return "No goals match the filters."
        lines = [f"Goals ({len(goals)}):"]
        for g in goals:
            score_pct = int(g.get("score", 0) * 100)
            lines.append(
                f"  [{g['level']}] {g['title']} — {score_pct}% "
                f"({g.get('health','?')}) | {g['id'][:8]}"
            )
        return "\n".join(lines)

    def handle_detail(self, text: str, args: dict) -> str:
        goal_id = args.get("goal_id", "").strip()
        if not goal_id:
            return "Please specify a goal_id."
        goal = self._memory().get_goal(goal_id)
        if not goal:
            return f"Goal '{goal_id}' not found."
        lines = [
            f"Goal: {goal['title']}",
            f"  Level: {goal['level']} | Horizon: {goal['time_horizon']}",
            f"  Score: {int(goal['score'] * 100)}% | Health: {goal['health']}",
            f"  Status: {goal['status']} | Escalation: {goal.get('escalation_stage', 'none')}",
            f"  ID: {goal['id']}",
        ]
        if goal.get("parent_id"):
            lines.append(f"  Parent: {goal['parent_id'][:8]}")
        return "\n".join(lines)

    def handle_complete(self, text: str, args: dict) -> str:
        goal_id = args.get("goal_id", "").strip()
        if not goal_id:
            return "Please specify a goal_id."
        self._memory().update_goal_score(goal_id, 1.0, note="completed")
        self._memory().update_goal_status(goal_id, "completed")
        return f"Goal {goal_id[:8]} marked as completed."

    def handle_pause(self, text: str, args: dict) -> str:
        goal_id = args.get("goal_id", "").strip()
        if not goal_id:
            return "Please specify a goal_id."
        self._memory().update_goal_status(goal_id, "paused")
        return f"Goal {goal_id[:8]} paused."

    def _morning(self, payload: dict) -> None:
        goals = self._memory().list_goals(session_id=self.app.session_id, status="active")
        at_risk = [g for g in goals if g.get("health") in ("at_risk", "behind")]
        msg = "Good morning! Time to review your goals."
        if at_risk:
            msg += f" You have {len(at_risk)} goal(s) that need attention."
        self.app.event_bus.publish("voice_response", msg)

    def _evening(self, payload: dict) -> None:
        goals = self._memory().list_goals(session_id=self.app.session_id, status="active")
        msg = f"Evening check-in. You have {len(goals)} active goal(s). How did today go?"
        self.app.event_bus.publish("voice_response", msg)
