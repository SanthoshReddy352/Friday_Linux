"""Feed Prism news fetching service.

Sources configured per user spec:
  Technology   : TechCrunch, The Verge, Wired
  Global News  : Al Jazeera, BBC World, NPR News
  Company News : Google Blog, Apple Newsroom
  Startups     : Product Hunt
  Security     : The Hacker News (Security)
  Business     : Forbes Business
"""
from __future__ import annotations

import os
import platform as _platform
import re
import subprocess

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from core.logger import logger
from core.model_output import strip_model_artifacts, with_no_think_user_message


FEED_PRISM_BASE = "https://feed-prism.vercel.app/api/v1/articles"
WORLDMONITOR_URL = "https://www.worldmonitor.app"

CATEGORY_CONFIG: dict[str, dict] = {
    "technology": {
        "label": "Technology",
        "category": "Technology",
        "sources": [
            "c116a3bb-01f1-4273-b826-fd6d21d06cbd",  # TechCrunch
            "f441f4c6-6fa7-4c9c-92cd-2ec2c91924eb",  # The Verge
            "b2d5498f-2190-4bce-b4b9-2bcd6e29a5a7",  # Wired
        ],
    },
    "global": {
        "label": "Global News",
        "category": "Global News",
        "sources": [
            "096ddc57-d505-44e5-b0ba-4c2b757d912a",  # Al Jazeera
            "466ac9ac-e8cc-460c-89f9-4c3c26ad6155",  # BBC World
            "48a62ef3-d971-41ab-b4c0-8224275897bd",  # NPR News
        ],
    },
    "company": {
        "label": "Company News",
        "category": "Company News",
        "sources": [
            "4840ec72-e45d-4a50-a460-f3d91c10a00d",  # Google Blog
            "7c1dda82-f203-41ef-82c9-33c895091a1c",  # Apple Newsroom
        ],
    },
    "startups": {
        "label": "Startup News",
        "category": "Startups",
        "sources": [
            "b8142a46-dd1d-41c4-95a7-0f9f8eb22e3c",  # Product Hunt
        ],
    },
    "security": {
        "label": "Security News",
        "category": "Security",
        "sources": [
            "7a0208be-5838-4b75-bb29-7bd057a07fed",  # The Hacker News (Security)
        ],
    },
    "business": {
        "label": "Business News",
        "category": "Business",
        "sources": [
            "7d5a0225-b820-483d-a36e-b6ee4bd7aa6a",  # Forbes Business
        ],
    },
}

_ORDINALS = ["First", "Second", "Third", "Fourth", "Fifth",
             "Sixth", "Seventh", "Eighth", "Ninth", "Tenth"]


class NewsFeedService:
    def __init__(self, app=None):
        self.app = app
        self._api_key = os.getenv("FEED_PRISM_API_KEY", "").strip()
        if not self._api_key:
            logger.warning("[NewsFeed] FEED_PRISM_API_KEY not set — news fetch will fail.")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict:
        return {"x-api-key": self._api_key}

    def _fetch(self, category: str, source_ids: list[str], limit: int) -> list[dict]:
        if not self._api_key:
            return []
        params: dict = {"limit": min(limit, 50), "page": 1, "categories": category}
        if source_ids:
            params["sources"] = ",".join(source_ids)
        try:
            resp = requests.get(
                FEED_PRISM_BASE,
                headers=self._headers(),
                params=params,
                timeout=15,
            )
            if resp.status_code == 401:
                logger.error("[NewsFeed] Invalid or missing API key (401).")
                return []
            if resp.status_code == 429:
                logger.warning("[NewsFeed] Rate limit exceeded (429).")
                return []
            resp.raise_for_status()
            return resp.json().get("data", [])
        except requests.exceptions.ConnectionError:
            logger.error("[NewsFeed] Cannot reach Feed Prism API.")
            return []
        except Exception as exc:
            logger.error("[NewsFeed] API error for %s: %s", category, exc)
            return []

    # ── Public API ────────────────────────────────────────────────────────────

    def get_category_news(self, category_key: str, limit: int = 5) -> str:
        """Fetch top *limit* articles from a single category and return a spoken string."""
        cfg = CATEGORY_CONFIG.get(category_key)
        if not cfg:
            return f"I don't recognise the news category '{category_key}'."

        if not self._api_key:
            return "The Feed Prism API key is not configured. Please add FEED_PRISM_API_KEY to your .env file."

        # Open worldmonitor.app for every news request
        self._open_worldmonitor_browser()

        articles = self._fetch(cfg["category"], cfg["sources"], limit)
        if not articles:
            return f"I couldn't fetch {cfg['label']} articles right now. Please try again shortly."

        label = cfg["label"]
        parts = [f"Here are the top {len(articles)} {label} stories."]
        for i, art in enumerate(articles):
            ordinal = _ORDINALS[i] if i < len(_ORDINALS) else f"Article {i + 1}"
            source_name = (art.get("sources") or {}).get("name", "")
            title = (art.get("title") or "").strip()
            body = (art.get("body") or "").strip()
            source_tag = f" from {source_name}" if source_name else ""
            parts.append(f"{ordinal}{source_tag}: {title}. {body}")

        return "  ".join(parts)

    def get_news_briefing(self, limit_per_category: int = 3) -> str:
        """Cumulative briefing: fetch *limit_per_category* articles from every category,
        open worldmonitor.app in the browser (non-blocking), then summarise via LLM."""
        if not self._api_key:
            return "The Feed Prism API key is not configured. Please add FEED_PRISM_API_KEY to your .env file."

        # Open worldmonitor.app in browser (non-blocking)
        self._open_worldmonitor_browser()

        # Fetch from all categories
        all_sections: list[str] = []
        for key, cfg in CATEGORY_CONFIG.items():
            articles = self._fetch(cfg["category"], cfg["sources"], limit_per_category)
            if not articles:
                continue
            lines: list[str] = []
            for art in articles[:limit_per_category]:
                source = (art.get("sources") or {}).get("name", "")
                title = (art.get("title") or "").strip()
                body = (art.get("body") or "").strip()
                tag = f"[{source}] " if source else ""
                lines.append(f"  • {tag}{title}: {body}")
            if lines:
                all_sections.append(f"=== {cfg['label']} ===\n" + "\n".join(lines))

        if not all_sections:
            return "No news articles could be fetched from any category at this time."

        corpus = "\n\n".join(all_sections)
        return self._summarize(corpus)

    # ── LLM summarisation ─────────────────────────────────────────────────────

    def _summarize(self, corpus: str) -> str:
        llm = None
        if self.app:
            llm = getattr(self.app.router, "get_llm", lambda: None)()

        if llm is None:
            return "Here is your news briefing.\n\n" + corpus

        prompt = (
            "You are FRIDAY, a concise and engaging news briefer. "
            "Below are today's top stories from six categories: "
            "Technology, Global News, Company News, Startups, Security, and Business. "
            "Write a spoken-word news briefing in 4–6 flowing paragraphs. "
            "Highlight the most important and interesting stories. "
            "Be informative, engaging, and natural — not a bullet list.\n\n"
            f"{corpus}\n\n"
            "Briefing:"
        )
        messages = with_no_think_user_message([{"role": "user", "content": prompt}])
        try:
            lock = getattr(getattr(self.app, "router", None), "chat_inference_lock", None)
            kwargs = dict(messages=messages, max_tokens=900, temperature=0.7, top_p=0.9)
            if lock:
                with lock:
                    result = llm.create_chat_completion(**kwargs)
            else:
                result = llm.create_chat_completion(**kwargs)
            if isinstance(result, dict):
                return strip_model_artifacts(result["choices"][0]["message"]["content"])
        except Exception as exc:
            logger.error("[NewsFeed] LLM summarisation failed: %s", exc)

        return "Here is your news briefing.\n\n" + corpus

    # ── Browser helper ────────────────────────────────────────────────────────

    def _open_worldmonitor_browser(self) -> None:
        """Open worldmonitor.app in the browser without blocking the news fetch."""
        # Prefer the Playwright-backed browser automation plugin
        try:
            # Phase 4: direct service reference
            if hasattr(self.app, "browser_media_service"):
                svc = self.app.browser_media_service
                if svc and hasattr(svc, "open_browser_url"):
                    svc.open_browser_url(WORLDMONITOR_URL, browser_name="chrome", platform="worldmonitor")
                    logger.info("[NewsFeed] Opened worldmonitor.app via browser automation (direct).")
                    return

            # Fallback to scanning plugins/extensions
            plugins = []
            if hasattr(self.app, "extension_loader"):
                plugins = getattr(self.app.extension_loader, "extensions", [])
            elif hasattr(self.app, "plugin_manager"):
                plugins = getattr(self.app.plugin_manager, "plugins", [])

            for plugin in plugins:
                svc = getattr(plugin, "service", None)
                if svc and hasattr(svc, "open_browser_url"):
                    svc.open_browser_url(WORLDMONITOR_URL, browser_name="chrome", platform="worldmonitor")
                    logger.info("[NewsFeed] Opened worldmonitor.app via browser automation (extension).")
                    return
        except Exception as exc:
            logger.warning("[NewsFeed] Browser automation unavailable: %s", exc)

        # Fallback: OS-level open
        try:
            system = _platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", WORLDMONITOR_URL])
            elif system == "Windows":
                subprocess.Popen(["cmd", "/c", "start", WORLDMONITOR_URL])
            else:
                subprocess.Popen(["xdg-open", WORLDMONITOR_URL])
            logger.info("[NewsFeed] Opened worldmonitor.app via xdg-open.")
        except Exception as exc:
            logger.warning("[NewsFeed] Could not open worldmonitor.app: %s", exc)
