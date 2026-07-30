from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AppSetting, Calendar

DEFAULT_SETTINGS: dict[str, object] = {
    "first_day_of_week": 0,  # 0=Sunday, 1=Monday
    "time_format_24h": False,
    "home_timezone": "America/New_York",
    "default_view": "week",
    "kiosk_default_route": "/calendar/week",
    "display_scale": "normal",  # normal | large | wall
    "day_start_hour": 7,
    "day_end_hour": 22,
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
