from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, Calendar
from .services.google_config import seed_from_env

DEFAULT_SETTINGS: dict[str, object] = {
    "first_day_of_week": 0,  # 0=Sunday, 1=Monday
    "time_format_24h": False,
    "home_timezone": "America/New_York",
    "default_view": "week",
    "kiosk_default_route": "/calendar/week",
    "display_scale": "normal",  # normal | large | wall
    "day_start_hour": 7,
    "day_end_hour": 22,
    # Screensaver / kiosk behaviour. A wall display is on 24/7, so idle handling
    # and a nightly blackout are part of normal operation, not a nice-to-have.
    "screensaver_enabled": True,
    "screensaver_delay_minutes": 5,
    "screensaver_mode": "auto",  # auto | photos | clock | off
    "screensaver_shuffle": True,
    "screensaver_seconds_per_photo": 20,
    "sleep_enabled": False,
    "sleep_start_hour": 23,
    "sleep_end_hour": 7,
    "burn_in_shift": True,
    # Weather. Empty coordinates mean the widget prompts for a location instead of
    # guessing, which would be worse than asking.
    "weather_enabled": True,
    "weather_lat": None,
    "weather_lon": None,
    "weather_place": "",
    "weather_provider": "auto",  # auto | nws | open-meteo
    "weather_units": "imperial",  # imperial | metric
    # Home Assistant. Optional; when set, a calendar change nudges HA to refresh
    # immediately instead of waiting out its 24-hour poll.
    "ha_base_url": "",
    "ha_token": "",
    "ha_entity_id": "calendar.family_calendar",
    # Google Calendar. Configured in Settings -> Google rather than .env, so a
    # self-hoster never has to edit a file and restart a container to finish
    # setup. Seeded from .env once on first run for installs that predate this.
    "google_client_id": "",
    "google_client_secret": "",
    "public_base_url": "",
}


def ensure_defaults(db: Session) -> None:
    """Idempotent first-run setup: a local calendar so the app is usable with zero
    Google configuration, plus default settings rows."""
    existing = {row[0] for row in db.execute(select(AppSetting.key))}
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing:
            db.add(AppSetting(key=key, value={"value": value}))

    has_local = db.execute(
        select(Calendar.id).where(Calendar.linked_account_id.is_(None))
    ).first()
    if not has_local:
        db.add(Calendar(name="Family", linked_account_id=None, sync_enabled=False))

    db.commit()

    # Carry any .env credentials into the database so Settings shows the truth
    # from here on. Only fills blanks, so it never clobbers an edit.
    seed_from_env(db)
