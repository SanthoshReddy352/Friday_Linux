import re
import threading
import sqlite3
import os
from datetime import datetime
from core.plugin_manager import FridayPlugin
from core.logger import logger


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "friday.db")


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
    conn.commit()
    conn.close()


class TaskManagerPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "TaskManager"
        self._reminder_timers = []
        _ensure_db()
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "set_reminder",
            "description": (
                "Set a reminder that FRIDAY will announce after a specified number of minutes. "
                "Example: 'remind me to call John in 5 minutes'."
            ),
            "parameters": {
                "message": "string – what to remind the user about",
                "minutes": "integer – how many minutes from now to trigger the reminder"
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
        message = args.get("message", "").strip()
        minutes = args.get("minutes", None)

        # Fallback parsing if LLM didn't extract args
        if not message or minutes is None:
            message, minutes = self._parse_reminder_text(text)

        if not message:
            return "What would you like me to remind you about?"
        if minutes is None or minutes <= 0:
            return "How many minutes from now should I remind you?"

        seconds = int(minutes * 60)
        timer = threading.Timer(seconds, self._fire_reminder, args=[message])
        timer.daemon = True
        timer.start()
        self._reminder_timers.append(timer)

        logger.info(f"[TaskManager] Reminder set: '{message}' in {minutes} min")
        return f"Got it! I'll remind you to '{message}' in {int(minutes)} minute{'s' if minutes != 1 else ''}."

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

    def _get_time(self):
        now = datetime.now()
        return f"The current time is {now.strftime('%I:%M %p')}."

    def _get_date(self):
        now = datetime.now()
        return f"Today is {now.strftime('%A, %B %d, %Y')}."


def setup(app):
    return TaskManagerPlugin(app)
