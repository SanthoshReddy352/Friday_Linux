from core.logger import logger
from core.plugin_manager import FridayPlugin

from .service import BrowserMediaService


class BrowserAutomationPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "BrowserAutomation"
        self.service = BrowserMediaService(app)
        self.app.browser_media_service = self.service
        self.on_load()

    def on_load(self):
        self.app.router.register_tool({
            "name": "open_browser_url",
            "description": "Open a website in a controlled browser session.",
            "parameters": {
                "url": "string - website URL to open",
                "browser_name": "string - preferred browser, usually chrome",
            },
            "context_terms": ["browser", "chrome", "youtube", "youtube music"],
        }, self.handle_open_browser_url, capability_meta={
            "connectivity": "online",
            "latency_class": "interactive",
            "permission_mode": "ask_first",
            "side_effect_level": "write",
        })

        self.app.router.register_tool({
            "name": "play_youtube",
            "description": "Search for a video on YouTube and start playback in a controlled browser session.",
            "parameters": {
                "query": "string - video title or search terms",
                "browser_name": "string - preferred browser, usually chrome",
            },
            "context_terms": ["play youtube", "video", "music video", "youtube"],
        }, self.handle_play_youtube, capability_meta={
            "connectivity": "online",
            "latency_class": "interactive",
            "permission_mode": "ask_first",
            "side_effect_level": "write",
        })

        self.app.router.register_tool({
            "name": "play_youtube_music",
            "description": "Search for a song on YouTube Music and start playback in a controlled browser session.",
            "parameters": {
                "query": "string - song title or search terms",
                "browser_name": "string - preferred browser, usually chrome",
            },
            "context_terms": ["youtube music", "song", "album", "playlist"],
        }, self.handle_play_youtube_music, capability_meta={
            "connectivity": "online",
            "latency_class": "interactive",
            "permission_mode": "ask_first",
            "side_effect_level": "write",
        })

        self.app.router.register_tool({
            "name": "browser_media_control",
            "description": "Control active browser playback such as pause, resume, or next.",
            "parameters": {
                "control": "string - one of pause, resume, next, play",
            },
            "context_terms": ["pause", "resume", "next", "skip", "browser media"],
        }, self.handle_browser_media_control, capability_meta={
            "connectivity": "online",
            "latency_class": "interactive",
            "permission_mode": "ask_first",
            "side_effect_level": "write",
        })

        logger.info("BrowserAutomationPlugin loaded.")

    def handle_open_browser_url(self, text, args):
        disabled_reason = self._disabled_reason()
        if disabled_reason:
            return disabled_reason
        url = args.get("url") or "https://www.youtube.com"
        browser_name = args.get("browser_name") or "chrome"
        orchestrator = getattr(self.app, "workflow_orchestrator", None)
        if orchestrator:
            result = orchestrator.run(
                "browser_media",
                text,
                self.app.session_id,
                {"action": "open_browser_url", "url": url, "browser_name": browser_name},
            )
            if result.handled:
                return result.response
        return self.service.open_browser_url(url, browser_name=browser_name)

    def handle_play_youtube(self, text, args):
        disabled_reason = self._disabled_reason()
        if disabled_reason:
            return disabled_reason
        query = args.get("query", "").strip()
        browser_name = args.get("browser_name") or "chrome"
        orchestrator = getattr(self.app, "workflow_orchestrator", None)
        if orchestrator:
            result = orchestrator.run(
                "browser_media",
                text,
                self.app.session_id,
                {"action": "play_youtube", "query": query, "browser_name": browser_name},
            )
            if result.handled:
                return result.response
        return self.service.play_youtube(query, browser_name=browser_name)

    def handle_play_youtube_music(self, text, args):
        disabled_reason = self._disabled_reason()
        if disabled_reason:
            return disabled_reason
        query = args.get("query", "").strip()
        browser_name = args.get("browser_name") or "chrome"
        orchestrator = getattr(self.app, "workflow_orchestrator", None)
        if orchestrator:
            result = orchestrator.run(
                "browser_media",
                text,
                self.app.session_id,
                {"action": "play_youtube_music", "query": query, "browser_name": browser_name},
            )
            if result.handled:
                return result.response
        return self.service.play_youtube_music(query, browser_name=browser_name)

    def handle_browser_media_control(self, text, args):
        disabled_reason = self._disabled_reason()
        if disabled_reason:
            return disabled_reason
        control = args.get("control") or ""
        orchestrator = getattr(self.app, "workflow_orchestrator", None)
        if orchestrator:
            result = orchestrator.run(
                "browser_media",
                text,
                self.app.session_id,
                {"action": "browser_media_control", "control": control},
            )
            if result.handled:
                return result.response
        return self.service.browser_media_control(control)

    def _disabled_reason(self):
        config = getattr(self.app, "config", None)
        if not config:
            return ""
        if not config.get("browser_automation.enabled", True):
            return "Browser automation is disabled in the FRIDAY configuration."
        if not config.get("browser_automation.allow_online", True):
            return "Browser automation is currently disabled because online features are turned off."
        return ""


def setup(app):
    return BrowserAutomationPlugin(app)
