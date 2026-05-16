"""Weather plugin — fast, local-friendly forecasts (Batch 5 / Issue 13).

Routing entry points:

* deterministic regex on phrases like "weather in Mumbai", "how's the
  weather in Delhi", "what's the forecast for Bangalore tomorrow"
* tool descriptor with ``connectivity="online"`` and explicit
  context_terms so the embedding router can also surface it

The plugin marks the capability as ``permission_mode="always_ok"`` — the
existing implicit-online detection in ``consent_service`` recognizes
weather queries as inherently online (already covered by
``CURRENT_INFO_PATTERNS``), so we never want a "Go online?" prompt to
appear before delivering a forecast.
"""

from __future__ import annotations

import re

from core.logger import logger
from core.plugin_manager import FridayPlugin

from . import openmeteo


_LOCATION_RE = re.compile(
    r"\b(?:weather|forecast|temperature|conditions)\b"
    r"(?:[^a-z0-9]+(?:in|for|at|near|around))?\s+([A-Za-z][A-Za-z\s\-']{1,60})",
    re.IGNORECASE,
)


class WeatherPlugin(FridayPlugin):
    def __init__(self, app):
        super().__init__(app)
        self.name = "Weather"
        self.on_load()

    def on_load(self):
        self.app.router.register_tool(
            {
                "name": "get_weather",
                "description": (
                    "Tell the user the current weather for a city, town, or address. "
                    "Use whenever the user asks about temperature, conditions, or the "
                    "forecast. Picks up the location from the user's words."
                ),
                "parameters": {
                    "location": "string – city, town, or place name",
                    "when": "string – 'now' (default), 'today', 'tomorrow', or 'week'",
                },
                "aliases": [
                    "weather",
                    "weather forecast",
                    "how's the weather",
                    "what's the weather",
                    "current weather",
                    "what's the temperature",
                ],
                "patterns": [
                    r"\b(?:what(?:'s| is)|how(?:'s| is)|tell\s+me)\s+(?:the\s+)?(?:weather|temperature|forecast|conditions)\b",
                    r"\b(?:weather|forecast|temperature|conditions)\s+(?:in|for|at|near|around)\s+[A-Za-z]",
                ],
                "context_terms": [
                    "weather", "forecast", "temperature", "humidity", "wind",
                    "rain", "rainy", "snow", "snowy", "sunny", "cloudy",
                ],
            },
            self.handle_get_weather,
            capability_meta={
                "connectivity": "online",
                "latency_class": "fast",
                # Weather is universally implicit-online, so we don't want
                # a "Go online?" prompt before answering.
                "permission_mode": "always_ok",
                "side_effect_level": "read",
            },
        )
        logger.info("WeatherPlugin loaded.")

    # ------------------------------------------------------------------
    # Tool handler
    # ------------------------------------------------------------------

    def handle_get_weather(self, text, args):
        args = dict(args or {})
        location = (args.get("location") or "").strip() or self._extract_location(text or "")
        if not location:
            return "Which city or area should I check the weather for?"
        try:
            report = openmeteo.current_weather(location)
        except openmeteo.WeatherError as exc:
            logger.warning("[weather] lookup failed for %r: %s", location, exc)
            return f"I couldn't check the weather for {location}: {exc}"
        return self._format_report(report)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_location(self, text: str) -> str:
        match = _LOCATION_RE.search(text)
        if not match:
            return ""
        raw = match.group(1).strip(" ?.!,")
        # Strip trailing temporal qualifiers ("Mumbai tomorrow", "Delhi today")
        # so the geocoder doesn't get confused.
        raw = re.sub(r"\s+\b(?:now|today|tomorrow|tonight|this\s+\w+|next\s+\w+)\b.*$", "", raw, flags=re.IGNORECASE)
        return raw.strip()

    def _format_report(self, report: "openmeteo.WeatherReport") -> str:
        parts = [
            f"It's {report.temperature_c:.0f}°C in {report.location.display_name()}",
            f"with {report.description}",
        ]
        if report.apparent_c and abs(report.apparent_c - report.temperature_c) >= 2:
            parts.append(f"(feels like {report.apparent_c:.0f}°C)")
        if report.humidity_pct is not None:
            parts.append(f"humidity {int(report.humidity_pct)}%")
        if report.wind_kph is not None:
            parts.append(f"wind {report.wind_kph:.0f} km/h")
        return ", ".join(parts) + "."
