from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import requests


DEFAULT_API_BASE_URL = "https://api.worldmonitor.app"
DEFAULT_WEB_BASE_URL = "https://www.worldmonitor.app"
USER_AGENT = "FRIDAY-WorldMonitor/1.0 (+https://github.com/koala73/worldmonitor)"

THREAT_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


class WorldMonitorService:
    def __init__(self, config=None):
        self.config = config

    def get_global_news_brief(
        self,
        focus="",
        country_code="",
        limit=6,
        min_threat="",
    ):
        return self.get_global_news_digest(
            focus=focus,
            country_code=country_code,
            limit=limit,
            min_threat=min_threat,
        )["display_text"]

    def get_global_news_digest(
        self,
        focus="",
        country_code="",
        limit=6,
        min_threat="",
    ):
        payload = self._fetch_bootstrap(["insights"])
        insights = (payload.get("data") or {}).get("insights") or {}
        stories = self._filter_stories(
            insights.get("topStories") or [],
            focus=focus,
            country_code=country_code,
            min_threat=min_threat,
        )
        limit = self._safe_limit(limit)
        stories = stories[:limit]
        return {
            "display_text": self._format_brief(insights, stories, focus=focus, country_code=country_code),
            "speech_segments": self._format_speech_segments(insights, stories, focus=focus, country_code=country_code),
            "stories": stories,
            "dashboard_url": self._config_str("world_monitor.web_base_url", DEFAULT_WEB_BASE_URL).rstrip("/") + "/",
        }

    def _fetch_bootstrap(self, keys):
        api_base = self._config_str("world_monitor.api_base_url", DEFAULT_API_BASE_URL).rstrip("/")
        web_base = self._config_str("world_monitor.web_base_url", DEFAULT_WEB_BASE_URL).rstrip("/")
        timeout = self._config_float("world_monitor.timeout_s", 12.0)
        params = urlencode({"keys": ",".join(keys)})
        url = f"{api_base}/api/bootstrap?{params}"

        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        api_key = self._config_str("world_monitor.api_key", "") or self._config_str("world_monitor_api_key", "")
        if api_key:
            headers["X-WorldMonitor-Key"] = api_key
        elif self._config_bool("world_monitor.public_dashboard_fallback", True):
            headers["Referer"] = f"{web_base}/"

        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("WorldMonitor returned an unexpected response.")
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return data

    def _filter_stories(self, stories, focus="", country_code="", min_threat=""):
        focus = str(focus or "").strip().lower()
        country_code = str(country_code or "").strip().upper()
        min_rank = THREAT_RANK.get(str(min_threat or "").strip().lower(), -1)
        filtered = []

        for story in stories:
            if not isinstance(story, dict):
                continue
            if country_code and str(story.get("countryCode") or "").upper() != country_code:
                continue
            threat = str(story.get("threatLevel") or "info").lower()
            if min_rank >= 0 and THREAT_RANK.get(threat, 0) < min_rank:
                continue
            haystack = " ".join(
                str(story.get(key) or "")
                for key in ("primaryTitle", "primarySource", "category", "threatLevel", "countryCode")
            ).lower()
            if focus and focus not in haystack:
                continue
            filtered.append(story)

        return sorted(
            filtered,
            key=lambda item: int(item.get("importanceScore") or 0),
            reverse=True,
        )

    def _format_brief(self, insights, stories, focus="", country_code=""):
        generated_at = self._format_datetime(insights.get("generatedAt"))
        scope = []
        if focus:
            scope.append(f"focus: {focus}")
        if country_code:
            scope.append(f"country: {str(country_code).upper()}")
        scope_text = f" ({', '.join(scope)})" if scope else ""

        lines = [f"WorldMonitor intelligence brief{scope_text}"]
        if generated_at:
            lines.append(f"Generated: {generated_at}")

        world_brief = str(insights.get("worldBrief") or "").strip()
        if world_brief:
            lines.append(f"AI summary: {world_brief}")

        cluster_count = insights.get("clusterCount")
        multi_source_count = insights.get("multiSourceCount")
        if cluster_count is not None or multi_source_count is not None:
            lines.append(
                f"Signals: {cluster_count or 0} clusters, {multi_source_count or 0} multi-source confirmations."
            )

        if not stories:
            lines.append("No matching WorldMonitor stories were returned for that filter.")
            return "\n".join(lines)

        lines.append("Top stories:")
        for index, story in enumerate(stories, start=1):
            title = str(story.get("primaryTitle") or "Untitled story").strip()
            source = str(story.get("primarySource") or "Unknown source").strip()
            threat = str(story.get("threatLevel") or "info").upper()
            category = str(story.get("category") or "news").strip()
            country = str(story.get("countryCode") or "").strip().upper()
            date_text = self._format_date(story.get("pubDate"))
            link = str(story.get("primaryLink") or "").strip()
            meta = ", ".join(part for part in (threat, category, country, date_text) if part)
            line = f"{index}. {title} — {source}"
            if meta:
                line += f" [{meta}]"
            if link:
                line += f"\n   Source: {link}"
            lines.append(line)

        return "\n".join(lines)

    def _format_speech_segments(self, insights, stories, focus="", country_code=""):
        scope = []
        if focus:
            scope.append(str(focus).strip())
        if country_code:
            scope.append(str(country_code).upper())
        scope_text = f" for {' and '.join(scope)}" if scope else ""

        segments = []
        world_brief = str(insights.get("worldBrief") or "").strip()
        if world_brief:
            segments.append(f"Opening WorldMonitor. Here is the global intelligence picture{scope_text}. {world_brief}")
        else:
            segments.append(f"Opening WorldMonitor for the latest world news{scope_text}.")

        for index, story in enumerate(stories, start=1):
            title = str(story.get("primaryTitle") or "Untitled story").strip()
            source = str(story.get("primarySource") or "").strip()
            threat = str(story.get("threatLevel") or "").strip().lower()
            category = str(story.get("category") or "").strip().lower()
            country = str(story.get("countryCode") or "").strip().upper()
            date_text = self._format_date(story.get("pubDate"))

            details = []
            if threat and threat != "info":
                details.append(f"{threat} threat")
            if category:
                details.append(category)
            if country:
                details.append(country)
            if date_text:
                details.append(date_text)

            detail_text = f" This is marked as {', '.join(details)}." if details else ""
            source_text = f" Reported by {source}." if source else ""
            segments.append(f"Story {index}: {title}.{detail_text}{source_text}")

        if not stories:
            segments.append("WorldMonitor did not return matching stories for that filter.")

        return segments

    def _format_datetime(self, value):
        dt = self._parse_datetime(value)
        if dt is None:
            return "" if value in (None, "") else str(value)
        date_text = self._format_date_from_datetime(dt)
        return f"{date_text}, {dt.hour:02d}:{dt.minute:02d} UTC"

    def _format_date(self, value):
        dt = self._parse_datetime(value)
        if dt is None:
            return "" if value in (None, "") else str(value)
        return self._format_date_from_datetime(dt)

    def _parse_datetime(self, value):
        if value in (None, ""):
            return None
        try:
            if isinstance(value, (int, float)):
                timestamp = float(value)
                if timestamp > 10_000_000_000:
                    timestamp = timestamp / 1000.0
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                text = str(value).replace("Z", "+00:00")
                dt = datetime.fromisoformat(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _format_date_from_datetime(self, dt):
        day = dt.day
        return f"{day}{self._ordinal_suffix(day)} {dt.strftime('%B')} {dt.year}"

    def _ordinal_suffix(self, day):
        if 10 <= day % 100 <= 20:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    def _safe_limit(self, value):
        try:
            return max(1, min(12, int(value)))
        except Exception:
            return 6

    def _config_str(self, key, default=""):
        config = self.config
        if config and hasattr(config, "get"):
            value = config.get(key, default)
        else:
            value = default
        return str(value or "").strip()

    def _config_float(self, key, default):
        try:
            return float(self._config_str(key, default))
        except Exception:
            return float(default)

    def _config_bool(self, key, default=False):
        config = self.config
        if config and hasattr(config, "get"):
            value = config.get(key, default)
        else:
            value = default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
