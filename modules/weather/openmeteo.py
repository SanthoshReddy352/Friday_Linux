"""Open-Meteo + Nominatim client for the weather plugin (Batch 5 / Issue 13).

No API key. Two small HTTPS calls:
  1. Geocode the user's location via Nominatim (OpenStreetMap).
  2. Fetch the forecast from api.open-meteo.com.

Results are cached on disk for 24h so repeat queries don't hammer the
public services. The cache key is the lowercased, stripped location
string — close enough for typical voice phrasings ("mumbai", "Mumbai",
"  mumbai  " all share an entry).

The module is import-safe even when ``requests`` is not installed: every
public function gracefully returns an ``Err`` outcome the plugin can
surface to the user, and the preflight badge tells them why.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from core.logger import logger


# Open-Meteo's WMO weather codes (truncated to the cases we surface).
# https://open-meteo.com/en/docs#weathervariables
_WEATHER_CODE_TEXT: dict[int, str] = {
    0: "clear sky",
    1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "freezing light drizzle", 57: "freezing dense drizzle",
    61: "light rain", 63: "moderate rain", 65: "heavy rain",
    66: "freezing light rain", 67: "freezing heavy rain",
    71: "light snow", 73: "moderate snow", 75: "heavy snow",
    77: "snow grains",
    80: "rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with light hail", 99: "thunderstorm with heavy hail",
}

_USER_AGENT = "FRIDAY-Linux-Weather/1.0 (https://github.com/anthropics/claude-code)"
_CACHE_TTL_S = 24 * 60 * 60  # 24h
_REQUEST_TIMEOUT_S = 6.0


def _cache_dir() -> str:
    base = os.path.join(os.path.expanduser("~"), ".cache", "friday", "weather")
    os.makedirs(base, exist_ok=True)
    return base


def _cache_key(name: str) -> str:
    cleaned = "_".join((name or "").strip().lower().split())
    return cleaned or "_default"


def _cache_path(name: str) -> str:
    return os.path.join(_cache_dir(), f"{_cache_key(name)}.json")


def _read_cache(name: str) -> dict | None:
    path = _cache_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.debug("[weather] cache read failed for %r: %s", name, exc)
        return None
    saved_at = payload.get("saved_at", 0)
    if (time.time() - saved_at) > _CACHE_TTL_S:
        return None
    return payload


def _write_cache(name: str, payload: dict) -> None:
    path = _cache_path(name)
    payload = dict(payload)
    payload["saved_at"] = time.time()
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    except Exception as exc:
        logger.debug("[weather] cache write failed for %r: %s", name, exc)


@dataclass
class GeocodeResult:
    name: str
    latitude: float
    longitude: float
    country: str = ""

    def display_name(self) -> str:
        if self.country and self.country.lower() not in self.name.lower():
            return f"{self.name}, {self.country}"
        return self.name


@dataclass
class WeatherReport:
    location: GeocodeResult
    temperature_c: float
    apparent_c: float
    humidity_pct: float | None
    wind_kph: float | None
    weather_code: int
    description: str


class WeatherError(Exception):
    pass


def describe_weather_code(code: int) -> str:
    return _WEATHER_CODE_TEXT.get(int(code), f"weather code {code}")


def _http_get_json(url: str, params: dict) -> dict:
    try:
        import requests  # noqa: PLC0415
    except ImportError as exc:
        raise WeatherError(
            "The 'requests' library isn't installed — run preflight for the exact fix."
        ) from exc
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=_REQUEST_TIMEOUT_S,
        )
    except Exception as exc:
        raise WeatherError(f"network error contacting {url}: {exc}") from exc
    if response.status_code != 200:
        raise WeatherError(
            f"HTTP {response.status_code} from {url}: {response.text[:120]}"
        )
    try:
        return response.json()
    except Exception as exc:
        raise WeatherError(f"non-JSON response from {url}: {exc}") from exc


def geocode(location: str) -> GeocodeResult:
    """Resolve a free-form location to a single (lat, lon) pair.

    Uses Nominatim (OpenStreetMap). Cached for 24h. Raises
    ``WeatherError`` on transport, parse, or empty-result failure.
    """
    name = (location or "").strip()
    if not name:
        raise WeatherError("Location is required.")
    cached = _read_cache(name)
    if cached and "geocode" in cached:
        g = cached["geocode"]
        return GeocodeResult(
            name=g["name"],
            latitude=float(g["latitude"]),
            longitude=float(g["longitude"]),
            country=g.get("country", ""),
        )
    data = _http_get_json(
        "https://nominatim.openstreetmap.org/search",
        {"q": name, "format": "json", "limit": 1, "addressdetails": 1},
    )
    if not isinstance(data, list) or not data:
        raise WeatherError(f"Couldn't find a place matching '{name}'.")
    first = data[0]
    address = first.get("address", {}) if isinstance(first, dict) else {}
    country = address.get("country", "") if isinstance(address, dict) else ""
    display = first.get("display_name", name).split(",")[0].strip()
    result = GeocodeResult(
        name=display,
        latitude=float(first["lat"]),
        longitude=float(first["lon"]),
        country=country,
    )
    _write_cache(name, {"geocode": result.__dict__})
    return result


def current_weather(location: str) -> WeatherReport:
    """Return the *current* conditions for ``location``.

    Caches the rendered ``WeatherReport`` for 24h so repeat queries
    ("how's the weather in Mumbai" within the cache window) reply
    instantly without burning network round-trips.
    """
    geo = geocode(location)
    cache_key = f"{location}|current"
    cached = _read_cache(cache_key)
    if cached and "current" in cached:
        c = cached["current"]
        return WeatherReport(
            location=geo,
            temperature_c=float(c["temperature_c"]),
            apparent_c=float(c["apparent_c"]),
            humidity_pct=c.get("humidity_pct"),
            wind_kph=c.get("wind_kph"),
            weather_code=int(c["weather_code"]),
            description=str(c.get("description") or describe_weather_code(c.get("weather_code", 0))),
        )
    data = _http_get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": geo.latitude,
            "longitude": geo.longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
            "wind_speed_unit": "kmh",
        },
    )
    current = data.get("current", {}) if isinstance(data, dict) else {}
    if not current:
        raise WeatherError("Open-Meteo did not return a current-conditions block.")
    code = int(current.get("weather_code", 0))
    report = WeatherReport(
        location=geo,
        temperature_c=float(current.get("temperature_2m", 0.0)),
        apparent_c=float(current.get("apparent_temperature", current.get("temperature_2m", 0.0))),
        humidity_pct=current.get("relative_humidity_2m"),
        wind_kph=current.get("wind_speed_10m"),
        weather_code=code,
        description=describe_weather_code(code),
    )
    _write_cache(cache_key, {
        "current": {
            "temperature_c": report.temperature_c,
            "apparent_c": report.apparent_c,
            "humidity_pct": report.humidity_pct,
            "wind_kph": report.wind_kph,
            "weather_code": report.weather_code,
            "description": report.description,
        }
    })
    return report
