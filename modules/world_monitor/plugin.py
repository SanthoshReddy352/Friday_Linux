import re

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
                "Fetch concise WorldMonitor news briefings from category-specific websites. "
                "Use global for worldnews.app, or category-specific feeds for tech, finance, "
                "commodity, energy, and good news."
            ),
            "parameters": {
                "category": "string - optional segment: global, tech, finance, commodity, energy, or good",
                "focus": "string - optional topic filter such as Iran, sanctions, conflict, cyber, oil, weather",
                "country_code": "string - optional ISO 3166-1 alpha-2 country code such as IR, US, UA, CN",
                "limit": "integer - optional number of stories, 1 to 12",
                "min_threat": "string - optional minimum threat level: info, low, medium, high, critical",
                "window_hours": "integer - optional recent-news window in hours, defaults to 20",
            },
            "aliases": [
                "world monitor",
                "global intelligence",
                "global news",
                "global news brief",
                "geopolitical brief",
                "latest world news",
                "latest news",
                "news briefing",
                "news brief",
                "world news",
                "world news intelligence",
                "tech news",
                "technology news",
                "latest technology",
                "latest technique",
                "finance news",
                "financial news",
                "market news",
                "commodity news",
                "commodities news",
                "energy news",
                "good news",
                "happy news",
            ],
            "patterns": [
                r"\b(?:what(?:'s| is)?|give me|show me|tell me|read me|open)?\s*(?:the\s+)?(?:latest\s+|current\s+)?world news\b",
                r"\b(?:what(?:'s| is)?|give me|show me|tell me|read me|brief me on|summarize)?\s*(?:the\s+)?(?:latest\s+|current\s+)?(?:news|news briefing|news brief)\b",
                r"\b(?:global intelligence|global news|geopolitical brief|world monitor)\b",
                r"\b(?:what(?:'s| is)?|give me|show me|tell me|read me|brief me on|summarize|open)?\s*(?:the\s+)?(?:latest\s+|current\s+)?(?:tech|technology|finance|financial|market|commodity|commodities|energy|good|happy) news\b",
                r"\b(?:what(?:'s| is)?|give me|show me|tell me|read me|brief me on|summarize)?\s*(?:the\s+)?(?:latest|current)\s+(?:tech|technology|technique)\b",
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
                "tech news",
                "technology",
                "technique",
                "finance",
                "financial",
                "market",
                "commodity",
                "commodities",
                "energy",
                "good news",
                "happy",
            ],
        }, self.handle_world_monitor_news, capability_meta={
            "connectivity": "online",
            "latency_class": "interactive",
            "permission_mode": "always_ok",
            "side_effect_level": "write",
            "resources": [
                {"type": "web", "url": "https://worldmonitor.app/"},
                {"type": "web", "url": "https://tech.worldmonitor.app/"},
                {"type": "web", "url": "https://finance.worldmonitor.app/"},
                {"type": "web", "url": "https://commodity.worldmonitor.app/"},
                {"type": "web", "url": "https://energy.worldmonitor.app/"},
                {"type": "web", "url": "https://happy.worldmonitor.app/"},
                {"type": "source", "url": "https://github.com/koala73/worldmonitor"},
            ],
        })

        logger.info("WorldMonitorPlugin loaded.")

    def handle_world_monitor_news(self, text, args):
        args = dict(args or {})
        category = args.get("category") or self._infer_category(text)
        focus = args.get("focus") or self._infer_focus(text)
        country_code = args.get("country_code") or ""
        limit = args.get("limit") or 8
        min_threat = args.get("min_threat") or ""
        window_hours = args.get("window_hours") or 20
        try:
            digest = self.service.get_news_digest(
                category=category,
                focus=focus,
                country_code=country_code,
                limit=limit,
                min_threat=min_threat,
                window_hours=window_hours,
            )
            return self._present_digest(digest)
        except Exception as exc:
            return (
                "I could not reach WorldMonitor right now. "
                f"Reason: {exc}. "
                "If this keeps happening, set world_monitor.api_key in config.yaml."
            )

    def _present_digest(self, digest):
        routing_state = getattr(self.app, "routing_state", None)
        if routing_state is not None:
            routing_state.mark_voice_spoken()

        max_segments = self._safe_int(self._config_get("world_monitor.spoken_limit", 9), 9)
        max_segments = max(1, min(12, max_segments))
        segments = list(digest.get("speech_segments") or [])

        category = str(digest.get("category") or "global").replace("_", " ")
        dashboard_url = digest.get("dashboard_url") or digest.get("source_url") or ""

        browser = getattr(self.app, "browser_media_service", None)
        if browser is not None and dashboard_url:
            try:
                if not self._browser_disabled_reason():
                    browser_name = self._config_get("browser_automation.preferred_browser", "chrome") or "chrome"
                    browser.open_browser_url(dashboard_url, browser_name=browser_name, platform="world_monitor")
            except Exception as exc:
                logger.warning("WorldMonitor dashboard open failed: %s", exc)

        for segment in segments[:max_segments]:
            self.app.event_bus.publish("voice_response", segment)

        if segments:
            return f"Opening and reading the WorldMonitor {category} briefing."
        message = f"I could not find a recent WorldMonitor {category} briefing."
        self.app.event_bus.publish("voice_response", message)
        return message


    def _infer_category(self, text):
        lowered = str(text or "").lower()
        if re.search(r"\b(?:tech|technology|technique)\b", lowered):
            return "tech"
        if re.search(r"\b(?:finance|financial|market|markets|stocks?|equities|earnings)\b", lowered):
            return "finance"
        if re.search(r"\b(?:commodity|commodities|metals?|gold|copper|wheat)\b", lowered):
            return "commodity"
        if re.search(r"\b(?:energy|oil|gas|power|electricity)\b", lowered):
            return "energy"
        if re.search(r"\b(?:good news|happy news|positive news|uplifting)\b", lowered):
            return "good"
        return "global"

    def _infer_focus(self, text):
        raw = str(text or "").strip()
        lowered = raw.lower()
        if self._infer_category(text) != "global":
            for phrase in (
                "tech news",
                "technology news",
                "finance news",
                "financial news",
                "market news",
                "markets news",
                "commodity news",
                "commodities news",
                "energy news",
                "good news",
                "happy news",
                "positive news",
            ):
                lowered = lowered.replace(phrase, "")
                raw = raw.replace(phrase, "")
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

    def _browser_disabled_reason(self):
        if not self._config_get("browser_automation.enabled", True):
            return "Browser automation is disabled in the FRIDAY configuration."
        if not self._config_get("browser_automation.allow_online", True):
            return "Browser automation is currently disabled because online features are turned off."
        return ""


def setup(app):
    return WorldMonitorPlugin(app)
