"""gws CLI wrapper for Google Workspace integration.

Thin subprocess wrapper around the `gws` CLI tool
(https://github.com/googleworkspace/cli).

The user has already authenticated `gws` (via keyring), so we just shell out
and parse JSON. All methods return Python objects shaped exactly the way the
CLI produces them; callers handle the formatting.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


class GWSError(Exception):
    pass


def _run(*args: str, timeout: int = 20) -> Any:
    """Run a gws command and return parsed JSON output."""
    gws_path = shutil.which("gws")
    if gws_path is None:
        # Fallback to common installation directories
        common_paths = [
            os.path.expanduser("~/.local/bin/gws"),
            os.path.expanduser("~/go/bin/gws"),
            os.path.expanduser("~/.cargo/bin/gws"),
            os.path.expanduser("~/.npm-global/bin/gws"),
            os.path.expanduser("~/bin/gws"),
            "/usr/local/bin/gws",
            "/usr/bin/gws",
            "/opt/homebrew/bin/gws",
            "/home/linuxbrew/.linuxbrew/bin/gws",
            "/snap/bin/gws",
        ]
        for p in common_paths:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                gws_path = p
                break

    if gws_path is None:
        cmd = ["bash", "-lc", 'exec gws "$@"', "--", *args]
    else:
        cmd = [gws_path, *args]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise GWSError(f"gws command timed out after {timeout}s")
    except Exception as exc:
        raise GWSError(f"gws subprocess error: {exc}") from exc

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    
    # Check if bash failed to find gws
    if result.returncode == 127 and "gws: command not found" in stderr:
         raise GWSError("gws CLI not found. Install from https://github.com/googleworkspace/cli")

    if result.returncode != 0 and not stdout:
        msg = stderr or f"gws exited with status {result.returncode}"
        raise GWSError(msg)
    if not stdout:
        return {}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"text": stdout}

    if isinstance(data, dict) and "error" in data:
        err = data["error"]
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise GWSError(f"gws API error: {msg}")
    return data


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

def gmail_list_unread(max_results: int = 10) -> list[dict]:
    """Return unread messages from `gws gmail +triage`.

    Each item: {id, from, subject, date}.
    """
    data = _run("gmail", "+triage", "--max", str(max_results), "--format", "json")
    messages = data.get("messages", []) if isinstance(data, dict) else []
    return list(messages)


def gmail_read(message_id: str, include_headers: bool = True) -> dict:
    """Read a Gmail message by id and return the parsed JSON.

    Real gws shape (key fields):
      from: {name, email}, to: [{name, email}], subject, date, body_text,
      thread_id, message_id, references
    """
    args = ["gmail", "+read", "--id", message_id, "--format", "json"]
    if include_headers:
        args.append("--headers")
    return _run(*args)


def gmail_send(to: str, subject: str, body: str) -> dict:
    """Send an email via the helper command."""
    return _run(
        "gmail", "+send",
        "--to", to,
        "--subject", subject,
        "--body", body,
        "--format", "json",
    )


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

def calendar_agenda(*, today: bool = False, tomorrow: bool = False, week: bool = False, days: int | None = None) -> list[dict]:
    """Return upcoming calendar events from `gws calendar +agenda`.

    Each event: {summary, start (ISO string), end (ISO string), calendar, location}.
    """
    args = ["calendar", "+agenda", "--format", "json"]
    if today:
        args.append("--today")
    elif tomorrow:
        args.append("--tomorrow")
    elif week:
        args.append("--week")
    elif days is not None:
        args += ["--days", str(days)]
    data = _run(*args)
    return data.get("events", []) if isinstance(data, dict) else []


def calendar_create_event(summary: str, start_datetime: str, end_datetime: str, description: str = "", timezone: str = "UTC") -> dict:
    """Create a calendar event via raw `events insert`."""
    payload = json.dumps({
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_datetime, "timeZone": timezone},
        "end": {"dateTime": end_datetime, "timeZone": timezone},
    })
    params = json.dumps({"calendarId": "primary"})
    return _run("calendar", "events", "insert", "--params", params, "--json", payload)


def calendar_update_event(
    event_id: str,
    *,
    summary: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    description: str | None = None,
    timezone: str = "UTC",
) -> dict:
    """Patch an existing calendar event (Batch 5 / Issue 12).

    Only the fields explicitly passed are forwarded — the Google
    Calendar API patches in-place, so untouched fields keep their
    server-side values. ``event_id`` is the Google-assigned id (returned
    by ``calendar_agenda`` and ``calendar_create_event``).
    """
    if not event_id:
        raise GWSError("event_id is required to update an event.")
    body: dict[str, Any] = {}
    if summary is not None:
        body["summary"] = summary
    if description is not None:
        body["description"] = description
    if start_datetime is not None:
        body["start"] = {"dateTime": start_datetime, "timeZone": timezone}
    if end_datetime is not None:
        body["end"] = {"dateTime": end_datetime, "timeZone": timezone}
    if not body:
        raise GWSError("Nothing to update — pass at least one field.")
    params = json.dumps({"calendarId": "primary", "eventId": event_id})
    return _run("calendar", "events", "patch", "--params", params, "--json", json.dumps(body))


def calendar_delete_event(event_id: str) -> dict:
    """Delete a calendar event by id (Batch 5 / Issue 12).

    ``cancel_calendar_event`` and ``delete_calendar_event`` map to the
    same Google API call; the tool surface just exposes the two verbs
    so users can phrase the request naturally.
    """
    if not event_id:
        raise GWSError("event_id is required to delete an event.")
    params = json.dumps({"calendarId": "primary", "eventId": event_id})
    return _run("calendar", "events", "delete", "--params", params)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def ensure_auth() -> tuple[bool, str]:
    """Probe whether the `gws` CLI has a usable token.

    Returns (ok, message). The message is user-facing on failure — it
    tells them exactly what to run to re-authenticate. Used by the
    workspace extension's handlers to upgrade the cryptic
    ``Failed to get token`` error path into a clear action prompt.
    """
    try:
        _run("auth", "+status", "--format", "json", timeout=8)
    except GWSError as exc:
        text = str(exc).lower()
        if "failed to get token" in text or "not authenticated" in text or "no credentials" in text:
            return False, "Google Workspace isn't authenticated. Run `gws auth` once in your terminal, then try again."
        return False, f"Google Workspace check failed: {exc}"
    return True, ""


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

def drive_list_files(query: str = "", page_size: int = 10) -> list[dict]:
    """List Drive files matching an optional query."""
    params_dict: dict[str, Any] = {"pageSize": page_size}
    if query:
        params_dict["q"] = query
    params = json.dumps(params_dict)
    data = _run("drive", "files", "list", "--params", params, "--format", "json")
    return data.get("files", []) if isinstance(data, dict) else []
