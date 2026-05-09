import os
import re
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.app import FridayApp
from modules.world_monitor.plugin import WorldMonitorPlugin
from modules.world_monitor.service import WorldMonitorService

# Dynamic timestamps so articles always fall within the default 20h window
_NOW_MS = int(time.time() * 1000)
_1H_AGO_MS = _NOW_MS - 3_600_000
_3H_AGO_MS = _NOW_MS - 10_800_000

SAMPLE_BOOTSTRAP = {
    "data": {
        "insights": {
            "worldBrief": "A concise global risk summary.",
            "generatedAt": "2026-04-28T06:50:49.955Z",
            "clusterCount": 239,
            "multiSourceCount": 20,
            "topStories": [
                {
                    "primaryTitle": "Iran tensions disrupt regional shipping",
                    "primarySource": "Reuters",
                    "primaryLink": "https://example.com/iran",
                    "pubDate": _1H_AGO_MS,
                    "importanceScore": 245,
                    "category": "conflict",
                    "threatLevel": "critical",
                    "countryCode": "IR",
                },
                {
                    "primaryTitle": "Colombia highway bombing leaves casualties",
                    "primarySource": "Guardian",
                    "primaryLink": "https://example.com/colombia",
                    "pubDate": _3H_AGO_MS,
                    "importanceScore": 220,
                    "category": "terrorism",
                    "threatLevel": "high",
                    "countryCode": "CO",
                },
            ],
        }
    },
    "missing": [],
}


SAMPLE_TECH_HTML = """
<html>
  <body>
    <main>
      <article>
        <h2>AI chip export rules rattle cloud infrastructure suppliers</h2>
        <p>Reuters</p>
        <time>11h ago</time>
        <p>Large providers are reassessing delivery schedules as new controls reshape near-term capacity plans.</p>
      </article>
      <article>
        <h2>Old semiconductor story should not make the briefing</h2>
        <p>Bloomberg</p>
        <time>24h ago</time>
        <p>This update is outside the requested window and should be filtered out.</p>
      </article>
    </main>
  </body>
</html>
"""


SAMPLE_FEED_DIGEST = {
    "categories": {
        "ai": {
            "items": [
                {
                    "title": "AI chip supply crunch forces cloud providers to revise capacity plans",
                    "description": "Suppliers are prioritizing high-margin accelerator orders as demand keeps rising.",
                    "source": "Reuters",
                    "link": "https://example.com/ai-chip",
                    "publishedAt": _1H_AGO_MS,
                    "threat": {"level": "THREAT_LEVEL_MEDIUM", "category": "supply-chain"},
                }
            ]
        }
    },
    "generatedAt": "2026-04-28T06:50:49.955Z",
}


def test_world_monitor_service_formats_filtered_brief():
    service = WorldMonitorService()

    with patch("modules.world_monitor.service.requests.get") as get:
        get.return_value = MagicMock(
            status_code=200,
            json=lambda: SAMPLE_BOOTSTRAP,
            raise_for_status=lambda: None,
        )

        result = service.get_global_news_brief(focus="Iran", limit=3)

    assert "WorldMonitor intelligence brief" in result
    assert "AI summary: A concise global risk summary." in result
    assert "Iran tensions disrupt regional shipping" in result
    assert "Colombia highway bombing" not in result
    assert re.search(r"\d+(?:st|nd|rd|th) \w+ 2026", result)
    assert "CRITICAL, conflict, IR" in result
    assert "Source: https://example.com/iran" in result


def test_world_monitor_service_sends_public_dashboard_headers_without_key():
    service = WorldMonitorService()

    with patch("modules.world_monitor.service.requests.get") as get:
        get.return_value = MagicMock(
            status_code=200,
            json=lambda: SAMPLE_BOOTSTRAP,
            raise_for_status=lambda: None,
        )

        service.get_global_news_brief()

    headers = get.call_args.kwargs["headers"]
    assert headers["Referer"] == "https://www.worldmonitor.app/"
    assert "X-WorldMonitor-Key" not in headers


def test_world_monitor_service_prefers_configured_api_key():
    class Config:
        def get(self, key, default=None):
            return {
                "world_monitor.api_key": "wm_test_key",
                "world_monitor.public_dashboard_fallback": True,
            }.get(key, default)

    service = WorldMonitorService(Config())

    with patch("modules.world_monitor.service.requests.get") as get:
        get.return_value = MagicMock(
            status_code=200,
            json=lambda: SAMPLE_BOOTSTRAP,
            raise_for_status=lambda: None,
        )

        service.get_global_news_brief()

    headers = get.call_args.kwargs["headers"]
    assert headers["X-WorldMonitor-Key"] == "wm_test_key"
    assert "Referer" not in headers


def test_world_monitor_service_builds_speech_without_raw_source_links():
    service = WorldMonitorService()

    with patch("modules.world_monitor.service.requests.get") as get:
        get.return_value = MagicMock(
            status_code=200,
            json=lambda: SAMPLE_BOOTSTRAP,
            raise_for_status=lambda: None,
        )

        digest = service.get_global_news_digest(limit=2)

    speech = "\n".join(digest["speech_segments"])
    assert "https://" not in speech
    assert "/" not in speech
    assert re.search(r"\d+(?:st|nd|rd|th) \w+ 2026", speech)
    assert "Reported by Reuters" in speech


def test_world_monitor_service_prefers_feed_digest_api_for_category_news():
    class Config:
        def get(self, key, default=None):
            return {
                "world_monitor.feed_api_base_url": "https://worldmonitor.app",
                "world_monitor.timeout_s": 12,
            }.get(key, default)

    service = WorldMonitorService(Config())

    with patch("modules.world_monitor.service.requests.get") as get:
        get.return_value = MagicMock(
            status_code=200,
            json=lambda: SAMPLE_FEED_DIGEST,
            raise_for_status=lambda: None,
        )

        digest = service.get_news_digest(category="tech", limit=3, window_hours=20)

    assert get.call_args.args[0] == "https://worldmonitor.app/api/news/v1/list-feed-digest?variant=tech&lang=en"
    assert digest["dashboard_url"] == "https://tech.worldmonitor.app/"
    assert "AI chip supply crunch" in digest["display_text"]
    assert "World Monitor" not in "\n".join(digest["speech_segments"])


def test_world_monitor_service_builds_category_digest_from_specific_website():
    class Config:
        def get(self, key, default=None):
            return {
                "world_monitor.sources.tech": "https://tech.worldmonitor.app/",
                "world_monitor.timeout_s": 12,
            }.get(key, default)

    service = WorldMonitorService(Config())

    with patch("modules.world_monitor.service.requests.get") as get:
        get.return_value = MagicMock(
            status_code=200,
            headers={"Content-Type": "text/html"},
            text=SAMPLE_TECH_HTML,
            raise_for_status=lambda: None,
        )

        digest = service.get_news_digest(category="tech", limit=3, window_hours=20)

    assert get.call_args.args[0] == "https://tech.worldmonitor.app/"
    assert digest["category"] == "tech"
    assert "WorldMonitor tech news briefing" in digest["display_text"]
    assert "AI chip export rules" in digest["display_text"]
    assert "Old semiconductor story" not in digest["display_text"]
    speech = "\n".join(digest["speech_segments"])
    assert "11 hours ago" in speech
    assert "11h ago" not in speech


def test_world_monitor_service_ignores_dashboard_shell_as_news():
    service = WorldMonitorService()

    articles = service._extract_articles_from_html(
        """
        <main>
          <h1>World Monitor — Real-Time Global Intelligence Dashboard</h1>
          <p>AI-powered real-time global intelligence dashboard with live news and markets.</p>
          <h2>Features</h2>
          <p>435+ curated RSS news feeds, 45 map layers.</p>
        </main>
        """,
        "https://tech.worldmonitor.app/",
    )

    assert articles == []


def test_world_monitor_plugin_speaks_digest_without_reading_browser_page():
    app = FridayApp()
    app.config.config = {
        "world_monitor": {
            "spoken_limit": 3,
        },
        "browser_automation": {
            "preferred_browser": "chrome",
        },
    }
    app.browser_media_service = MagicMock()
    plugin = WorldMonitorPlugin(app)
    plugin.service.get_news_digest = MagicMock(
        return_value={
            "display_text": "WorldMonitor global news briefing\nCritical summaries...",
            "dashboard_url": "https://worldmonitor.app/",
            "source_url": "https://worldmonitor.app/",
            "category": "global",
            "speech_segments": ["Here is your global briefing.", "Story 1.", "Story 2."],
        }
    )
    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    result = plugin.handle_world_monitor_news("world news", {})

    assert result == "Opening and reading the WorldMonitor global briefing."
    plugin.service.get_news_digest.assert_called_once()
    app.browser_media_service.open_browser_url.assert_called_once_with(
        "https://worldmonitor.app/",
        browser_name="chrome",
        platform="world_monitor",
    )
    app.browser_media_service.extract_visible_sections.assert_not_called()
    assert spoken == ["Here is your global briefing.", "Story 1.", "Story 2."]
    assert app.router._voice_already_spoken is True


def test_world_monitor_plugin_uses_requested_segment_only():
    app = FridayApp()
    app.config.config = {
        "world_monitor": {
            "spoken_limit": 3,
        },
        "browser_automation": {
            "preferred_browser": "chrome",
        },
    }
    app.browser_media_service = MagicMock()
    plugin = WorldMonitorPlugin(app)
    plugin.service.get_news_digest = MagicMock(
        return_value={
            "display_text": "WorldMonitor finance news briefing\nCritical summaries...",
            "dashboard_url": "https://finance.worldmonitor.app/",
            "source_url": "https://finance.worldmonitor.app/",
            "category": "finance",
            "speech_segments": ["Here is your finance news briefing.", "Markets moved after central bank comments."],
        }
    )
    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    result = plugin.handle_world_monitor_news("give me finance news", {})

    assert result == "Opening and reading the WorldMonitor finance briefing."
    assert plugin.service.get_news_digest.call_args.kwargs["category"] == "finance"
    app.browser_media_service.open_browser_url.assert_called_once_with(
        "https://finance.worldmonitor.app/",
        browser_name="chrome",
        platform="world_monitor",
    )
    assert spoken == [
        "Here is your finance news briefing.",
        "Markets moved after central bank comments.",
    ]
    app.browser_media_service.extract_visible_sections.assert_not_called()


def test_world_news_routes_directly_to_world_monitor():
    app = FridayApp()
    WorldMonitorPlugin(app)

    plan = app.conversation_agent.plan_turn("what is the latest world news")

    assert plan.mode == "local_tool"
    assert plan.tool_calls[0]["name"] == "get_world_monitor_news"


def test_general_latest_news_routes_directly_to_world_monitor():
    app = FridayApp()
    WorldMonitorPlugin(app)

    plan = app.conversation_agent.plan_turn("what is the latest news")

    assert plan.mode == "local_tool"
    assert plan.tool_calls[0]["name"] == "get_world_monitor_news"


def test_segment_news_routes_directly_to_world_monitor():
    app = FridayApp()
    WorldMonitorPlugin(app)

    plan = app.conversation_agent.plan_turn("what is the latest tech news")

    assert plan.mode == "local_tool"
    assert plan.tool_calls[0]["name"] == "get_world_monitor_news"


def test_stt_technology_variant_routes_directly_to_world_monitor_without_online_prompt():
    app = FridayApp()
    WorldMonitorPlugin(app)

    plan = app.conversation_agent.plan_turn("what is the latest technique")

    assert plan.mode == "local_tool"
    assert plan.tool_calls[0]["name"] == "get_world_monitor_news"


def test_world_monitor_plugin_registers_online_dashboard_tool():
    app = FridayApp()

    plugin = WorldMonitorPlugin(app)

    assert plugin.name == "WorldMonitor"
    descriptor = app.capability_registry.get_descriptor("get_world_monitor_news")
    assert descriptor is not None
    assert descriptor.connectivity == "online"
    assert descriptor.permission_mode == "always_ok"
    assert descriptor.side_effect_level == "write"


def test_world_monitor_service_returns_empty_digest_when_api_key_missing():
    """Without an API key, a 401 from the bootstrap API must not surface as an exception."""
    service = WorldMonitorService()

    def raise_401(*args, **kwargs):
        mock = MagicMock(status_code=401)
        mock.raise_for_status.side_effect = Exception("401 Client Error: Unauthorized")
        return mock

    with patch("modules.world_monitor.service.requests.get", side_effect=raise_401):
        result = service.get_news_digest(category="global", limit=3, window_hours=20)

    assert result["category"] == "global"
    assert result["stories"] == []
    assert "could not find" in result["display_text"].lower()


def test_world_monitor_service_get_full_briefing_returns_all_categories():
    service = WorldMonitorService()

    def make_mock(*args, **kwargs):
        return MagicMock(
            status_code=200,
            headers={"Content-Type": "text/html"},
            text=SAMPLE_TECH_HTML,
            raise_for_status=lambda: None,
        )

    with patch("modules.world_monitor.service.requests.get", side_effect=make_mock):
        digests = service.get_full_briefing(top_n=2, window_hours=20)

    assert set(digests.keys()) == {"global", "tech", "finance", "commodity", "energy", "good"}
    formatted = service.format_full_briefing(digests, top_n=2)
    assert "WorldMonitor Full Briefing" in formatted["display_text"]
    assert "GLOBAL NEWS:" in formatted["display_text"].upper()
    assert "TECH NEWS:" in formatted["display_text"].upper()
    assert len(formatted["speech_segments"]) >= 1


def test_world_monitor_plugin_full_briefing_invoked_on_briefing_keyword():
    app = FridayApp()
    app.config.config = {
        "world_monitor": {"spoken_limit": 3},
        "browser_automation": {"preferred_browser": "chrome"},
    }
    app.browser_media_service = MagicMock()
    plugin = WorldMonitorPlugin(app)
    plugin.service.get_full_briefing = MagicMock(return_value={
        cat: {
            "display_text": f"{cat} news",
            "speech_segments": [f"Top {cat} story."],
            "stories": [{"title": f"{cat} story", "summary": "", "source": ""}],
            "dashboard_url": "https://worldmonitor.app/",
            "category": cat,
        }
        for cat in ("global", "tech", "finance", "commodity", "energy", "good")
    })
    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    result = plugin.handle_world_monitor_news("give me a world monitor briefing", {})

    plugin.service.get_full_briefing.assert_called_once()
    assert result == "Opening and reading the full WorldMonitor briefing."
    assert len(spoken) >= 1


def test_world_monitor_plugin_single_category_skips_full_briefing():
    app = FridayApp()
    app.config.config = {
        "world_monitor": {"spoken_limit": 3},
        "browser_automation": {"preferred_browser": "chrome"},
    }
    app.browser_media_service = MagicMock()
    plugin = WorldMonitorPlugin(app)
    plugin.service.get_news_digest = MagicMock(return_value={
        "display_text": "tech briefing",
        "speech_segments": ["Tech story."],
        "stories": [],
        "dashboard_url": "https://tech.worldmonitor.app/",
        "category": "tech",
    })
    plugin.service.get_full_briefing = MagicMock()
    app.event_bus.subscribe("voice_response", lambda _: None)

    plugin.handle_world_monitor_news("give me a tech news briefing", {})

    plugin.service.get_full_briefing.assert_not_called()
    plugin.service.get_news_digest.assert_called_once()
