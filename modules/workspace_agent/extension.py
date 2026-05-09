"""WorkspaceAgentExtension — Google Workspace integration for FRIDAY.

create_calendar_event accepts either explicit ISO datetimes (``start`` /
``end`` args) or natural language ("today at 6 pm", "tomorrow at 9") via
the raw transcript and the ``datetime`` arg. Natural-language parsing
delegates to ``app.task_manager`` so we share regex coverage with the
local-only reminder flow. Times default to a 60-minute event in the
system timezone.

Provides Gmail, Calendar, and Drive capabilities via the user's already
authenticated `gws` CLI (https://github.com/googleworkspace/cli). Read-only
operations are tagged `permission_mode="always_ok"` so the user does not need
to confirm every email/calendar request; create_calendar_event keeps
`ask_first` because it writes.

Capabilities:
  check_unread_emails    — list unread inbox
  read_latest_email      — read body of the most recent unread message
  read_email             — read a specific message by id
  get_calendar_today     — today's events
  get_calendar_week      — this week's events
  get_calendar_agenda    — upcoming N-day agenda
  create_calendar_event  — create an event (still asks for consent)
  search_drive           — search Drive
  daily_briefing         — morning summary: emails + today's calendar
"""
from __future__ import annotations

import re
import time as _time_mod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from core.extensions.protocol import Extension, ExtensionContext
from core.logger import logger
from modules.workspace_agent import gws_client as gws
from modules.workspace_agent.gws_client import GWSError


def _local_tz_offset() -> timezone:
    """System tz, computed from time.timezone/altzone with DST awareness."""
    seconds = -(_time_mod.altzone if _time_mod.daylight and _time_mod.localtime().tm_isdst > 0
                else _time_mod.timezone)
    return timezone(timedelta(seconds=seconds))


def _to_iso_local(dt: datetime) -> str:
    """Return RFC3339 with offset (e.g. ``2026-04-30T18:00:00+05:30``)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_local_tz_offset())
    return dt.isoformat(timespec="seconds")


_READ_META = {
    "connectivity": "online",
    "permission_mode": "always_ok",
    "latency_class": "slow",
    "side_effect_level": "read",
}

_WRITE_META = {
    "connectivity": "online",
    "permission_mode": "ask_first",
    "latency_class": "slow",
    "side_effect_level": "critical",
}


class WorkspaceAgentExtension(Extension):
    name = "WorkspaceAgent"

    def load(self, ctx: ExtensionContext) -> None:
        self.ctx = ctx
        self._register_capabilities()
        logger.info("WorkspaceAgentExtension loaded.")

    def unload(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register_capabilities(self) -> None:
        ctx = self.ctx

        ctx.register_capability(
            {
                "name": "check_unread_emails",
                "description": "List unread emails in the user's Gmail inbox (sender, subject, date).",
                "parameters": {"max_results": "max emails to return (default 10)"},
            },
            self._handle_check_unread_emails,
            metadata=_READ_META,
        )

        ctx.register_capability(
            {
                "name": "read_latest_email",
                "description": "Read the body of the most recent unread email in Gmail.",
                "parameters": {},
            },
            self._handle_read_latest_email,
            metadata=_READ_META,
        )

        ctx.register_capability(
            {
                "name": "read_email",
                "description": "Read the full body of a specific Gmail message by id.",
                "parameters": {"id": "Gmail message id"},
            },
            self._handle_read_email,
            metadata=_READ_META,
        )

        ctx.register_capability(
            {
                "name": "get_calendar_today",
                "description": "Get today's Google Calendar events.",
                "parameters": {},
            },
            self._handle_calendar_today,
            metadata=_READ_META,
        )

        ctx.register_capability(
            {
                "name": "get_calendar_week",
                "description": "Get this week's Google Calendar events.",
                "parameters": {},
            },
            self._handle_calendar_week,
            metadata=_READ_META,
        )

        ctx.register_capability(
            {
                "name": "get_calendar_agenda",
                "description": "Get upcoming calendar events for the next N days.",
                "parameters": {"days": "number of days ahead (default 3)"},
            },
            self._handle_calendar_agenda,
            metadata=_READ_META,
        )

        ctx.register_capability(
            {
                "name": "create_calendar_event",
                "description": "Create a new Google Calendar event.",
                "parameters": {
                    "summary": "event title",
                    "start": "start datetime ISO 8601",
                    "end": "end datetime ISO 8601",
                    "description": "optional description",
                },
            },
            self._handle_create_event,
            metadata=_WRITE_META,
        )

        ctx.register_capability(
            {
                "name": "search_drive",
                "description": "Search Google Drive for files by name or content.",
                "parameters": {"query": "search terms", "max_results": "max files to return"},
            },
            self._handle_search_drive,
            metadata=_READ_META,
        )

        ctx.register_capability(
            {
                "name": "daily_briefing",
                "description": "Morning briefing: unread email summary + today's calendar.",
                "parameters": {},
            },
            self._handle_daily_briefing,
            metadata=_READ_META,
        )

        ctx.register_capability(
            {
                "name": "summarize_inbox",
                "description": "Summarize all unread Gmail emails into a single spoken paragraph — sender, topic, and key details from every message.",
                "parameters": {"max_results": "max emails to fetch and summarize (default 10)"},
            },
            self._handle_summarize_inbox,
            metadata=_READ_META,
        )

    # ------------------------------------------------------------------
    # Gmail handlers
    # ------------------------------------------------------------------

    def _handle_check_unread_emails(self, raw_text: str, args: dict) -> str:
        try:
            max_results = int(args.get("max_results") or 10)
        except (TypeError, ValueError):
            max_results = 10
        try:
            messages = gws.gmail_list_unread(max_results=max_results)
        except GWSError as exc:
            return f"I couldn't reach Gmail: {exc}"

        if not messages:
            return "You have no unread emails, sir."

        lines = [f"You have {len(messages)} unread email(s), sir:"]
        for i, msg in enumerate(messages, 1):
            sender = _short_sender(msg.get("from", ""))
            subject = msg.get("subject") or "(no subject)"
            when = _short_date(msg.get("date", ""))
            lines.append(f"  {i}. From {sender} — {subject}{f' ({when})' if when else ''}")
        return "\n".join(lines)

    def _handle_read_latest_email(self, raw_text: str, args: dict) -> str:
        try:
            messages = gws.gmail_list_unread(max_results=1)
        except GWSError as exc:
            return f"I couldn't reach Gmail: {exc}"

        if not messages:
            return "Your inbox is clear — no unread emails, sir."

        latest = messages[0]
        message_id = latest.get("id", "")
        if not message_id:
            return "I couldn't find a message id for the latest email."

        try:
            data = gws.gmail_read(message_id, include_headers=True)
        except GWSError as exc:
            return f"Couldn't read that email: {exc}"

        return _format_full_email(data)

    def _handle_read_email(self, raw_text: str, args: dict) -> str:
        message_id = (args.get("id") or "").strip()
        if not message_id:
            return "Please provide a message id to read, sir."
        try:
            data = gws.gmail_read(message_id, include_headers=True)
        except GWSError as exc:
            return f"Couldn't read that email: {exc}"
        return _format_full_email(data)

    # ------------------------------------------------------------------
    # Calendar handlers
    # ------------------------------------------------------------------

    def _handle_calendar_today(self, raw_text: str, args: dict) -> str:
        return self._format_agenda(
            today=True,
            empty_message="You have no events scheduled for today, sir.",
            header="Here's your schedule for today, sir:",
        )

    def _handle_calendar_week(self, raw_text: str, args: dict) -> str:
        return self._format_agenda(
            week=True,
            empty_message="No events this week, sir. Your schedule is clear.",
            header="Here's your week ahead, sir:",
        )

    def _handle_calendar_agenda(self, raw_text: str, args: dict) -> str:
        try:
            days = int(args.get("days") or 3)
        except (TypeError, ValueError):
            days = 3
        return self._format_agenda(
            days=days,
            empty_message=f"Nothing scheduled in the next {days} day(s), sir.",
            header=f"Your agenda for the next {days} day(s), sir:",
        )

    def _format_agenda(self, *, header: str, empty_message: str, **kwargs) -> str:
        try:
            events = gws.calendar_agenda(**kwargs)
        except GWSError as exc:
            return f"Couldn't reach Calendar: {exc}"
        if not events:
            return empty_message
        lines = [header]
        for event in events:
            lines.append(_format_event(event))
        return "\n".join(lines)

    def _handle_create_event(self, raw_text: str, args: dict) -> str:
        args = dict(args or {})
        raw_text = raw_text or ""
        description = (args.get("description") or "").strip()

        summary = (args.get("summary") or args.get("title") or "").strip()
        if not summary:
            summary = self._extract_summary_from_text(raw_text)

        start_dt, end_dt = self._resolve_event_times(raw_text, args)

        if not summary and not start_dt:
            return (
                "What's the event title and when should it start, sir? "
                "Try \"create a calendar event titled standup tomorrow at 10\"."
            )
        if not summary:
            return "What should I title the event, sir?"
        if not start_dt:
            # Save pending state so the next turn is routed back here.
            self._save_calendar_workflow_state({
                "pending_slots": ["start_dt"],
                "summary": summary,
                "description": description,
            })
            return f"When should '{summary}' start, sir?"

        if end_dt is None:
            end_dt = start_dt + timedelta(hours=1)

        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=1)

        # Clear any pending workflow state before making the API call.
        self._clear_calendar_workflow_state()

        try:
            result = gws.calendar_create_event(
                summary,
                _to_iso_local(start_dt),
                _to_iso_local(end_dt),
                description=description,
            )
        except GWSError as exc:
            return f"Couldn't create the event: {exc}"
        event_id = result.get("id", "") if isinstance(result, dict) else ""
        when = start_dt.strftime("%a %d %b at ") + start_dt.strftime("%I:%M %p").lstrip("0")
        suffix = f" (id: {event_id})" if event_id else ""
        return f"Done, sir. I've added '{summary}' to your calendar for {when}.{suffix}"

    def _memory(self):
        app = self._get_app()
        if app is None:
            return None
        return getattr(app, "memory_service", None) or getattr(app, "context_store", None)

    def _save_calendar_workflow_state(self, state: dict) -> None:
        app = self._get_app()
        memory = self._memory()
        session_id = getattr(app, "session_id", None) if app else None
        if not session_id or not memory:
            return
        memory.save_workflow_state(session_id, "calendar_event_workflow", {
            "workflow_name": "calendar_event_workflow",
            "status": "active",
            **state,
        })

    def _clear_calendar_workflow_state(self) -> None:
        app = self._get_app()
        memory = self._memory()
        session_id = getattr(app, "session_id", None) if app else None
        if not session_id or not memory:
            return
        memory.clear_workflow_state(session_id, "calendar_event_workflow")

    def _get_app(self):
        ctx = getattr(self, "ctx", None)
        if ctx is None:
            return None
        return getattr(ctx, "_app_ref", None)

    # ------------------------------------------------------------------
    # Calendar parsing helpers
    # ------------------------------------------------------------------

    def _resolve_event_times(self, raw_text: str, args: dict):
        """Parse ``start`` / ``end`` from args (ISO) or natural-language text.

        Returns (start_dt, end_dt). Either may be None if unresolvable.
        """
        start_dt = self._parse_iso(args.get("start") or args.get("datetime"))
        end_dt = self._parse_iso(args.get("end"))

        if start_dt is None:
            blob = " ".join(
                str(part) for part in (
                    args.get("datetime"), args.get("start"), raw_text,
                ) if part
            ).strip()
            start_dt = self._parse_natural(blob)

        # Allow explicit duration via "for 30 minutes" / "for 2 hours".
        if start_dt and end_dt is None:
            duration = self._parse_duration(raw_text)
            if duration:
                end_dt = start_dt + duration

        return start_dt, end_dt

    def _parse_iso(self, value):
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            # ``fromisoformat`` accepts "2026-05-01T18:00:00+05:30" on 3.11+.
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _parse_natural(self, text: str):
        if not text:
            return None
        task_manager = self._get_task_manager()
        if task_manager is None:
            return None
        parsed = task_manager._parse_datetime_parts(text)
        if parsed.get("remind_at"):
            return parsed["remind_at"]
        return task_manager._combine_date_time(parsed.get("date"), parsed.get("time"))

    def _parse_duration(self, text: str):
        if not text:
            return None
        match = re.search(
            r"\bfor\s+(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|hrs?)\b",
            text, re.IGNORECASE,
        )
        if not match:
            return None
        amount = float(match.group(1))
        unit = match.group(2).lower()
        if unit.startswith("hour") or unit.startswith("hr"):
            return timedelta(hours=amount)
        return timedelta(minutes=amount)

    def _extract_summary_from_text(self, text: str) -> str:
        if not text:
            return ""
        task_manager = self._get_task_manager()
        if task_manager is not None:
            title = task_manager._extract_event_title(text)
            if title:
                # task_manager strips date/time suffixes but leaves "for 30
                # minutes" intact (it's a duration, not a time). Drop it here
                # so the calendar summary is just "meeting with bob".
                title = re.sub(
                    r"\s+for\s+\d+(?:\.\d+)?\s*(?:minutes?|mins?|hours?|hrs?)\b.*$",
                    "", title, flags=re.IGNORECASE,
                ).strip()
                if title:
                    return title

        # Fallback: strip the action verbs and the temporal tail. Handles
        # phrases like "schedule a dentist appointment today at 6 pm" →
        # "dentist appointment".
        cleaned = re.sub(
            r"^\s*(?:please\s+)?(?:create|add|schedule|set\s+up|book|put|make|add\s+to\s+(?:my\s+)?calendar(?:\s+for)?)\b",
            "",
            text.strip(),
            flags=re.IGNORECASE,
        ).strip()
        cleaned = re.sub(
            r"^\s*(?:a|an|the)\s+", "", cleaned, flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^\s*(?:calendar\s+)?(?:event|meeting|reminder|appointment)\s+"
            r"(?:titled|called|named|for|to)\s+",
            "", cleaned, flags=re.IGNORECASE,
        )
        # Strip the trailing temporal phrase.
        cleaned = re.sub(
            r"\s+(?:on|at|today|tomorrow|tonight|next|in|from|by|for)\b.*$",
            "", cleaned, flags=re.IGNORECASE,
        )
        cleaned = cleaned.strip(" .,!?")
        return cleaned

    def _get_task_manager(self):
        app = getattr(self, "ctx", None) and self.ctx._app_ref
        if app is None:
            return None
        return getattr(app, "task_manager", None)

    # ------------------------------------------------------------------
    # Drive
    # ------------------------------------------------------------------

    def _handle_search_drive(self, raw_text: str, args: dict) -> str:
        query = (args.get("query") or "").strip()
        try:
            max_results = int(args.get("max_results") or 5)
        except (TypeError, ValueError):
            max_results = 5
        if not query:
            for prefix in ("search drive for", "find in drive", "search drive", "drive search"):
                if prefix in (raw_text or "").lower():
                    query = raw_text.lower().split(prefix, 1)[-1].strip()
                    break
        if not query:
            return "What should I search for in Drive, sir?"
        try:
            files = gws.drive_list_files(query=f"name contains '{query}'", page_size=max_results)
        except GWSError as exc:
            return f"Couldn't search Drive: {exc}"
        if not files:
            return f"No files found matching '{query}' in Drive, sir."

        lines = [f"Found {len(files)} file(s) matching '{query}' in Drive:"]
        for f in files:
            name = f.get("name", "Unnamed")
            mime = (f.get("mimeType") or "").split(".")[-1] or "file"
            link = f.get("webViewLink", "")
            line = f"  • {name} ({mime})"
            if link:
                line += f" — {link}"
            lines.append(line)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Inbox summary
    # ------------------------------------------------------------------

    def _handle_summarize_inbox(self, raw_text: str, args: dict) -> str:
        """Fetch unread email bodies in parallel, then LLM-summarize into one paragraph."""
        try:
            max_emails = min(int(args.get("max_results") or 10), 15)
        except (TypeError, ValueError):
            max_emails = 10

        try:
            messages = gws.gmail_list_unread(max_results=max_emails)
        except GWSError as exc:
            return f"I couldn't reach Gmail: {exc}"

        if not messages:
            return "Your inbox is clear — no unread emails to summarize, sir."

        count = len(messages)
        # Read bodies for the top 5 only — keeps prompt short and inference fast.
        to_read = [m for m in messages[:5] if m.get("id")]

        bodies: dict[str, str] = {}

        def _read_one(msg: dict) -> tuple[str, str]:
            try:
                data = gws.gmail_read(msg["id"], include_headers=True)
                body = (
                    data.get("body_text") or data.get("body") or data.get("text") or ""
                ).strip()
                if len(body) > 200:
                    body = body[:200].rstrip() + "…"
                return msg["id"], body
            except Exception:
                return msg["id"], ""

        with ThreadPoolExecutor(max_workers=4) as pool:
            for msg_id, body in pool.map(_read_one, to_read):
                if msg_id:
                    bodies[msg_id] = body

        # Build compact context blocks
        blocks = []
        for i, msg in enumerate(messages, 1):
            sender = _short_sender(msg.get("from", ""))
            subject = msg.get("subject") or "(no subject)"
            body = bodies.get(msg.get("id", ""), "")
            block = f"{i}. {sender}: {subject}"
            if body:
                block += f" — {body}"
            blocks.append(block)

        email_text = "\n".join(blocks)

        llm, inference_lock = self._get_chat_llm_and_lock()
        if llm is not None:
            prompt = (
                f"You have {count} unread email(s):\n{email_text}\n\n"
                "Write ONE paragraph (2-3 sentences) summarising all these emails. "
                "Mention each sender and their key point. "
                "Plain conversational English, no lists, no bullet points."
            )
            try:
                with inference_lock:
                    resp = llm.create_chat_completion(
                        messages=[{"role": "user", "content": prompt + "\n\n/no_think"}],
                        max_tokens=150,
                        temperature=0.3,
                        top_p=0.9,
                    )
                summary = (resp["choices"][0]["message"]["content"] or "").strip()
                summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL).strip()
                if summary:
                    return summary
                logger.warning("[workspace] LLM returned empty email summary")
            except Exception as exc:
                logger.warning("[workspace] LLM inbox summary failed: %s", exc)

        # Fallback: plain spoken list when LLM is unavailable
        parts = [f"You have {count} unread email(s), sir."]
        for msg in messages:
            sender = _short_sender(msg.get("from", ""))
            subject = msg.get("subject") or "(no subject)"
            parts.append(f"From {sender}: {subject}.")
        return " ".join(parts)

    def _get_chat_llm_and_lock(self):
        """Return (chat_llm, inference_lock) from the app router, or (None, dummy_lock)."""
        import threading
        _dummy = threading.Lock()
        app = self._get_app()
        if app is None:
            return None, _dummy
        router = getattr(app, "router", None)
        if router is None:
            return None, _dummy
        try:
            llm = router.get_llm()
            lock = getattr(router, "chat_inference_lock", _dummy)
            return llm, lock
        except Exception:
            return None, _dummy

    # ------------------------------------------------------------------
    # Daily briefing
    # ------------------------------------------------------------------

    def _handle_daily_briefing(self, raw_text: str, args: dict) -> str:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            greeting = "Good morning"
        elif 12 <= hour < 17:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        parts = [f"{greeting}, sir. Here's your daily briefing:\n"]

        try:
            events = gws.calendar_agenda(today=True)
            if events:
                parts.append(f"CALENDAR — {len(events)} event(s) today:")
                for event in events[:5]:
                    parts.append(_format_event(event))
            else:
                parts.append("CALENDAR — No events today. Your schedule is clear.")
        except GWSError as exc:
            parts.append(f"CALENDAR — Could not retrieve events: {exc}")

        parts.append("")

        try:
            messages = gws.gmail_list_unread(max_results=5)
            if messages:
                parts.append(f"EMAIL — {len(messages)} unread message(s):")
                for msg in messages[:5]:
                    sender = _short_sender(msg.get("from", ""))
                    subject = msg.get("subject") or "(no subject)"
                    parts.append(f"  • {sender}: {subject}")
            else:
                parts.append("EMAIL — Inbox clear. No unread messages.")
        except GWSError as exc:
            parts.append(f"EMAIL — Could not retrieve emails: {exc}")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _short_sender(sender) -> str:
    """Return a compact display name from gws's `from` field.

    `gws gmail +triage` returns a string like 'Name <addr@x>' or just an
    email; `gws gmail +read` returns a dict {name, email}.
    """
    if isinstance(sender, dict):
        name = (sender.get("name") or "").strip().strip('"')
        email = (sender.get("email") or "").strip()
        return name or email or "Unknown"
    text = str(sender or "").strip()
    if "<" in text:
        text = text.split("<", 1)[0].strip().strip('"')
    return text or "Unknown"


def _short_date(date_str: str) -> str:
    if not date_str:
        return ""
    if "," in date_str:
        date_str = date_str.split(",", 1)[1].strip()
    return date_str[:12]


def _format_event(event: dict) -> str:
    summary = event.get("summary") or "Untitled Event"
    start = event.get("start")
    when = ""
    if isinstance(start, dict):
        when = start.get("dateTime") or start.get("date") or ""
    elif isinstance(start, str):
        when = start
    if when and "T" in when:
        try:
            dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
            when = str(dt.day) + dt.strftime(" %b at ") + dt.strftime("%I:%M %p").lstrip("0")
        except Exception:
            when = when[:16]
    location = event.get("location") or ""
    line = f"  • {when} — {summary}" if when else f"  • {summary}"
    if location:
        line += f" @ {location}"
    return line


def _format_full_email(data: dict) -> str:
    """Format the JSON returned by `gws gmail +read --format json --headers`.

    Real shape: {from: {name,email}, to: [...], subject, date, body_text, ...}
    """
    if not isinstance(data, dict):
        return str(data)

    sender = _short_sender(data.get("from"))
    subject = data.get("subject") or "(no subject)"
    when = data.get("date") or ""
    body = data.get("body_text") or data.get("body") or data.get("text") or ""
    # Strip invisible whitespace padding marketing emails like to use, plus
    # collapse runs of whitespace so TTS doesn't read empty lines.
    body = body.replace("‌", " ").replace("​", " ").replace(" ", " ")
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{2,}", "\n\n", body).strip()
    if len(body) > 1500:
        body = body[:1500].rstrip() + "…"

    lines = [f"From: {sender}", f"Subject: {subject}"]
    if when:
        lines.append(f"Date: {when}")
    lines.append("")
    lines.append(body or "(empty message)")
    return "\n".join(lines)
