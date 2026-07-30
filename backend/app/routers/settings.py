from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bootstrap import DEFAULT_SETTINGS
from ..config import get_settings
from ..db import get_db
from ..models import AppSetting
from ..services import homeassistant

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get(
    "",
    summary="Get app settings",
    description=(
        "Display and behavior preferences shared by every screen in the house. Also reports "
        "read-only server facts under `server`, such as whether Google sync is configured."
    ),
)
def get_app_settings(db: Session = Depends(get_db)) -> dict:
    stored = {row.key: row.value.get("value") for row in db.scalars(select(AppSetting))}
    s = get_settings()
    return {
        **DEFAULT_SETTINGS,
        **stored,
        "server": {
            "version": s.version,
            "google_configured": s.google_configured,
            "sync_enabled": s.sync_enabled,
            "sync_interval_seconds": s.sync_interval_seconds,
        },
    }


@router.patch(
    "",
    summary="Update app settings",
    description=(
        "Send only the keys you want to change, e.g. `{\"display_scale\": \"wall\"}`. Unknown "
        "keys are rejected so a typo cannot silently do nothing."
    ),
)
def update_app_settings(payload: dict, db: Session = Depends(get_db)) -> dict:
    unknown = set(payload) - set(DEFAULT_SETTINGS)
    if unknown:
        raise HTTPException(400, f"Unknown settings: {', '.join(sorted(unknown))}")
    for key, value in payload.items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value={"value": value}))
        else:
            row.value = {"value": value}
    db.commit()
    return get_app_settings(db)


@router.post(
    "/test-home-assistant",
    summary="Check the Home Assistant connection",
    description=(
        "Verifies the saved URL and token reach a Home Assistant instance, so a typo "
        "surfaces immediately rather than as silently missing calendar updates weeks later."
    ),
)
def test_home_assistant(db: Session = Depends(get_db)) -> dict:
    stored = {row.key: row.value.get("value") for row in db.scalars(select(AppSetting))}
    ok, message = homeassistant.test_connection(
        str(stored.get("ha_base_url") or ""), str(stored.get("ha_token") or "")
    )
    return {"ok": ok, "message": message}
