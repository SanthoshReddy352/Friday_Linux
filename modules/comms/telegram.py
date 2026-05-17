"""Telegram delivery channel for proactive FRIDAY notifications.

Mirrors jarvis src/comms/channels/telegram.ts.
Sends messages when the user is away from the machine (reminders, goal
check-ins, awareness suggestions).

Setup:
  1. Create a bot via @BotFather and copy the token.
  2. Message the bot once to get your chat_id.
  3. Set environment variables:
       FRIDAY_TELEGRAM_TOKEN=<bot_token>
       FRIDAY_TELEGRAM_CHAT_ID=<chat_id>
  4. Install:  pip install python-telegram-bot

Security: tokens live in OS environment variables, never in config.yaml.
"""
from __future__ import annotations

import os
import threading
import time

from core.logger import logger


class TelegramChannel:
    """Sends proactive notifications to a Telegram chat."""

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self._token = token or os.environ.get("FRIDAY_TELEGRAM_TOKEN", "")
        self._chat_id = chat_id or os.environ.get("FRIDAY_TELEGRAM_CHAT_ID", "")
        self._available = bool(self._token and self._chat_id)
        if not self._available:
            logger.debug("[Telegram] disabled — set FRIDAY_TELEGRAM_TOKEN + FRIDAY_TELEGRAM_CHAT_ID")

    @property
    def available(self) -> bool:
        return self._available

    def send(self, text: str, parse_mode: str = "") -> bool:
        """Send a message asynchronously. Returns True if dispatched."""
        if not self.available:
            return False
        t = threading.Thread(target=self._send_sync, args=(text, parse_mode), daemon=True)
        t.start()
        return True

    def _send_sync(self, text: str, parse_mode: str) -> None:
        import urllib.request
        import urllib.error
        import json as _json
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        body: dict = {"chat_id": self._chat_id, "text": text}
        if parse_mode:
            body["parse_mode"] = parse_mode
        payload = _json.dumps(body).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = _json.load(resp)
                if not result.get("ok"):
                    logger.warning("[Telegram] send failed: %s", result.get("description"))
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read()
            logger.warning("[Telegram] send failed HTTP %d: %s", exc.code, body_bytes.decode()[:200])
        except Exception as exc:
            logger.warning("[Telegram] send failed: %s", exc)


class TelegramInbound:
    """Polls the bot for incoming messages and routes them to FRIDAY silently.

    Each incoming message is processed via app.process_input(text, source="telegram")
    on a worker thread. Because source="telegram" takes the synchronous _execute_turn
    path, process_input returns the response text directly — no event-bus subscription
    is needed. TTS is suppressed for the duration of the call via the
    app.telegram_turn_active flag checked in VoiceIOPlugin.handle_speak.
    """

    _POLL_TIMEOUT = 20   # seconds — Telegram long-poll window

    def __init__(self, channel: TelegramChannel, app):
        self._channel = channel
        self._app = app
        self._offset = 0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._poll_loop, name="TelegramInbound", daemon=True)
        self._thread.start()
        logger.info("[TelegramInbound] polling started")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while True:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._dispatch(update)
            except Exception as exc:
                logger.warning("[TelegramInbound] poll error: %s", exc)
                time.sleep(5)

    def _get_updates(self) -> list:
        import urllib.request
        import urllib.error
        import json as _json

        url = (
            f"https://api.telegram.org/bot{self._channel._token}/getUpdates"
            f"?offset={self._offset}&timeout={self._POLL_TIMEOUT}&allowed_updates=message"
        )
        try:
            with urllib.request.urlopen(url, timeout=self._POLL_TIMEOUT + 5) as resp:
                data = _json.load(resp)
        except urllib.error.HTTPError as exc:
            logger.warning("[TelegramInbound] getUpdates HTTP %d", exc.code)
            return []
        if not data.get("ok"):
            return []
        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    def _dispatch(self, update: dict) -> None:
        message = update.get("message") or {}
        chat_id = str(message.get("chat", {}).get("id", ""))
        if chat_id != self._channel._chat_id:
            return

        # File attachment (document, photo, audio, video, …)
        doc = message.get("document")
        photo_arr = message.get("photo")  # list of PhotoSize, largest last
        if doc or photo_arr:
            if doc:
                file_id = doc.get("file_id", "")
                file_name = doc.get("file_name") or f"attachment_{file_id[:8]}"
            else:
                largest = max(photo_arr, key=lambda p: p.get("file_size", 0))
                file_id = largest.get("file_id", "")
                file_name = f"photo_{file_id[:8]}.jpg"
            caption = (message.get("caption") or "").strip()
            threading.Thread(
                target=self._handle_file,
                args=(file_id, file_name, caption),
                name="TelegramFile",
                daemon=True,
            ).start()
            return

        # Plain text message
        text = (message.get("text") or "").strip()
        if not text:
            return

        # Telegram bot commands (always start with '/') must not be routed to FRIDAY.
        # Strip optional @BotUsername suffix that Telegram appends in groups.
        if text.startswith('/'):
            command = text.split()[0].split('@')[0].lower()
            if command == '/start':
                self._channel.send(
                    "Hello! I'm FRIDAY, your AI assistant.\n"
                    "Send me a message or upload a document (.pdf, .docx, .txt, .csv, "
                    ".xlsx, .pptx, .md, .html) to get started."
                )
            # All other bot commands (e.g. /help, /settings) are silently ignored.
            return

        threading.Thread(
            target=self._process,
            args=(text,),
            name="TelegramProcess",
            daemon=True,
        ).start()

    # Extensions the session RAG / MarkItDown converter can handle.
    # Kept in sync with modules/document_intel/converter.py SUPPORTED_EXTENSIONS
    # plus the plain-text fallbacks in SessionRAG._PLAIN_SUFFIXES.
    _SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".md", ".txt", ".html", ".csv"}

    def _handle_file(self, file_id: str, file_name: str, caption: str) -> None:
        """Download a Telegram file, load it into session RAG, reply with status."""
        import tempfile
        import urllib.request
        import urllib.error
        import json as _json
        from pathlib import Path

        suffix = Path(file_name).suffix.lower()
        if suffix not in self._SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(self._SUPPORTED_EXTENSIONS))
            self._channel.send(
                f"Unsupported file type: {suffix or '(no extension)'}\n"
                f"Supported formats: {supported}"
            )
            return

        # Step 1 — resolve download URL via getFile
        try:
            gf_url = (
                f"https://api.telegram.org/bot{self._channel._token}"
                f"/getFile?file_id={file_id}"
            )
            with urllib.request.urlopen(gf_url, timeout=10) as resp:
                gf_data = _json.load(resp)
        except Exception as exc:
            logger.warning("[TelegramInbound] getFile failed: %s", exc)
            self._channel.send("Could not retrieve the file from Telegram. Please try again.")
            return

        if not gf_data.get("ok"):
            self._channel.send("Telegram returned an error fetching the file.")
            return

        file_path_remote = gf_data["result"].get("file_path", "")
        if not file_path_remote:
            self._channel.send("Telegram did not return a download path for this file.")
            return

        # Step 2 — download to a temp file
        download_url = (
            f"https://api.telegram.org/file/bot{self._channel._token}/{file_path_remote}"
        )
        try:
            with tempfile.NamedTemporaryFile(
                suffix=suffix, prefix="friday_tg_", delete=False
            ) as tmp:
                tmp_path = tmp.name
            urllib.request.urlretrieve(download_url, tmp_path)
        except Exception as exc:
            logger.warning("[TelegramInbound] download failed: %s", exc)
            self._channel.send(f"Download failed: {exc}")
            return

        # Step 3 — rename to preserve the original filename (cosmetic, for status msg)
        import os
        try:
            named = str(Path(tmp_path).parent / file_name)
            os.rename(tmp_path, named)
            load_path = named
        except Exception:
            load_path = tmp_path

        status = self._app.load_session_rag_file(load_path)

        reply = f"File loaded: {file_name}\n{status}"
        if caption:
            # Process the caption as a query against the freshly loaded document
            reply += "\n\nProcessing your caption..."
            self._channel.send(reply)
            self._process(caption)
        else:
            self._channel.send(reply)

    def _process(self, text: str) -> None:
        # process_input(source="telegram") takes the synchronous _execute_turn path
        # and returns the response text directly — no event subscription needed.
        # The flag is True only for the duration of the synchronous call so voice
        # TTS is never blocked longer than the actual Telegram turn takes.
        self._app.telegram_turn_active = True
        try:
            response = self._app.process_input(text, source="telegram")
        finally:
            self._app.telegram_turn_active = False

        if response:
            self._channel.send(response)
