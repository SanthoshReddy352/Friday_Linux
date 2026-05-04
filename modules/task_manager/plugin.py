import re
import threading
import sqlite3
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from core.plugin_manager import FridayPlugin
from core.logger import logger


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "friday.db")
REMINDER_WORKFLOW = "reminder_workflow"
TIME_RE = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap])\s*\.?\s*m\.?\b", re.IGNORECASE)
TIME_24H_RE = re.compile(r"\b(?:at\s+)?([01]?\d|2[0-3]):([0-5]\d)\b", re.IGNORECASE)
TIME_SPOKEN_RE = re.compile(r"\b(?:at\s+)?([01]?\d|2[0-3])\s+([0-5]\d)\b", re.IGNORECASE)
TIME_BARE_AT_RE = re.compile(r"\bat\s+([1-9]|1[0-2])\b", re.IGNORECASE)
TIME_COMPACT_RE = re.compile(r"(?:^|\bat\s+)(\d{3,4})\b", re.IGNORECASE)
RELATIVE_RE = re.compile(r"\bin\s+(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?|days?)\b", re.IGNORECASE)
DATE_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
MINUTE_WORDS = {
    "oh": 0,
    "zero": 0,
    "five": 5,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}
MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled',
            created_at TEXT NOT NULL,
            fired_at TEXT
        )
    """)
    conn.commit()
    conn.close()


class TaskManagerPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "TaskManager"
        self._reminder_timers = {}
        self._system_notification_event_ids = set()
        self.app.task_manager = self
        _ensure_db()
        self.on_load()
        self._cleanup_completed_calendar_events()
        self._load_pending_calendar_events()

    def on_load(self):
        self.app.router.register_tool({
            "name": "set_reminder",
            "description": (
                "Set a reminder or calendar event that FRIDAY will announce at a specified date and time. "
                "Examples: 'remind me to call John in 5 minutes', "
                "'remind me to purchase a gift tomorrow at 5 PM'."
            ),
            "parameters": {
                "message": "string – what to remind the user about",
                "minutes": "integer – optional number of minutes from now to trigger the reminder",
                "datetime": "string – optional exact or natural date and time for the reminder"
            }
        }, self.handle_set_reminder)

        self.app.router.register_tool({
            "name": "save_note",
            "description": "Save a quick note or piece of text for later retrieval.",
            "parameters": {
                "content": "string – the text content to save as a note"
            }
        }, self.handle_save_note)

        self.app.router.register_tool({
            "name": "read_notes",
            "description": "Read back the most recent saved notes.",
            "parameters": {}
        }, self.handle_read_notes)

        self.app.router.register_tool({
            "name": "create_calendar_event",
            "description": (
                "Create a calendar event or scheduled reminder for a specific date and time. "
                "Use when the user says things like 'create a calendar event titled standup tomorrow at 10', "
                "'schedule a meeting on Friday at 3pm', or 'add an event called dinner tonight at 8'."
            ),
            "parameters": {
                "title": "string – event title",
                "datetime": "string – ISO timestamp or natural-language date and time",
                "minutes": "integer – minutes from now",
            },
            "context_terms": ["create calendar event", "add calendar event", "schedule event", "schedule meeting", "add to calendar"],
        }, self.handle_create_calendar_event)

        self.app.router.register_tool({
            "name": "move_calendar_event",
            "description": (
                "Reschedule a previously-scheduled reminder or calendar event to a new date/time. "
                "Use for 'move my 3 PM to 4', 'reschedule the standup to tomorrow morning', "
                "'shift the gym block by 2 hours'."
            ),
            "parameters": {
                "title": "string – partial title of the event to move (or 'next')",
                "datetime": "string – new ISO timestamp or natural-language date and time",
                "minutes": "integer – minutes from now",
            },
            "context_terms": ["move event", "reschedule", "shift event", "change time"],
        }, self.handle_move_calendar_event)

        self.app.router.register_tool({
            "name": "cancel_calendar_event",
            "description": (
                "Cancel or delete a previously scheduled reminder/calendar event by title or by saying 'the next one'."
            ),
            "parameters": {
                "title": "string – partial title of the event to cancel",
            },
            "context_terms": ["cancel reminder", "delete reminder", "cancel calendar event", "remove event"],
        }, self.handle_cancel_calendar_event)

        self.app.router.register_tool({
            "name": "list_calendar_events",
            "description": "Read upcoming reminders and calendar events with their scheduled date and time.",
            "parameters": {
                "limit": "integer – optional number of upcoming events to read"
            },
            "aliases": ["calendar events", "upcoming reminders", "my reminders", "agenda", "today's events"],
            "patterns": [
                r"\b(?:what(?:'s| is)?|read|show|list|brief)\s+(?:my\s+)?(?:calendar|agenda|events|reminders)\b",
                r"\b(?:upcoming|scheduled)\s+(?:events|reminders)\b",
            ],
            "context_terms": ["calendar", "agenda", "events", "reminders", "schedule", "briefing"],
        }, self.handle_list_calendar_events)

        self.app.router.register_tool({
            "name": "get_time",
            "description": "Tell the user the current local time.",
            "parameters": {}
        }, lambda t, a: self._get_time())

        self.app.router.register_tool({
            "name": "get_date",
            "description": "Tell the user today's date.",
            "parameters": {}
        }, lambda t, a: self._get_date())

        logger.info("TaskManagerPlugin loaded.")

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    def handle_set_reminder(self, text, args):
        parsed = self._parse_reminder_request(text, args)
        return self._handle_reminder_parts(parsed)

    def handle_reminder_followup(self, text, workflow_state):
        target = dict((workflow_state or {}).get("target") or {})
        pending_slots = set((workflow_state or {}).get("pending_slots") or [])
        parsed = self._parse_datetime_parts(text, allow_bare_time="time" in pending_slots)
        if "date" not in parsed and target.get("date"):
            parsed["date"] = target.get("date")
        if "time" not in parsed and target.get("time"):
            parsed["time"] = target.get("time")
        if "remind_at" not in parsed and target.get("remind_at"):
            parsed["remind_at"] = self._parse_iso_datetime(target.get("remind_at"))
        parsed["message"] = target.get("message", "")
        return self._handle_reminder_parts(parsed)

    def _handle_reminder_parts(self, parsed):
        message = str(parsed.get("message") or "").strip()
        if not message:
            return "What would you like me to remind you about?"

        remind_at = parsed.get("remind_at") or self._combine_date_time(parsed.get("date"), parsed.get("time"))
        if remind_at:
            if remind_at <= datetime.now():
                return "That time has already passed. Please mention a future date and time."
            self._clear_reminder_workflow()
            event_id = self._create_calendar_event(message, remind_at)
            return self._format_confirmation(message, remind_at, event_id)

        missing = []
        if not parsed.get("date"):
            missing.append("date")
        if not parsed.get("time"):
            missing.append("time")
        self._save_reminder_workflow(message, parsed, missing)

        if missing == ["date", "time"]:
            return "When should I remind you? Please mention the date and time to remind you."
        if missing == ["time"]:
            return "What time should I remind you?"
        if missing == ["date"]:
            return "What date should I remind you?"
        return "Please mention the date and time to remind you."

    def handle_create_calendar_event(self, text, args):
        args = dict(args or {})
        raw_text = str(text or "")
        title = str(args.get("title") or "").strip() or self._extract_event_title(raw_text)
        if not title:
            return "What should I title the event?"

        parsed = self._parse_datetime_parts(
            " ".join(part for part in [raw_text, str(args.get("datetime") or "")] if part)
        )
        minutes = args.get("minutes")
        if minutes is not None and not parsed.get("remind_at"):
            try:
                parsed["remind_at"] = datetime.now() + timedelta(minutes=float(minutes))
            except Exception:
                pass

        remind_at = parsed.get("remind_at") or self._combine_date_time(parsed.get("date"), parsed.get("time"))
        if not remind_at:
            return f"When should '{title}' be scheduled? Tell me a date and time."
        if remind_at <= datetime.now():
            return "That time has already passed. Please mention a future date and time."

        ok, payload = self.create_calendar_event(title, remind_at)
        if not ok:
            return payload if isinstance(payload, str) else "I couldn't create that event."
        return self._format_confirmation(title, remind_at, payload.get("id"))

    def handle_move_calendar_event(self, text, args):
        args = dict(args or {})
        raw_text = str(text or "")
        target = (args.get("title") or "").strip().lower() or self._extract_move_target(raw_text)

        events = [event for event in self.list_calendar_events(limit=50) if event.get("status") == "scheduled"]
        now = datetime.now()
        upcoming = []
        for event in events:
            remind_at = self._parse_iso_datetime(event.get("remind_at"))
            if remind_at and remind_at >= now:
                upcoming.append((remind_at, event))
        upcoming.sort(key=lambda item: item[0])
        if not upcoming:
            return "You don't have any upcoming reminders to move."

        chosen = None
        if target in {"", "next", "the next one", "next one", "upcoming"}:
            chosen = upcoming[0]
        else:
            time_target = self._extract_clock_target(target)
            for remind_at, event in upcoming:
                if target and target in (event.get("title") or "").lower():
                    chosen = (remind_at, event)
                    break
                if time_target is not None:
                    if remind_at.hour == time_target[0] and remind_at.minute == time_target[1]:
                        chosen = (remind_at, event)
                        break
        if chosen is None:
            return f"I couldn't find a reminder matching '{target}'."

        old_remind_at, event = chosen

        new_remind_at = self._parse_move_target_time(raw_text, args, old_remind_at)
        if new_remind_at is None:
            return f"When should I move '{event.get('title', 'that')}' to?"
        if new_remind_at <= datetime.now():
            return "That time has already passed. Please pick a future time."

        ok, reschedule_message = self._reschedule_calendar_event(event, new_remind_at)
        if not ok:
            return reschedule_message
        return (
            f"Moved '{event.get('title', 'reminder')}' from {self._format_event_time(old_remind_at)} "
            f"to {self._format_event_time(new_remind_at)}."
        )

    def _extract_move_target(self, text):
        for pattern in (
            r"\b(?:move|reschedule|shift|push|change)\s+(?:the\s+|my\s+)?(.+?)\s+(?:to|by|until|forward|back|ahead)\b",
            r"\b(?:move|reschedule|shift|push)\s+(?:the\s+)?(next|upcoming)\b",
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip(" .!?").lower()
        return ""

    def _extract_clock_target(self, text):
        match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text, re.IGNORECASE)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = (match.group(3) or "").lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        return hour, minute

    def _parse_move_target_time(self, raw_text, args, anchor):
        # Direct datetime string from args wins.
        explicit = str(args.get("datetime") or "").strip()
        if explicit:
            parsed = self._parse_iso_datetime(explicit)
            if parsed:
                return parsed

        minutes = args.get("minutes")
        if minutes is not None:
            try:
                return datetime.now() + timedelta(minutes=float(minutes))
            except Exception:
                pass

        lowered = raw_text.lower()

        # "shift X by N minutes/hours"
        shift_match = re.search(
            r"\bby\s+(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)\b",
            lowered,
        )
        if shift_match:
            amount = float(shift_match.group(1))
            unit = shift_match.group(2).lower()
            delta = timedelta(minutes=amount) if unit.startswith("min") else timedelta(hours=amount)
            if re.search(r"\bback\b|\bearlier\b", lowered):
                return anchor - delta
            return anchor + delta

        # "to N pm" / "to 4" — keep the original date, change the clock time.
        to_match = re.search(
            r"\bto\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?(?!\w)",
            lowered,
        )
        if to_match:
            hour = int(to_match.group(1))
            minute = int(to_match.group(2) or 0)
            meridiem = (to_match.group(3) or "").lower()
            if not meridiem and 1 <= hour <= 7:
                # Voice "to 4" usually means PM if the original was PM.
                if anchor.hour >= 12:
                    hour += 12
            elif meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            return anchor.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # Full "to <natural date>" — let the date/time parser try.
        parsed = self._parse_datetime_parts(raw_text)
        candidate = parsed.get("remind_at") or self._combine_date_time(
            parsed.get("date"), parsed.get("time")
        )
        return candidate

    def _reschedule_calendar_event(self, event, new_remind_at):
        try:
            event_id = int(event.get("id"))
        except Exception:
            return False, "I couldn't identify that reminder to move."

        timer = self._reminder_timers.pop(event_id, None)
        if timer:
            timer.cancel()
        self._cancel_system_notification(event_id)

        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "UPDATE calendar_events SET remind_at = ? WHERE id = ?",
                (new_remind_at.isoformat(timespec="seconds"), event_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("[TaskManager] Failed to reschedule reminder %s: %s", event_id, exc)
            return False, "I couldn't reschedule that reminder."

        title = event.get("title") or ""
        if self._schedule_system_notification(event_id, title, new_remind_at):
            self._system_notification_event_ids.add(event_id)
        self._schedule_calendar_timer(event_id, title, new_remind_at)
        self.app.event_bus.publish(
            "calendar_event_updated",
            {
                "id": event_id,
                "title": title,
                "remind_at": new_remind_at.isoformat(timespec="seconds"),
                "status": "scheduled",
            },
        )
        return True, ""

    def handle_cancel_calendar_event(self, text, args):
        args = dict(args or {})
        raw_text = str(text or "")
        target = (args.get("title") or "").strip().lower() or self._extract_cancel_target(raw_text)
        events = [event for event in self.list_calendar_events(limit=50) if event.get("status") == "scheduled"]
        if not events:
            return "You don't have any scheduled reminders to cancel."

        upcoming = []
        now = datetime.now()
        for event in events:
            remind_at = self._parse_iso_datetime(event.get("remind_at"))
            if remind_at and remind_at >= now:
                upcoming.append((remind_at, event))
        upcoming.sort(key=lambda item: item[0])
        if not upcoming:
            return "There are no upcoming reminders to cancel."

        chosen = None
        if target in {"", "next", "the next one", "next one", "upcoming"}:
            chosen = upcoming[0][1]
        else:
            for _, event in upcoming:
                if target in (event.get("title") or "").lower():
                    chosen = event
                    break
        if chosen is None:
            return f"I couldn't find a reminder matching '{target}'."

        ok, message = self.delete_calendar_event(chosen.get("id"))
        if not ok:
            return message if isinstance(message, str) else "I couldn't cancel that reminder."
        return f"Cancelled '{chosen.get('title', 'that reminder')}'."

    def _extract_event_title(self, text):
        for pattern in (
            r"\b(?:create|add|schedule|set\s+up|book)\s+(?:a\s+|an\s+)?(?:calendar\s+)?(?:event|meeting|reminder|appointment)\s+(?:titled|called|named)\s+(.+)",
            r"\b(?:create|add|schedule|set\s+up|book)\s+(?:a\s+|an\s+)?(?:calendar\s+)?(?:event|meeting|reminder|appointment)\s+(?:for\s+|to\s+)?(.+)",
            r"\b(?:add\s+to\s+(?:my\s+)?calendar)\s*[:\-]?\s*(.+)",
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            title = match.group(1).strip(" .!?")
            title = self._strip_temporal_suffix(title)
            if title:
                return title
        return ""

    def _extract_cancel_target(self, text):
        for pattern in (
            r"\b(?:cancel|delete|remove|drop)\s+(?:the\s+|my\s+)?(?:event|reminder|meeting|appointment)\s+(?:titled|called|named|for|about)\s+(.+)",
            r"\b(?:cancel|delete|remove|drop)\s+(?:the\s+|my\s+)?(.+?)\s+(?:event|reminder|meeting|appointment)",
            r"\b(?:cancel|delete|remove|drop)\s+(?:the\s+)?(next|upcoming)\s+(?:event|reminder|meeting|appointment)?",
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1).strip(" .!?").lower()
                return self._strip_temporal_suffix(value)
        return ""

    def _strip_temporal_suffix(self, text):
        if not text:
            return text
        cleaned = text
        for pattern in (
            r"\s+\bin\s+\d+(?:\.\d+)?\s*(?:minutes?|mins?|hours?|hrs?|days?)\b.*$",
            r"\s+\b(?:today|tomorrow|tonight)\b.*$",
            r"\s+\bat\s+\d.*$",
            r"\s+\bon\s+\d.*$",
            r"\s+\bon\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*$",
            r"\s+\bnext\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|week)\b.*$",
            r"\s+\bfrom\s+\d.*$",
        ):
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip(" .!?")

    def handle_save_note(self, text, args):
        content = args.get("content", "").strip()
        if not content:
            # Try to extract from raw text after "save note:" or "note:"
            match = re.search(r'(?:save\s+note|note|remember)[:\s]+(.+)', text, re.IGNORECASE)
            content = match.group(1).strip() if match else ""
        if not content:
            return "What would you like me to note down?"

        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                "INSERT INTO notes (content, created_at) VALUES (?, ?)",
                (content, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()
            logger.info(f"[TaskManager] Note saved: '{content[:50]}'")
            return f"Note saved: \"{content}\""
        except Exception as e:
            logger.error(f"[TaskManager] Failed to save note: {e}")
            return "I couldn't save that note. Please try again."

    def handle_read_notes(self, text, args):
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT content, created_at FROM notes ORDER BY id DESC LIMIT 5"
            ).fetchall()
            conn.close()

            if not rows:
                return "You don't have any saved notes yet."

            lines = ["Here are your recent notes:"]
            for i, (content, created_at) in enumerate(rows, 1):
                # Format: "Apr 12, 01:30"
                try:
                    dt = datetime.fromisoformat(created_at)
                    time_str = dt.strftime("%b %d, %H:%M")
                except Exception:
                    time_str = created_at[:16]
                lines.append(f"{i}. [{time_str}] {content}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[TaskManager] Failed to read notes: {e}")
            return "I couldn't retrieve your notes right now."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fire_reminder(self, message):
        logger.info(f"[TaskManager] Firing reminder: '{message}'")
        response = f"Reminder: {message}"
        self.app.emit_assistant_message(f"⏰ {response}", source="reminder", spoken_text=response)

    def _fire_calendar_event(self, event_id, message):
        logger.info("[TaskManager] Firing calendar event %s: '%s'", event_id, message)
        self._reminder_timers.pop(int(event_id), None)
        fired_at = datetime.now().isoformat(timespec="seconds")
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("[TaskManager] Failed to remove completed event: %s", exc)
        payload = {"id": event_id, "title": message, "fired_at": fired_at}
        self.app.event_bus.publish("calendar_event_fired", payload)
        if event_id not in self._system_notification_event_ids:
            self._send_desktop_notification("FRIDAY Reminder", message)
        response = f"Reminder: {message}"
        self.app.emit_assistant_message(f"⏰ {response}", source="reminder", spoken_text=response)

    def _parse_reminder_text(self, text):
        """Extract message and minutes from natural language fallback."""
        text_lower = text.lower()
        # Extract minutes: "in X minutes" or "in X min"
        min_match = re.search(r'in\s+(\d+(?:\.\d+)?)\s+(?:minutes?|mins?)', text_lower)
        minutes = float(min_match.group(1)) if min_match else None

        # Extract the reminder subject
        # Pattern: "remind me to <X> in N minutes" → capture <X>
        msg_match = re.search(
            r'remind\s+(?:me\s+)?(?:to\s+)?(.+?)(?:\s+in\s+\d+\s+(?:minutes?|mins?))?$',
            text_lower
        )
        message = msg_match.group(1).strip() if msg_match else ""
        # Clean up trailing "in X min" if it leaked into the message
        message = re.sub(r'\s+in\s+\d+\s+(?:minutes?|mins?)$', '', message).strip()

        return message, minutes

    def _parse_reminder_request(self, text, args=None):
        args = dict(args or {})
        raw_text = str(text or "")
        message = str(args.get("message") or "").strip() or self._extract_reminder_message(raw_text)
        parsed = self._parse_datetime_parts(" ".join(part for part in [raw_text, str(args.get("datetime") or "")] if part))
        minutes = args.get("minutes")
        if minutes is not None and not parsed.get("remind_at"):
            try:
                parsed["remind_at"] = datetime.now() + timedelta(minutes=float(minutes))
            except Exception:
                pass
        parsed["message"] = message
        return parsed

    def _parse_datetime_parts(self, text, allow_bare_time=False):
        text = str(text or "")
        lowered = text.lower()
        parsed = {}

        relative = RELATIVE_RE.search(lowered)
        if relative:
            amount = float(relative.group(1))
            unit = relative.group(2).lower()
            if unit.startswith(("minute", "min")):
                delta = timedelta(minutes=amount)
            elif unit.startswith(("hour", "hr")):
                delta = timedelta(hours=amount)
            else:
                delta = timedelta(days=amount)
            parsed["remind_at"] = datetime.now() + delta
            return parsed

        date_value = self._parse_date(lowered)
        if date_value:
            parsed["date"] = date_value.isoformat()
        time_value = self._parse_time(lowered, allow_bare=allow_bare_time)
        if time_value:
            parsed["time"] = f"{time_value[0]:02d}:{time_value[1]:02d}"
        return parsed

    def _parse_date(self, lowered):
        today = datetime.now().date()
        if re.search(r"\btoday\b", lowered):
            return today
        if re.search(r"\btomorrow\b", lowered):
            return today + timedelta(days=1)

        iso = ISO_DATE_RE.search(lowered)
        if iso:
            try:
                return datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))).date()
            except ValueError:
                return None

        numeric = DATE_NUMERIC_RE.search(lowered)
        if numeric:
            day = int(numeric.group(1))
            month = int(numeric.group(2))
            year = int(numeric.group(3) or today.year)
            if year < 100:
                year += 2000
            try:
                candidate = datetime(year, month, day).date()
                if candidate < today and numeric.group(3) is None:
                    candidate = datetime(year + 1, month, day).date()
                return candidate
            except ValueError:
                return None

        month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
        month_first = re.search(rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b", lowered)
        if month_first:
            return self._date_from_month_match(month_first.group(2), month_first.group(1), month_first.group(3), today)
        day_first = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})(?:,?\s+(\d{{4}}))?\b", lowered)
        if day_first:
            return self._date_from_month_match(day_first.group(1), day_first.group(2), day_first.group(3), today)

        next_prefix = "next " in lowered
        for name, index in WEEKDAYS.items():
            if re.search(rf"\b(?:next\s+)?{re.escape(name)}\b", lowered):
                days_ahead = (index - today.weekday()) % 7
                if days_ahead == 0 or next_prefix:
                    days_ahead += 7
                return today + timedelta(days=days_ahead)
        return None

    def _date_from_month_match(self, day_text, month_text, year_text, today):
        try:
            day = int(day_text)
            month = MONTHS[month_text.lower()]
            year = int(year_text or today.year)
            candidate = datetime(year, month, day).date()
            if candidate < today and not year_text:
                candidate = datetime(year + 1, month, day).date()
            return candidate
        except Exception:
            return None

    def _parse_time(self, lowered, allow_bare=False):
        match = TIME_RE.search(lowered)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            meridian = match.group(3).lower()
            if meridian == "p" and hour != 12:
                hour += 12
            if meridian == "a" and hour == 12:
                hour = 0
            return hour, minute
        match = TIME_24H_RE.search(lowered)
        if match:
            return int(match.group(1)), int(match.group(2))
        match = TIME_SPOKEN_RE.search(lowered)
        if match:
            return int(match.group(1)), int(match.group(2))
        match = TIME_BARE_AT_RE.search(lowered)
        if match:
            return int(match.group(1)), 0
        match = TIME_COMPACT_RE.search(lowered.strip())
        if match:
            digits = match.group(1)
            hour = int(digits[:-2])
            minute = int(digits[-2:])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
        if allow_bare:
            match = re.search(r"\b([1-9]|1[0-2])\b", lowered)
            if match:
                return int(match.group(1)), 0
        word_time = self._parse_word_time(lowered, allow_bare=allow_bare)
        if word_time:
            return word_time
        return None

    def _parse_word_time(self, lowered, allow_bare=False):
        hour_words = "|".join(NUMBER_WORDS)
        minute_words = "|".join(MINUTE_WORDS)
        match = re.search(
            rf"\b(?:at\s+)?({hour_words})\s+({minute_words})(?:\s+([ap])\s*\.?\s*m\.?)?\b",
            lowered,
        )
        if match:
            hour = NUMBER_WORDS[match.group(1)]
            minute = MINUTE_WORDS[match.group(2)]
            meridian = (match.group(3) or "").lower()
            return self._apply_meridian(hour, minute, meridian)

        match = re.search(rf"\b(?:at\s+)?({hour_words})(?:\s+o\s+clock|\s+oclock)\b", lowered)
        if match:
            hour = NUMBER_WORDS[match.group(1)]
            return hour, 0

        match = re.search(rf"\b(?:at\s+)?({hour_words})\s+([ap])\s*\.?\s*m\.?\b", lowered)
        if match:
            hour = NUMBER_WORDS[match.group(1)]
            meridian = (match.group(2) or "").lower()
            return self._apply_meridian(hour, 0, meridian)
        if allow_bare:
            match = re.search(rf"^\s*({hour_words})\s*$", lowered)
            if match:
                return NUMBER_WORDS[match.group(1)], 0
        return None

    def _apply_meridian(self, hour, minute, meridian):
        if meridian == "p" and hour != 12:
            hour += 12
        if meridian == "a" and hour == 12:
            hour = 0
        return hour, minute

    def _combine_date_time(self, date_text, time_text):
        if not date_text or not time_text:
            return None
        try:
            candidate = datetime.fromisoformat(f"{date_text}T{time_text}:00")
            now = datetime.now()
            if candidate.date() == now.date() and candidate <= now and 1 <= candidate.hour <= 11:
                candidate = candidate + timedelta(hours=12)
            return candidate
        except Exception:
            return None

    def _parse_iso_datetime(self, value):
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    def _extract_reminder_message(self, text):
        match = re.search(r"\bremind\s+(?:me\s+)?(?:to\s+|about\s+)?(.+)", text, re.IGNORECASE)
        if not match:
            match = re.search(r"\bset\s+(?:a\s+)?reminder\s+(?:to\s+|about\s+)?(.+)", text, re.IGNORECASE)
        message = match.group(1).strip(" .!?") if match else ""
        if not message:
            return ""
        temporal_markers = (
            r"\s+\bin\s+\d+(?:\.\d+)?\s*(?:minutes?|mins?|hours?|hrs?|days?)\b",
            r"\s+\b(?:today|tomorrow)\b",
            r"\s+\b(?:on|at|by)\s+\d",
            r"\s+\b(?:on|at|by|next)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            r"\s+\b(?:on|at|by)\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
            r"\s+\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
        )
        for pattern in temporal_markers:
            found = re.search(pattern, message, re.IGNORECASE)
            if found:
                message = message[:found.start()].strip(" .!?")
                break
        message = re.sub(r"\s+\b(?:at|on|by|in|for)\b$", "", message, flags=re.IGNORECASE).strip(" .!?")
        return message

    def _memory(self):
        return getattr(self.app, "memory_service", None) or getattr(self.app, "context_store", None)

    def _save_reminder_workflow(self, message, parsed, missing):
        memory = self._memory()
        session_id = getattr(self.app, "session_id", None)
        if not memory or not session_id:
            return
        target = {"message": message}
        for key in ("date", "time"):
            if parsed.get(key):
                target[key] = parsed[key]
        if parsed.get("remind_at"):
            target["remind_at"] = parsed["remind_at"].isoformat(timespec="seconds")
        memory.save_workflow_state(session_id, REMINDER_WORKFLOW, {
            "status": "pending",
            "pending_slots": missing,
            "last_action": "set_reminder",
            "target": target,
            "result_summary": "Waiting for reminder date and time.",
        })

    def _clear_reminder_workflow(self):
        memory = self._memory()
        session_id = getattr(self.app, "session_id", None)
        if memory and session_id:
            memory.clear_workflow_state(session_id, REMINDER_WORKFLOW)

    def _create_calendar_event(self, message, remind_at):
        event_id = self._insert_calendar_event(message, remind_at)
        if self._schedule_system_notification(event_id, message, remind_at):
            self._system_notification_event_ids.add(event_id)
        self._schedule_calendar_timer(event_id, message, remind_at)
        payload = {
            "id": event_id,
            "title": message,
            "remind_at": remind_at.isoformat(timespec="seconds"),
            "status": "scheduled",
        }
        self.app.event_bus.publish("calendar_event_created", payload)
        return event_id

    def create_calendar_event(self, message, remind_at):
        message = str(message or "").strip()
        if not message:
            return False, "Please enter a reminder title."
        if not isinstance(remind_at, datetime):
            return False, "Please choose a valid reminder date and time."
        if remind_at <= datetime.now():
            return False, "Please choose a future date and time."
        event_id = self._create_calendar_event(message, remind_at)
        return True, {
            "id": event_id,
            "title": message,
            "remind_at": remind_at.isoformat(timespec="seconds"),
            "status": "scheduled",
        }

    def delete_calendar_event(self, event_id):
        try:
            event_id = int(event_id)
        except Exception:
            return False, "Please select a reminder to delete."

        timer = self._reminder_timers.pop(event_id, None)
        if timer:
            timer.cancel()
        self._cancel_system_notification(event_id)

        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.execute("DELETE FROM calendar_events WHERE id = ?", (event_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            conn.close()
        except Exception as exc:
            logger.warning("[TaskManager] Failed to delete reminder: %s", exc)
            return False, "I couldn't delete that reminder."

        if not deleted:
            return False, "That reminder was already completed or deleted."
        self.app.event_bus.publish("calendar_event_deleted", {"id": event_id})
        return True, "Reminder deleted."

    def _insert_calendar_event(self, message, remind_at):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute(
            "INSERT INTO calendar_events (title, remind_at, status, created_at) VALUES (?, ?, 'scheduled', ?)",
            (message, remind_at.isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        event_id = int(cursor.lastrowid)
        conn.close()
        return event_id

    def _schedule_calendar_timer(self, event_id, message, remind_at):
        seconds = max(0.1, (remind_at - datetime.now()).total_seconds())
        timer = threading.Timer(seconds, self._fire_calendar_event, args=[event_id, message])
        timer.daemon = True
        timer.start()
        self._reminder_timers[int(event_id)] = timer

    def _load_pending_calendar_events(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT id, title, remind_at FROM calendar_events WHERE status = 'scheduled'"
            ).fetchall()
            conn.close()
        except Exception as exc:
            logger.warning("[TaskManager] Failed to load reminders: %s", exc)
            return
        now = datetime.now()
        for event_id, title, remind_at_text in rows:
            remind_at = self._parse_iso_datetime(remind_at_text)
            if not remind_at:
                continue
            if remind_at <= now:
                self._fire_calendar_event(event_id, title)
            else:
                if self._schedule_system_notification(event_id, title, remind_at):
                    self._system_notification_event_ids.add(event_id)
                self._schedule_calendar_timer(event_id, title, remind_at)

    def _cleanup_completed_calendar_events(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM calendar_events WHERE status != 'scheduled' OR fired_at IS NOT NULL")
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("[TaskManager] Failed to clean completed reminders: %s", exc)

    def list_calendar_events(self, limit=20):
        try:
            conn = sqlite3.connect(DB_PATH)
            rows = conn.execute(
                "SELECT id, title, remind_at, status FROM calendar_events ORDER BY remind_at ASC LIMIT ?",
                (int(limit),),
            ).fetchall()
            conn.close()
            return [
                {"id": row[0], "title": row[1], "remind_at": row[2], "status": row[3]}
                for row in rows
            ]
        except Exception:
            return []

    def handle_list_calendar_events(self, text, args):
        limit = int((args or {}).get("limit") or 5)
        events = [event for event in self.list_calendar_events(limit=50) if event.get("status") == "scheduled"]
        now = datetime.now()
        upcoming = []
        for event in events:
            remind_at = self._parse_iso_datetime(event.get("remind_at"))
            if remind_at and remind_at >= now:
                upcoming.append((remind_at, event))
        upcoming.sort(key=lambda item: item[0])
        if not upcoming:
            return "You don't have any upcoming reminders."

        lines = ["Here are your upcoming reminders:"]
        for remind_at, event in upcoming[:max(1, limit)]:
            lines.append(f"{self._format_event_time(remind_at)}: {event.get('title', '')}")
        return "\n".join(lines)

    def get_unfinished_task_briefing(self, limit=5):
        events = [event for event in self.list_calendar_events(limit=50) if event.get("status") == "scheduled"]
        now = datetime.now()
        upcoming = []
        for event in events:
            remind_at = self._parse_iso_datetime(event.get("remind_at"))
            if remind_at and remind_at >= now:
                upcoming.append((remind_at, event))
        upcoming.sort(key=lambda item: item[0])
        if not upcoming:
            return "You have no unfinished reminders."

        count = len(upcoming)
        noun = "reminder" if count == 1 else "reminders"
        lines = [f"You have {count} unfinished {noun}."]
        for remind_at, event in upcoming[:max(1, int(limit))]:
            lines.append(f"{self._format_event_time(remind_at)}: {event.get('title', '')}")
        if count > limit:
            lines.append(f"And {count - limit} more.")
        return "\n".join(lines)

    def _format_event_time(self, remind_at):
        today = datetime.now().date()
        if remind_at.date() == today:
            day = "Today"
        elif remind_at.date() == today + timedelta(days=1):
            day = "Tomorrow"
        else:
            day = remind_at.strftime("%A, %B %d, %Y")
        return f"{day} at {remind_at.strftime('%I:%M %p').lstrip('0')}"

    def _send_desktop_notification(self, title, body):
        if os.name == "nt" or not shutil.which("notify-send"):
            return False
        try:
            subprocess.run(
                ["notify-send", "-a", "FRIDAY", "-u", "normal", title, body],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            return True
        except Exception as exc:
            logger.warning("[TaskManager] Desktop notification failed: %s", exc)
            return False

    def _schedule_system_notification(self, event_id, message, remind_at):
        if os.name == "nt" or remind_at <= datetime.now():
            return False
        if not shutil.which("systemd-run") or not shutil.which("notify-send"):
            return False

        unit = f"friday-reminder-{int(event_id)}"
        on_calendar = remind_at.strftime("%Y-%m-%d %H:%M:%S")
        code = (
            "import datetime, sqlite3, subprocess, sys;"
            "db=sys.argv[1]; event_id=int(sys.argv[2]); title=sys.argv[3];"
            "conn=sqlite3.connect(db);"
            "conn.execute('DELETE FROM calendar_events WHERE id = ?', (event_id,));"
            "conn.commit(); conn.close();"
            "subprocess.run(['notify-send', '-a', 'FRIDAY', '-u', 'normal', 'FRIDAY Reminder', title], check=False)"
        )
        command = [
            "systemd-run",
            "--user",
            "--unit",
            unit,
            "--description",
            f"FRIDAY reminder {event_id}",
            "--on-calendar",
            on_calendar,
            "--collect",
            sys.executable,
            "-c",
            code,
            DB_PATH,
            str(event_id),
            str(message),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5, encoding="utf-8", errors="replace")
            if result.returncode == 0:
                logger.info("[TaskManager] Scheduled system notification unit %s for %s", unit, on_calendar)
                return True
            stderr = (result.stderr or result.stdout or "").strip()
            lowered = stderr.lower()
            if "already exists" in lowered or "already loaded" in lowered or "fragment file" in lowered:
                logger.info("[TaskManager] System notification unit %s already exists.", unit)
                return True
            logger.warning("[TaskManager] Failed to schedule system notification: %s", stderr)
            return False
        except Exception as exc:
            logger.warning("[TaskManager] Failed to schedule system notification: %s", exc)
            return False

    def _cancel_system_notification(self, event_id):
        if os.name == "nt" or not shutil.which("systemctl"):
            return
        unit_base = f"friday-reminder-{int(event_id)}"
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", f"{unit_base}.timer", f"{unit_base}.service"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except Exception as exc:
            logger.debug("[TaskManager] Failed to cancel system notification unit %s: %s", unit_base, exc)

    def _format_confirmation(self, message, remind_at, event_id):
        time_str = remind_at.strftime("%I:%M %p").lstrip("0")
        when = remind_at.strftime("%A, %B %d, %Y") + " at " + time_str
        return f"Got it! I'll remind you to {message} on {when}."

    def _get_time(self):
        now = datetime.now()
        return f"The current time is {now.strftime('%I:%M %p')}."

    def _get_date(self):
        now = datetime.now()
        return f"Today is {now.strftime('%A, %B %d, %Y')}."


def setup(app):
    return TaskManagerPlugin(app)
