"""Weather for the wall display.

Two providers behind one shape:

* **NWS** (api.weather.gov) -- free, no key, and the richest data available:
  hourly forecasts, watches and warnings. **United States only.**
* **Open-Meteo** -- free, no key, worldwide. The default everywhere else, because
  shipping a US-only calendar publicly is not acceptable.

`auto` picks NWS inside the US and Open-Meteo elsewhere.

Both degrade the same way: a network failure serves the last cached response with
`stale: true`, and a failure with nothing cached returns `available: false`. The
panel never shows an error and never disappears.
"""

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .httpcache import fetch, get_cached, put_cached

log = logging.getLogger(__name__)

POINTS_TTL = 30 * 86400  # a coordinate's NWS gridpoint never changes
FORECAST_TTL = 1800
ALERTS_TTL = 300
GEOCODE_TTL = 30 * 86400

# Rough continental US + Alaska + Hawaii box. Only used to choose a default
# provider, so being generous at the edges costs nothing.
US_BOUNDS = (18.0, 72.0, -180.0, -66.0)  # lat_min, lat_max, lon_min, lon_max


def _in_us(lat: float, lon: float) -> bool:
    lat_min, lat_max, lon_min, lon_max = US_BOUNDS
    return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max


def choose_provider(preference: str, lat: float, lon: float) -> str:
    if preference in ("nws", "open-meteo"):
        return preference
    return "nws" if _in_us(lat, lon) else "open-meteo"


def unavailable(reason: str) -> dict:
    return {"available": False, "stale": True, "reason": reason}


# ------------------------------- geocoding -----------------------------------


def geocode(session: Session, query: str) -> list[dict]:
    """Turn a town or postcode into coordinates via Open-Meteo's free geocoder, so
    nobody has to look up their own latitude."""
    body, _ = fetch(
        session,
        f"geocode:{query.lower().strip()}",
        "https://geocoding-api.open-meteo.com/v1/search",
        GEOCODE_TTL,
        params={"name": query, "count": 5, "format": "json"},
    )
    if not body:
        return []
    try:
        results = json.loads(body).get("results") or []
    except json.JSONDecodeError:
        return []

    return [
        {
            "name": r.get("name"),
            "admin1": r.get("admin1"),
            "country": r.get("country"),
            "latitude": r.get("latitude"),
            "longitude": r.get("longitude"),
            "label": ", ".join(
                p for p in (r.get("name"), r.get("admin1"), r.get("country")) if p
            ),
        }
        for r in results
        if r.get("latitude") is not None
    ]


# --------------------------------- NWS ---------------------------------------


def _nws_point(lat: float, lon: float) -> str:
    """NWS caps /points precision and 301-redirects anything finer. Following that
    redirect and caching its problem document as the forecast is a silent failure
    that looks like "no forecast available", so round before asking."""
    return f"{round(lat, 4)},{round(lon, 4)}"


def _nws(session: Session, lat: float, lon: float, units: str) -> dict:
    point = _nws_point(lat, lon)
    raw_points, points_stale = fetch(
        session, f"nws_points:{point}", f"https://api.weather.gov/points/{point}", POINTS_TTL
    )
    if not raw_points:
        return unavailable("Could not reach the National Weather Service.")

    try:
        props = json.loads(raw_points)["properties"]
        forecast_url = props["forecast"]
        hourly_url = props["forecastHourly"]
        zone = (props.get("forecastZone") or "").rsplit("/", 1)[-1]
    except (json.JSONDecodeError, KeyError):
        return unavailable("The weather service returned something unexpected.")

    raw_daily, daily_stale = fetch(session, f"nws_daily:{point}", forecast_url, FORECAST_TTL)
    raw_hourly, hourly_stale = fetch(session, f"nws_hourly:{point}", hourly_url, FORECAST_TTL)

    days = _remember_todays_high(session, _nws_days(raw_daily, units), units)
    current, hours = _nws_current(raw_hourly, units)
    alerts = _nws_alerts(session, zone) if zone else []

    return {
        "available": current is not None or bool(days),
        "stale": points_stale or daily_stale or hourly_stale,
        "provider": "nws",
        "units": units,
        "current": current,
        "days": days,
        "hourly": hours,
        "alerts": alerts,
    }


def _nws_days(raw: str | None, units: str) -> list[dict]:
    """NWS returns 14 alternating day/night periods; the strip wants one row per
    calendar day, with the high from the daytime half and the low from the night."""
    if not raw:
        return []
    try:
        periods = json.loads(raw)["properties"]["periods"]
    except (json.JSONDecodeError, KeyError):
        return []

    days: dict[str, dict] = {}
    order: list[str] = []
    for p in periods:
        try:
            date = datetime.fromisoformat(p["startTime"]).date().isoformat()
        except (KeyError, ValueError):
            continue
        if date not in days:
            days[date] = {"date": date, "high": None, "low": None, "pop": 0, "short": None}
            order.append(date)
        entry = days[date]
        entry["pop"] = max(
            entry["pop"], (p.get("probabilityOfPrecipitation") or {}).get("value") or 0
        )
        temp = _convert_temp(p.get("temperature"), p.get("temperatureUnit", "F"), units)
        if p.get("isDaytime"):
            entry["high"] = temp
            entry["short"] = p.get("shortForecast")
        else:
            entry["low"] = temp
            entry["short"] = entry["short"] or p.get("shortForecast")

    return [days[d] for d in order[:7]]


def _nws_current(raw: str | None, units: str) -> tuple[dict | None, list[dict]]:
    if not raw:
        return None, []
    try:
        periods = json.loads(raw)["properties"]["periods"]
        now = periods[0]
    except (json.JSONDecodeError, KeyError, IndexError):
        return None, []

    temp = _convert_temp(now.get("temperature"), now.get("temperatureUnit", "F"), units)
    humidity = (now.get("relativeHumidity") or {}).get("value")
    current = {
        "temp": temp,
        "feels_like": temp,
        "humidity": round(humidity) if humidity is not None else None,
        "short": now.get("shortForecast"),
        "pop": (now.get("probabilityOfPrecipitation") or {}).get("value") or 0,
        "wind": now.get("windSpeed"),
        "wind_direction": now.get("windDirection"),
        "is_daytime": now.get("isDaytime", True),
    }

    hours = [
        {
            "time": p.get("startTime"),
            "temp": _convert_temp(p.get("temperature"), p.get("temperatureUnit", "F"), units),
            "pop": (p.get("probabilityOfPrecipitation") or {}).get("value") or 0,
            "short": p.get("shortForecast"),
        }
        for p in periods[:24]
    ]
    return current, hours


def _nws_alerts(session: Session, zone: str) -> list[dict]:
    body, _ = fetch(
        session,
        f"nws_alerts:{zone}",
        "https://api.weather.gov/alerts/active",
        ALERTS_TTL,
        params={"zone": zone},
    )
    if not body:
        return []
    try:
        features = json.loads(body).get("features") or []
    except json.JSONDecodeError:
        return []

    return [
        {
            "event": f["properties"].get("event"),
            "severity": f["properties"].get("severity"),
            "headline": f["properties"].get("headline"),
        }
        for f in features
        if f.get("properties")
    ][:5]


def _remember_todays_high(session: Session, days: list[dict], units: str) -> list[dict]:
    """Keep showing today's high after NWS stops reporting it.

    NWS drops today's daytime period from the feed once that period is over, so a
    few hours after the actual high the tile flips from "91" to a dash -- which
    reads as broken data rather than as what it is: a temperature that is known,
    just no longer in the live feed. Remembering the last real value, keyed to
    today's date, keeps it on screen for the rest of the day and cannot leak into
    tomorrow because tomorrow's key starts empty.
    """
    if not days:
        return days

    today = days[0]
    key = f"nws_high:{today['date']}:{units}"

    if today.get("high") is not None:
        put_cached(session, key, str(today["high"]))
        return days

    cached, _ = get_cached(session, key, ttl_s=86400)
    if cached is not None:
        try:
            today["high"] = int(cached)
        except ValueError:
            pass
    return days


# ------------------------------ Open-Meteo -----------------------------------

# Condition codes, collapsed to the handful of buckets a family display needs.
WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle", 61: "Light rain", 63: "Rain",
    65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain", 71: "Light snow",
    73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Showers", 81: "Showers",
    82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


def _open_meteo(session: Session, lat: float, lon: float, units: str) -> dict:
    imperial = units == "imperial"
    params: dict[str, Any] = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
        "precipitation_probability,weather_code,wind_speed_10m,is_day",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max",
        "forecast_days": 7,
        "timezone": "auto",
    }
    if imperial:
        params |= {"temperature_unit": "fahrenheit", "wind_speed_unit": "mph"}

    body, stale = fetch(
        session,
        f"openmeteo:{round(lat, 4)},{round(lon, 4)}:{units}",
        "https://api.open-meteo.com/v1/forecast",
        FORECAST_TTL,
        params=params,
    )
    if not body:
        return unavailable("Could not reach the weather service.")

    try:
        data = json.loads(body)
        cur = data["current"]
        daily = data["daily"]
    except (json.JSONDecodeError, KeyError):
        return unavailable("The weather service returned something unexpected.")

    current = {
        "temp": _round(cur.get("temperature_2m")),
        "feels_like": _round(cur.get("apparent_temperature")),
        "humidity": _round(cur.get("relative_humidity_2m")),
        "short": WMO.get(cur.get("weather_code"), "—"),
        "pop": cur.get("precipitation_probability") or 0,
        "wind": f"{_round(cur.get('wind_speed_10m'))} {'mph' if imperial else 'km/h'}",
        "wind_direction": None,
        "is_daytime": bool(cur.get("is_day", 1)),
    }

    days = [
        {
            "date": date,
            "high": _round(daily["temperature_2m_max"][i]),
            "low": _round(daily["temperature_2m_min"][i]),
            "pop": daily.get("precipitation_probability_max", [0] * 7)[i] or 0,
            "short": WMO.get(daily["weather_code"][i], "—"),
        }
        for i, date in enumerate(daily.get("time", []))
    ]

    hourly_block = data.get("hourly") or {}
    hours = [
        {
            "time": t,
            "temp": _round(hourly_block["temperature_2m"][i]),
            "pop": (hourly_block.get("precipitation_probability") or [0] * 24)[i] or 0,
            "short": WMO.get((hourly_block.get("weather_code") or [])[i], "—"),
        }
        for i, t in enumerate(hourly_block.get("time", [])[:24])
    ]

    return {
        "available": True,
        "stale": stale,
        "provider": "open-meteo",
        "units": units,
        "current": current,
        "days": days,
        "hourly": hours,
        "alerts": [],
    }


# ------------------------------- entry point ---------------------------------


def forecast(session: Session, lat: float, lon: float, provider: str, units: str) -> dict:
    """Never raises. See the module docstring for the degradation contract."""
    chosen = choose_provider(provider, lat, lon)
    try:
        if chosen == "nws":
            result = _nws(session, lat, lon, units)
            # A US coordinate NWS has no gridpoint for (offshore, territories) should
            # fall back rather than show nothing.
            if not result.get("available") and provider == "auto":
                return _open_meteo(session, lat, lon, units)
            return result
        return _open_meteo(session, lat, lon, units)
    except Exception:  # noqa: BLE001
        log.exception("weather lookup failed")
        return unavailable("The weather service is unavailable.")


def _round(value) -> int | None:
    return None if value is None else round(value)


def _convert_temp(value, from_unit: str, units: str) -> int | None:
    if value is None:
        return None
    fahrenheit = (from_unit or "F").upper().startswith("F")
    if units == "imperial":
        return round(value if fahrenheit else value * 9 / 5 + 32)
    return round((value - 32) * 5 / 9 if fahrenheit else value)
