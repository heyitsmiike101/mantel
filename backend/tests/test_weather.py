"""Weather tests.

The behaviour that matters most here is not parsing -- it's that a wall display
never breaks. Every failure mode gets its own test: upstream down with a warm
cache, upstream down with nothing cached, and garbage responses.
"""

import json

import pytest

from app.services import httpcache
from app.services import weather as weather_service

# ------------------------------- fixtures ------------------------------------

NWS_POINTS = json.dumps(
    {
        "properties": {
            "forecast": "https://api.weather.gov/gridpoints/TBW/70,60/forecast",
            "forecastHourly": "https://api.weather.gov/gridpoints/TBW/70,60/forecast/hourly",
            "forecastZone": "https://api.weather.gov/zones/forecast/FLZ151",
        }
    }
)

NWS_DAILY = json.dumps(
    {
        "properties": {
            "periods": [
                {
                    "startTime": "2026-08-03T06:00:00-04:00",
                    "isDaytime": True,
                    "temperature": 91,
                    "temperatureUnit": "F",
                    "probabilityOfPrecipitation": {"value": 60},
                    "shortForecast": "Scattered thunderstorms",
                },
                {
                    "startTime": "2026-08-03T18:00:00-04:00",
                    "isDaytime": False,
                    "temperature": 76,
                    "temperatureUnit": "F",
                    "probabilityOfPrecipitation": {"value": 30},
                    "shortForecast": "Mostly cloudy",
                },
                {
                    "startTime": "2026-08-04T06:00:00-04:00",
                    "isDaytime": True,
                    "temperature": 93,
                    "temperatureUnit": "F",
                    "probabilityOfPrecipitation": {"value": 20},
                    "shortForecast": "Sunny",
                },
            ]
        }
    }
)

NWS_HOURLY = json.dumps(
    {
        "properties": {
            "periods": [
                {
                    "startTime": "2026-08-03T14:00:00-04:00",
                    "temperature": 89,
                    "temperatureUnit": "F",
                    "relativeHumidity": {"value": 62.4},
                    "probabilityOfPrecipitation": {"value": 45},
                    "windSpeed": "10 mph",
                    "windDirection": "SW",
                    "shortForecast": "Chance showers",
                    "isDaytime": True,
                }
            ]
        }
    }
)

NWS_ALERTS = json.dumps(
    {
        "features": [
            {
                "properties": {
                    "event": "Heat Advisory",
                    "severity": "Moderate",
                    "headline": "Heat Advisory until 8 PM EDT",
                }
            }
        ]
    }
)

OPEN_METEO = json.dumps(
    {
        "current": {
            "temperature_2m": 21.6,
            "relative_humidity_2m": 58,
            "apparent_temperature": 22.1,
            "precipitation_probability": 15,
            "weather_code": 2,
            "wind_speed_10m": 12.4,
            "is_day": 1,
        },
        "hourly": {
            "time": ["2026-08-03T14:00", "2026-08-03T15:00"],
            "temperature_2m": [21.6, 22.4],
            "precipitation_probability": [15, 20],
            "weather_code": [2, 61],
        },
        "daily": {
            "time": ["2026-08-03", "2026-08-04"],
            "weather_code": [2, 61],
            "temperature_2m_max": [24.0, 19.5],
            "temperature_2m_min": [14.2, 12.8],
            "precipitation_probability_max": [20, 80],
        },
    }
)


@pytest.fixture
def fake_http(monkeypatch):
    """Routes every outbound URL to a canned body and records the calls."""
    state = {"responses": {}, "calls": [], "fail": False}

    def fetch(session, key, url, ttl_s, params=None):
        state["calls"].append({"key": key, "url": url, "params": params})
        if state["fail"]:
            cached, _ = httpcache.get_cached(session, key, ttl_s)
            return (cached, True) if cached else (None, True)
        for fragment, body in state["responses"].items():
            if fragment in url:
                httpcache.put_cached(session, key, body)
                return body, False
        return None, True

    monkeypatch.setattr(weather_service, "fetch", fetch)
    return state


@pytest.fixture
def nws(fake_http):
    fake_http["responses"] = {
        "/points/": NWS_POINTS,
        "/forecast/hourly": NWS_HOURLY,
        "/forecast": NWS_DAILY,
        "/alerts/active": NWS_ALERTS,
    }
    return fake_http


@pytest.fixture
def open_meteo(fake_http):
    fake_http["responses"] = {"open-meteo.com/v1/forecast": OPEN_METEO}
    return fake_http


def set_location(client, lat=28.19, lon=-82.6, **extra):
    return client.patch(
        "/api/settings",
        json={"weather_lat": lat, "weather_lon": lon, "weather_place": "Odessa, FL", **extra},
    )


# ---------------------------- provider choice --------------------------------


@pytest.mark.parametrize(
    "lat,lon,expected",
    [
        (28.19, -82.6, "nws"),  # Florida
        (61.2, -149.9, "nws"),  # Alaska
        (51.5, -0.12, "open-meteo"),  # London
        (-33.9, 151.2, "open-meteo"),  # Sydney
    ],
)
def test_auto_picks_nws_only_inside_the_us(lat, lon, expected):
    assert weather_service.choose_provider("auto", lat, lon) == expected


def test_explicit_provider_overrides_location():
    assert weather_service.choose_provider("open-meteo", 28.19, -82.6) == "open-meteo"
    assert weather_service.choose_provider("nws", 51.5, -0.12) == "nws"


def test_nws_point_is_rounded():
    """NWS 301-redirects finer precision, and caching that redirect as the forecast
    is a silent failure that reads as 'no forecast available'."""
    assert weather_service._nws_point(28.1923456, -82.6123456) == "28.1923,-82.6123"


# --------------------------------- NWS ---------------------------------------


def test_nws_forecast(client, db, nws):
    set_location(client)
    body = client.get("/api/weather").json()

    assert body["available"] is True
    assert body["provider"] == "nws"
    assert body["stale"] is False
    assert body["place"] == "Odessa, FL"

    assert body["current"]["temp"] == 89
    assert body["current"]["humidity"] == 62
    assert body["current"]["short"] == "Chance showers"

    # Day/night periods must collapse into one row per calendar day.
    assert [d["date"] for d in body["days"]] == ["2026-08-03", "2026-08-04"]
    assert body["days"][0]["high"] == 91
    assert body["days"][0]["low"] == 76
    assert body["days"][0]["pop"] == 60, "the day takes the higher of its two periods"
    assert body["days"][1]["high"] == 93


def test_nws_alerts_surface(client, db, nws):
    set_location(client)
    alerts = client.get("/api/weather").json()["alerts"]
    assert alerts[0]["event"] == "Heat Advisory"


def test_nws_converts_to_metric_on_request(client, db, nws):
    set_location(client, weather_units="metric")
    body = client.get("/api/weather").json()
    assert body["current"]["temp"] == 32, "89F is 32C"
    assert body["days"][0]["high"] == 33


# ------------------------------ Open-Meteo -----------------------------------


def test_open_meteo_forecast(client, db, open_meteo):
    set_location(client, lat=51.5, lon=-0.12, weather_units="metric")
    body = client.get("/api/weather").json()

    assert body["available"] is True
    assert body["provider"] == "open-meteo"
    assert body["current"]["temp"] == 22
    assert body["current"]["short"] == "Partly cloudy"
    assert [d["date"] for d in body["days"]] == ["2026-08-03", "2026-08-04"]
    assert body["days"][1]["short"] == "Light rain"
    assert body["days"][1]["pop"] == 80
    assert len(body["hourly"]) == 2


def test_open_meteo_asks_for_fahrenheit_when_imperial(client, db, open_meteo):
    set_location(client, lat=51.5, lon=-0.12, weather_units="imperial")
    client.get("/api/weather")
    call = next(c for c in open_meteo["calls"] if "open-meteo" in c["url"])
    assert call["params"]["temperature_unit"] == "fahrenheit"


# ------------------------------ degradation ----------------------------------


def test_serves_stale_cache_when_upstream_fails(client, db, nws):
    """The behaviour that matters: yesterday's forecast beats a blank panel."""
    set_location(client)
    first = client.get("/api/weather").json()
    assert first["stale"] is False

    nws["fail"] = True
    second = client.get("/api/weather").json()

    assert second["available"] is True, "must still render"
    assert second["stale"] is True, "and must admit the data is old"
    assert second["current"]["temp"] == first["current"]["temp"]


def test_total_failure_with_no_cache_is_reported_not_raised(client, db, fake_http):
    set_location(client)
    fake_http["fail"] = True
    r = client.get("/api/weather")
    assert r.status_code == 200, "a weather outage must never be an API error"
    assert r.json()["available"] is False
    assert r.json()["reason"]


def test_garbage_upstream_response_degrades(client, db, fake_http):
    fake_http["responses"] = {"/points/": "<html>503 Service Unavailable</html>"}
    set_location(client)
    body = client.get("/api/weather").json()
    assert body["available"] is False


def test_us_location_falls_back_to_open_meteo_when_nws_has_no_gridpoint(client, db, fake_http):
    """Offshore and territorial coordinates are inside the US box but have no NWS
    gridpoint; showing nothing there would be worse than a global provider."""
    fake_http["responses"] = {"open-meteo.com/v1/forecast": OPEN_METEO}
    set_location(client)  # Florida, but /points returns nothing
    body = client.get("/api/weather").json()
    assert body["available"] is True
    assert body["provider"] == "open-meteo"


def test_no_location_configured(client, db):
    body = client.get("/api/weather").json()
    assert body["available"] is False
    assert "Settings" in body["reason"]


def test_weather_can_be_switched_off(client, db, nws):
    set_location(client, weather_enabled=False)
    body = client.get("/api/weather").json()
    assert body["available"] is False


# -------------------------------- caching ------------------------------------


def test_second_call_uses_the_cache(client, db, monkeypatch):
    """A warm cache must not hit the network -- NWS asks callers not to hammer it."""
    calls = []
    real_get = httpcache.get_cached

    import httpx

    def explode(*args, **kwargs):
        calls.append(1)
        raise AssertionError("network was used despite a warm cache")

    httpcache.put_cached(db, "probe", "cached-body")
    body, expired = real_get(db, "probe", 3600)
    assert body == "cached-body" and expired is False

    monkeypatch.setattr(httpx, "Client", explode)
    body, stale = httpcache.fetch(db, "probe", "https://example.invalid", 3600)
    assert body == "cached-body" and stale is False
    assert not calls


def test_expired_cache_is_refetched_and_survives_failure(client, db, monkeypatch):
    httpcache.put_cached(db, "probe2", "old-body")
    body, stale = httpcache.fetch(db, "probe2", "https://example.invalid", ttl_s=0)
    assert body == "old-body", "a failed refresh falls back to whatever we had"
    assert stale is True


# ------------------------------- geocoding -----------------------------------


def test_place_search(client, db, monkeypatch):
    payload = json.dumps(
        {
            "results": [
                {
                    "name": "Odessa",
                    "admin1": "Florida",
                    "country": "United States",
                    "latitude": 28.19,
                    "longitude": -82.6,
                }
            ]
        }
    )
    monkeypatch.setattr(weather_service, "fetch", lambda *a, **k: (payload, False))
    results = client.get("/api/weather/search", params={"q": "Odessa"}).json()
    assert results[0]["label"] == "Odessa, Florida, United States"
    assert results[0]["latitude"] == 28.19


def test_place_search_handles_no_matches(client, db, monkeypatch):
    monkeypatch.setattr(
        weather_service, "fetch", lambda *a, **k: ('{"generationtime_ms":0}', False)
    )
    assert client.get("/api/weather/search", params={"q": "zzzzz"}).json() == []


# ------------------------- today's high carry-forward ------------------------


def _daily_without_todays_daytime() -> str:
    """What NWS actually returns in the evening: today's daytime period is gone."""
    return json.dumps(
        {
            "properties": {
                "periods": [
                    {
                        "startTime": "2026-08-03T18:00:00-04:00",
                        "isDaytime": False,
                        "temperature": 76,
                        "temperatureUnit": "F",
                        "probabilityOfPrecipitation": {"value": 30},
                        "shortForecast": "Mostly cloudy",
                    },
                    {
                        "startTime": "2026-08-04T06:00:00-04:00",
                        "isDaytime": True,
                        "temperature": 93,
                        "temperatureUnit": "F",
                        "probabilityOfPrecipitation": {"value": 20},
                        "shortForecast": "Sunny",
                    },
                ]
            }
        }
    )


def test_todays_high_survives_nws_dropping_the_daytime_period(client, db, nws):
    """Otherwise the tile flips from a real temperature to a dash a few hours
    after the high actually happened, which reads as broken."""
    set_location(client)
    first = client.get("/api/weather").json()
    assert first["days"][0]["high"] == 91

    nws["responses"]["/forecast"] = _daily_without_todays_daytime()
    later = client.get("/api/weather").json()

    assert later["days"][0]["date"] == "2026-08-03"
    assert later["days"][0]["high"] == 91, "the known high must persist through the evening"
    assert later["days"][0]["low"] == 76


def test_carried_high_does_not_leak_into_another_day(client, db, nws):
    set_location(client)
    client.get("/api/weather")

    # A feed that starts on a different date must not inherit yesterday's number.
    nws["responses"]["/forecast"] = json.dumps(
        {
            "properties": {
                "periods": [
                    {
                        "startTime": "2026-08-05T18:00:00-04:00",
                        "isDaytime": False,
                        "temperature": 70,
                        "temperatureUnit": "F",
                        "probabilityOfPrecipitation": {"value": 10},
                        "shortForecast": "Clear",
                    }
                ]
            }
        }
    )
    body = client.get("/api/weather").json()
    assert body["days"][0]["date"] == "2026-08-05"
    assert body["days"][0]["high"] is None
