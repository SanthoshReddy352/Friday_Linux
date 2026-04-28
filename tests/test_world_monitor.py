import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.app import FridayApp
from modules.world_monitor.plugin import WorldMonitorPlugin
from modules.world_monitor.service import WorldMonitorService


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
                    "pubDate": 1777352556000,
                    "importanceScore": 245,
                    "category": "conflict",
                    "threatLevel": "critical",
                    "countryCode": "IR",
                },
                {
                    "primaryTitle": "Colombia highway bombing leaves casualties",
                    "primarySource": "Guardian",
                    "primaryLink": "https://example.com/colombia",
                    "pubDate": 1777310589000,
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
    assert "28th April 2026" in result
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
    assert "28th April 2026" in speech
    assert "Reported by Reuters" in speech


def test_world_monitor_plugin_opens_dashboard_speaks_and_scrolls():
    app = FridayApp()
    app.config.config = {
        "world_monitor": {
            "scroll_pause_s": 0,
            "spoken_limit": 3,
        },
        "browser_automation": {
            "preferred_browser": "chrome",
        },
    }
    app.browser_media_service = MagicMock()
    plugin = WorldMonitorPlugin(app)
    plugin.service.get_global_news_digest = MagicMock(
        return_value={
            "display_text": "WorldMonitor intelligence brief\nTop stories...",
            "dashboard_url": "https://www.worldmonitor.app/",
            "speech_segments": ["Opening WorldMonitor.", "Story 1.", "Story 2."],
        }
    )
    spoken = []
    app.event_bus.subscribe("voice_response", spoken.append)

    result = plugin.handle_world_monitor_news("world news", {})

    assert result == "WorldMonitor intelligence brief\nTop stories..."
    app.browser_media_service.open_browser_url.assert_called_once_with(
        "https://www.worldmonitor.app/",
        browser_name="chrome",
        platform="world_monitor",
    )
    assert app.browser_media_service.scroll_page.call_count == 2
    assert spoken == ["Opening WorldMonitor.", "Story 1.", "Story 2."]
    assert app.router._voice_already_spoken is True


def test_world_news_routes_directly_to_world_monitor():
    app = FridayApp()
    WorldMonitorPlugin(app)

    plan = app.conversation_agent.plan_turn("what is the latest world news")

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
