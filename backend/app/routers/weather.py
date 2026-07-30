from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bootstrap import DEFAULT_SETTINGS
from ..db import get_db
from ..models import AppSetting
from ..services import weather as weather_service

router = APIRouter(prefix="/weather", tags=["weather"])


def _settings(db: Session) -> dict:
    stored = {row.key: row.value.get("value") for row in db.scalars(select(AppSetting))}
    return {**DEFAULT_SETTINGS, **stored}


@router.get(
    "",
    summary="Current conditions and a 7-day forecast",
    description=(
        "Uses the location set in Settings → Weather. Returns "
        "`{available: false, reason}` when no location is configured or the "
        "upstream service can't be reached, and sets `stale: true` when the data "
        "came from cache after a failed refresh — it never returns an error status, "
        "so a wall display can render it unconditionally."
    ),
)
def get_weather(db: Session = Depends(get_db)) -> dict:
    settings = _settings(db)
    if not settings.get("weather_enabled", True):
        return weather_service.unavailable("Weather is turned off in settings.")

    lat, lon = settings.get("weather_lat"), settings.get("weather_lon")
    if lat is None or lon is None:
        return weather_service.unavailable("Set a location in Settings → Weather.")

    result = weather_service.forecast(
        db,
        float(lat),
        float(lon),
        str(settings.get("weather_provider", "auto")),
        str(settings.get("weather_units", "imperial")),
    )
    result["place"] = settings.get("weather_place") or None
    return result


@router.get(
    "/search",
    summary="Find coordinates for a town or postcode",
    description=(
        "Wraps Open-Meteo's free geocoder so nobody has to look up their own "
        "latitude and longitude. Returns up to five matches."
    ),
)
def search_places(
    q: str = Query(min_length=2, description="Town, city or postcode.", examples=["Odessa, FL"]),
    db: Session = Depends(get_db),
) -> list[dict]:
    return weather_service.geocode(db, q)
