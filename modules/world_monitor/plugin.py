import time

from core.logger import logger
from core.plugin_manager import FridayPlugin

from .service import WorldMonitorService


class WorldMonitorPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "WorldMonitor"
        self.service = WorldMonitorService(getattr(app, "config", None))
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "get_world_monitor_news",
            "description": (
                "Fetch WorldMonitor's AI global intelligence news summary and ranked top stories. "
                "Use for current geopolitical, conflict, crisis, sanctions, infrastructure, weather, "
                "economic, military, and global risk updates."
            ),
            "parameters": {
                "focus": "string - optional topic filter such as Iran, sanctions, conflict, cyber, oil, weather",
                "country_code": "string - optional ISO 3166-1 alpha-2 country code such as IR, US, UA, CN",
                "limit": "integer - optional number of stories, 1 to 12",
                "min_threat": "string - optional minimum threat level: info, low, medium, high, critical",
            },
            "aliases": [
                "world monitor",
                "global intelligence",
                "global news",
                "global news brief",
                "geopolitical brief",
                "latest world news",
                "world news",
                "world news intelligence",
            ],
            "patterns": [
                r"\b(?:what(?:'s| is)?|give me|show me|tell me|read me|open)?\s*(?:the\s+)?(?:latest\s+|current\s+)?world news\b",
                r"\b(?:global intelligence|global news|geopolitical brief|world monitor)\b",
            ],
            "context_terms": [
                "worldmonitor",
                "world monitor",
                "global news",
                "global intelligence",
                "geopolitics",
                "conflict",
                "crisis",
                "sanctions",
                "military",
                "threat",
                "risk",
                "world news",
            ],
        }, self.handle_world_monitor_news, capability_meta={
            "connectivity": "online",
            "latency_class": "interactive",
            "permission_mode": "always_ok",
            "side_effect_level": "write",
            "resources": [
                {"type": "web", "url": "https://www.worldmonitor.app/"},
                {"type": "source", "url": "https://github.com/koala73/worldmonitor"},
            ],
        })

        logger.info("WorldMonitorPlugin loaded.")

    def handle_world_monitor_news(self, text, args):
        args = dict(args or {})
        focus = args.get("focus") or self._infer_focus(text)
        country_code = args.get("country_code") or ""
        limit = args.get("limit") or 6
        min_threat = args.get("min_threat") or ""
        try:
            digest = self.service.get_global_news_digest(
                focus=focus,
                country_code=country_code,
                limit=limit,
                min_threat=min_threat,
            )
            self._present_digest(digest)
            return digest["display_text"]
        except Exception as exc:
            return (
                "I could not reach WorldMonitor right now. "
                f"Reason: {exc}. "
                "If this keeps happening, set world_monitor.api_key in config.yaml."
            )

    def _present_digest(self, digest):
        router = getattr(self.app, "router", None)
        if router is not None and hasattr(router, "_voice_already_spoken"):
            router._voice_already_spoken = True

        browser = getattr(self.app, "browser_media_service", None)
        if browser is not None:
            try:
                if not self._browser_disabled_reason():
                    browser_name = self._config_get("browser_automation.preferred_browser", "chrome") or "chrome"
                    browser.open_browser_url(digest["dashboard_url"], browser_name=browser_name, platform="world_monitor")
            except Exception as exc:
                logger.warning("WorldMonitor dashboard open failed: %s", exc)

        speech_segments = list(digest.get("speech_segments") or [])
        max_segments = self._safe_int(self._config_get("world_monitor.spoken_limit", 5), 5)
        max_segments = max(1, min(8, max_segments))
        pause_s = self._safe_float(self._config_get("world_monitor.scroll_pause_s", 1.35), 1.35)
        scroll_pixels = self._safe_int(self._config_get("world_monitor.scroll_pixels", 420), 420)

        for index, segment in enumerate(speech_segments[:max_segments]):
            if segment:
                self.app.event_bus.publish("voice_response", segment)
            if browser is not None and index < min(len(speech_segments), max_segments) - 1:
                if pause_s > 0:
                    time.sleep(min(pause_s, 5.0))
                try:
                    browser.scroll_page(platform="world_monitor", pixels=scroll_pixels)
                except Exception as exc:
                    logger.debug("WorldMonitor dashboard scroll failed: %s", exc)

    def _infer_focus(self, text):
        raw = str(text or "").strip()
        lowered = raw.lower()
        markers = (
            "about ",
            "on ",
            "for ",
            "regarding ",
        )
        for marker in markers:
            if marker in lowered:
                return raw[lowered.rfind(marker) + len(marker):].strip(" ?.")
        return ""

    def _config_get(self, key, default=None):
        config = getattr(self.app, "config", None)
        if config and hasattr(config, "get"):
            return config.get(key, default)
        return default

    def _safe_int(self, value, default):
        try:
            return int(value)
        except Exception:
            return int(default)

    def _safe_float(self, value, default):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _browser_disabled_reason(self):
        if not self._config_get("browser_automation.enabled", True):
            return "Browser automation is disabled in the FRIDAY configuration."
        if not self._config_get("browser_automation.allow_online", True):
            return "Browser automation is currently disabled because online features are turned off."
        return ""


def setup(app):
    return WorldMonitorPlugin(app)
