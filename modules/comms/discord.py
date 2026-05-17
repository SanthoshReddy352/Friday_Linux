"""Discord delivery channel for proactive FRIDAY notifications.

Mirrors jarvis src/comms/channels/discord.ts.
Uses Discord webhook URLs — no bot account required.

Setup:
  1. In Discord: channel settings → Integrations → Webhooks → New Webhook.
  2. Copy the webhook URL.
  3. Set environment variable:
       FRIDAY_DISCORD_WEBHOOK_URL=<webhook_url>

Security: webhook URL lives in OS environment, never in config.yaml.
"""
from __future__ import annotations

import os
import threading

from core.logger import logger


class DiscordChannel:
    """Sends proactive notifications to a Discord channel via webhook."""

    def __init__(self, webhook_url: str | None = None):
        self._url = webhook_url or os.environ.get("FRIDAY_DISCORD_WEBHOOK_URL", "")
        self._available = bool(self._url)
        if not self._available:
            logger.debug("[Discord] disabled — set FRIDAY_DISCORD_WEBHOOK_URL")

    @property
    def available(self) -> bool:
        return self._available

    def send(self, text: str, username: str = "FRIDAY") -> bool:
        """Send a message asynchronously. Returns True if dispatched."""
        if not self.available:
            return False
        t = threading.Thread(
            target=self._send_sync, args=(text, username), daemon=True
        )
        t.start()
        return True

    def _send_sync(self, text: str, username: str) -> None:
        try:
            import urllib.request
            import json as _json
            payload = _json.dumps({
                "content": text[:2000],  # Discord message limit
                "username": username,
            }).encode()
            req = urllib.request.Request(
                self._url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status not in (200, 204):
                    logger.warning("[Discord] send failed: HTTP %d", resp.status)
        except Exception as exc:
            logger.warning("[Discord] send failed: %s", exc)
