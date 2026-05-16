"""Tests for Batch 5 — Missing tools & confirmation hygiene (Issues 12, 13).

Covers:
* Weather plugin: location extraction from text, report formatting, cache
  read/write, and graceful error when requests/Open-Meteo fail.
* GWS calendar resolver: title fuzzy match, "next" sentinel, clock-time
  match, "couldn't find" fallback.
* Capability broker pending_online TTL — a stale proposal does not resolve.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.capability_broker import CapabilityBroker
from modules.weather import openmeteo
from modules.weather.plugin import WeatherPlugin


# ---------------------------------------------------------------------------
# Weather plugin
# ---------------------------------------------------------------------------


class _FakeApp:
    class _Router:
        def __init__(self):
            self.tools_registered = []

        def register_tool(self, spec, handler, capability_meta=None):
            self.tools_registered.append((spec["name"], spec, capability_meta))

    def __init__(self):
        self.router = self._Router()


@pytest.fixture
def weather_plugin(monkeypatch, tmp_path):
    # Redirect the on-disk cache so tests don't touch ~/.cache.
    monkeypatch.setattr(openmeteo, "_cache_dir", lambda: str(tmp_path))
    app = _FakeApp()
    return WeatherPlugin(app)


class TestWeatherPlugin:
    def test_registers_tool_with_online_metadata(self, weather_plugin):
        tools = weather_plugin.app.router.tools_registered
        assert any(name == "get_weather" for name, _, _ in tools)
        name, spec, meta = [t for t in tools if t[0] == "get_weather"][0]
        assert meta["connectivity"] == "online"
        assert meta["latency_class"] == "fast"
        # Critical for Issue 13: this tool must not trigger the "Go online?"
        # prompt because weather is universally implicit-online.
        assert meta["permission_mode"] == "always_ok"

    def test_extracts_location_from_natural_phrasing(self, weather_plugin):
        assert weather_plugin._extract_location("what's the weather in Mumbai") == "Mumbai"
        assert weather_plugin._extract_location("weather for Bangalore tomorrow").lower() == "bangalore"
        assert weather_plugin._extract_location("how's the weather in New York today").lower() == "new york"

    def test_handle_get_weather_requests_location_when_missing(self, weather_plugin):
        reply = weather_plugin.handle_get_weather("weather", {})
        assert "city" in reply.lower() or "area" in reply.lower()

    def test_handle_get_weather_uses_openmeteo_and_formats(self, weather_plugin, monkeypatch):
        report = openmeteo.WeatherReport(
            location=openmeteo.GeocodeResult(
                name="Mumbai", latitude=19.07, longitude=72.87, country="India"
            ),
            temperature_c=31.0,
            apparent_c=35.0,
            humidity_pct=78,
            wind_kph=12.0,
            weather_code=2,
            description="partly cloudy",
        )
        monkeypatch.setattr(openmeteo, "current_weather", lambda loc: report)
        reply = weather_plugin.handle_get_weather("what's the weather in Mumbai", {})
        assert "Mumbai" in reply
        assert "31" in reply
        assert "partly cloudy" in reply
        # Feels-like differs by ≥2 so it shows up.
        assert "35" in reply
        assert "humidity" in reply.lower()
        assert "wind" in reply.lower()

    def test_handle_get_weather_surfaces_weather_error(self, weather_plugin, monkeypatch):
        def _boom(_loc):
            raise openmeteo.WeatherError("network unreachable")
        monkeypatch.setattr(openmeteo, "current_weather", _boom)
        reply = weather_plugin.handle_get_weather("weather in Mars Colony", {})
        assert "couldn't" in reply.lower()
        assert "mars colony" in reply.lower()


class TestWeatherCache:
    def test_cache_read_returns_none_for_expired_payload(self, tmp_path, monkeypatch):
        monkeypatch.setattr(openmeteo, "_cache_dir", lambda: str(tmp_path))
        # Write a cache entry that's two days old.
        openmeteo._write_cache("staleville", {"geocode": {"name": "Stale"}})
        path = openmeteo._cache_path("staleville")
        old = time.time() - (3 * 24 * 60 * 60)
        import json
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["saved_at"] = old
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        assert openmeteo._read_cache("staleville") is None

    def test_cache_key_normalizes_whitespace_and_case(self, tmp_path, monkeypatch):
        monkeypatch.setattr(openmeteo, "_cache_dir", lambda: str(tmp_path))
        openmeteo._write_cache("  Mumbai  ", {"hello": "world"})
        # Different-cased / spaced version hits the same file.
        cached = openmeteo._read_cache("mumbai")
        assert cached is not None
        assert cached["hello"] == "world"


class TestWeatherDescribe:
    def test_known_weather_code_returns_text(self):
        assert "rain" in openmeteo.describe_weather_code(61)
        assert "clear" in openmeteo.describe_weather_code(0)

    def test_unknown_code_falls_back_to_number(self):
        out = openmeteo.describe_weather_code(999)
        assert "999" in out


# ---------------------------------------------------------------------------
# GWS calendar event resolver (Issue 12)
# ---------------------------------------------------------------------------


class _StubGWSExtension:
    """Minimal stub with just the resolver-related methods so we can drive
    the matcher in isolation without booting the full extension."""

    from modules.workspace_agent.extension import (  # type: ignore[import-untyped]
        WorkspaceAgentExtension as _Ext,
    )
    _resolve_event = _Ext._resolve_event
    _parse_iso = _Ext._parse_iso
    _auth_aware_error = _Ext._auth_aware_error


def _events_fixture():
    base = datetime.now().replace(minute=0, second=0, microsecond=0)
    return [
        {
            "id": "evt-1",
            "summary": "Dentist appointment",
            "start": (base + timedelta(hours=2)).isoformat(),
        },
        {
            "id": "evt-2",
            "summary": "Team standup",
            "start": (base + timedelta(hours=4)).isoformat(),
        },
        {
            "id": "evt-3",
            "summary": "Q4 review",
            "start": (base + timedelta(days=1)).isoformat(),
        },
    ]


class TestEventResolver:
    def test_next_returns_first_event(self, monkeypatch):
        from modules.workspace_agent import extension as ext_mod
        monkeypatch.setattr(ext_mod.gws, "calendar_agenda", lambda **kw: _events_fixture())
        result = _StubGWSExtension._resolve_event(_StubGWSExtension(), "next")
        assert isinstance(result, dict)
        assert result["id"] == "evt-1"

    def test_fuzzy_title_match(self, monkeypatch):
        from modules.workspace_agent import extension as ext_mod
        monkeypatch.setattr(ext_mod.gws, "calendar_agenda", lambda **kw: _events_fixture())
        result = _StubGWSExtension._resolve_event(_StubGWSExtension(), "dentist")
        if isinstance(result, str):
            # rapidfuzz not installed — substring fallback should still hit.
            pytest.skip("rapidfuzz not installed; substring fallback covered separately")
        assert result["id"] == "evt-1"

    def test_no_match_returns_message(self, monkeypatch):
        from modules.workspace_agent import extension as ext_mod
        monkeypatch.setattr(ext_mod.gws, "calendar_agenda", lambda **kw: _events_fixture())
        result = _StubGWSExtension._resolve_event(_StubGWSExtension(), "nonexistent event xyz")
        assert isinstance(result, str)
        assert "couldn't find" in result.lower()

    def test_empty_calendar_returns_explanation(self, monkeypatch):
        from modules.workspace_agent import extension as ext_mod
        monkeypatch.setattr(ext_mod.gws, "calendar_agenda", lambda **kw: [])
        result = _StubGWSExtension._resolve_event(_StubGWSExtension(), "anything")
        assert isinstance(result, str)
        assert "no upcoming events" in result.lower()

    def test_gws_error_renders_auth_message(self, monkeypatch):
        from modules.workspace_agent import extension as ext_mod

        def boom(**kw):
            raise ext_mod.GWSError("gws API error: Gmail auth failed: Failed to get token")

        monkeypatch.setattr(ext_mod.gws, "calendar_agenda", boom)
        result = _StubGWSExtension._resolve_event(_StubGWSExtension(), "next")
        assert isinstance(result, str)
        assert "gws auth" in result.lower()


# ---------------------------------------------------------------------------
# CapabilityBroker pending_online TTL (5c)
# ---------------------------------------------------------------------------


class TestPendingExpiry:
    """The TTL guard is method-local on `CapabilityBroker` and only reads
    the class-level ``_PENDING_ONLINE_TTL_S`` constant, so we call it
    with the class itself as the implicit-self stand-in (no app, no
    memory_service required)."""

    def test_fresh_pending_not_expired(self):
        fresh = {
            "tool_name": "get_weather",
            "proposed_at": datetime.now().isoformat(),
        }
        assert CapabilityBroker._is_pending_expired(CapabilityBroker, fresh) is False  # type: ignore[arg-type]

    def test_stale_pending_marked_expired(self):
        stale = {
            "tool_name": "get_weather",
            "proposed_at": (datetime.now() - timedelta(minutes=2)).isoformat(),
        }
        assert CapabilityBroker._is_pending_expired(CapabilityBroker, stale) is True  # type: ignore[arg-type]

    def test_missing_timestamp_treated_as_fresh(self):
        legacy = {"tool_name": "get_weather"}
        # Legacy entries from older releases must still resolve on a "yes".
        assert CapabilityBroker._is_pending_expired(CapabilityBroker, legacy) is False  # type: ignore[arg-type]
