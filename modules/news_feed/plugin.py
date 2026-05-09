"""Feed Prism news feed plugin.

Registers six single-category news tools and one cumulative briefing tool.
Individual category tools return the top 5 articles (title + body).
The briefing tool fetches 3 per category, opens worldmonitor.app, and
delivers a LLM-summarised spoken digest.
"""
from core.plugin_manager import FridayPlugin
from core.logger import logger

from .service import NewsFeedService, CATEGORY_CONFIG


_SINGLE_TOOLS = [
    (
        "get_technology_news",
        "technology",
        "Fetch the top 5 technology news articles from TechCrunch, The Verge, and Wired via Feed Prism.",
    ),
    (
        "get_global_news_feed",
        "global",
        "Fetch the top 5 global/world news headlines from Feed Prism.",
    ),
    (
        "get_company_news",
        "company",
        "Fetch the top 5 big-tech company announcements from Google Blog and Apple Newsroom via Feed Prism.",
    ),
    (
        "get_startup_news",
        "startups",
        "Fetch the top 5 startup and product launch stories from Product Hunt via Feed Prism.",
    ),
    (
        "get_security_news",
        "security",
        "Fetch the top 5 cybersecurity news stories from The Hacker News via Feed Prism.",
    ),
    (
        "get_business_news",
        "business",
        "Fetch the top 5 business news articles from Forbes Business via Feed Prism.",
    ),
]


class NewsFeedPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "NewsFeed"
        self.service = NewsFeedService(app)
        self.on_load()

    def on_load(self):
        capability_meta = {
            "connectivity": "online",
            "latency_class": "slow",
            "permission_mode": "always_ok",
            "side_effect_level": "read",
            "streaming": False,
        }

        # Register one tool per category
        for tool_name, category_key, description in _SINGLE_TOOLS:
            key = category_key  # capture for closure
            self.app.router.register_tool(
                {"name": tool_name, "description": description, "parameters": {}},
                lambda raw, args, _k=key: self._handle_category(raw, args, _k),
                capability_meta=capability_meta,
            )

        # Register cumulative briefing tool
        self.app.router.register_tool(
            {
                "name": "get_news_briefing",
                "description": (
                    "Fetch a comprehensive news digest from all Feed Prism categories "
                    "(Technology, Global News, Company News, Startups, Security, Business), "
                    "open worldmonitor.app in the browser, and deliver a summarised spoken briefing."
                ),
                "parameters": {},
            },
            self._handle_briefing,
            capability_meta=capability_meta,
        )

        logger.info("NewsFeedPlugin loaded — %d category tools + briefing.", len(_SINGLE_TOOLS))

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _handle_category(self, raw_text: str, args: dict, category_key: str) -> str:
        logger.info("[NewsFeed] Category request: %s", category_key)
        category_label = category_key.replace("_", " ")
        self.app.event_bus.publish("voice_response", f"Fetching the latest {category_label} news for you. Just a second.")
        try:
            return self.service.get_category_news(category_key, limit=5)
        except Exception as exc:
            logger.error("[NewsFeed] Category %s error: %s", category_key, exc)
            return "I ran into a problem fetching that category. Please try again."

    def _handle_briefing(self, raw_text: str, args: dict) -> str:
        logger.info("[NewsFeed] Cumulative briefing request.")
        self.app.event_bus.publish("voice_response", "Gathering your comprehensive news briefing. This might take a moment.")
        try:
            return self.service.get_news_briefing(limit_per_category=3)
        except Exception as exc:
            logger.error("[NewsFeed] Briefing error: %s", exc)
            return "I ran into a problem generating the news briefing. Please try again."


def setup(app):
    return NewsFeedPlugin(app)
