from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..bootstrap import DEFAULT_SETTINGS
from ..config import get_settings
from ..db import get_db
from ..models import AppSetting
from ..services import google_config, homeassistant

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
    cfg = google_config.load(db)

    values = {**DEFAULT_SETTINGS, **stored}
    # Secrets are write-only over the API. Reporting whether one is set is enough
    # for the settings screen to render, and means a stored client secret and a
    # Home Assistant token can never be read back out of a no-auth LAN endpoint.
    values[google_config.CLIENT_SECRET_KEY] = ""
    values["ha_token"] = ""

    return {
        **values,
        "server": {
            "version": s.version,
            "google_configured": cfg.configured,
            "google_client_secret_set": bool(cfg.client_secret),
            "ha_token_set": bool(stored.get("ha_token")),
            "google_redirect_uri": cfg.redirect_uri,
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

    # Encrypted at rest with the same key as the OAuth tokens. An empty string
    # means "leave it alone", so the settings form can post the whole object
    # without a blank field wiping a secret the user never touched.
    if google_config.CLIENT_SECRET_KEY in payload:
        secret = str(payload.pop(google_config.CLIENT_SECRET_KEY) or "")
        if secret:
            google_config.save_secret(db, secret)

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
