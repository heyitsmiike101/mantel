"""Where the Google Calendar credentials live.

They are stored in the database and edited in Settings, not in `.env`. A
self-hoster should be able to finish setup in the browser, and asking someone to
SSH into a box, edit a file and restart a container just to paste a client ID is
the kind of thing that makes a homelab app not get used.

`.env` is still read, once, as a seed: an install that already had
`GOOGLE_CLIENT_ID` set keeps working across the upgrade, and the value is copied
into the database on first start so Settings shows the truth from then on.

The client secret is encrypted at rest with the same key as the OAuth tokens, and
never leaves the API -- `GET /api/settings` reports only whether one is set.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AppSetting
from .crypto import decrypt, encrypt

CLIENT_ID_KEY = "google_client_id"
CLIENT_SECRET_KEY = "google_client_secret"
BASE_URL_KEY = "public_base_url"


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    base_url: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    @property
    def redirect_uri(self) -> str:
        """Must match a redirect URI registered in Google Cloud, exactly."""
        return f"{self.base_url.rstrip('/')}/api/accounts/google/callback"


def _read(db: Session, key: str) -> str:
    row = db.get(AppSetting, key)
    if row is None:
        return ""
    value = row.value.get("value")
    return "" if value is None else str(value)


def load(db: Session) -> GoogleConfig:
    env = get_settings()
    secret = _read(db, CLIENT_SECRET_KEY)
    return GoogleConfig(
        client_id=_read(db, CLIENT_ID_KEY) or env.google_client_id,
        # Stored encrypted; a value that fails to decrypt (SECRET_KEY rotated)
        # falls back to the env seed rather than sending Google a garbage secret.
        client_secret=(decrypt(secret) if secret else "") or env.google_client_secret,
        base_url=_read(db, BASE_URL_KEY) or env.public_base_url,
    )


def save_secret(db: Session, raw: str) -> None:
    stored = encrypt(raw) if raw else ""
    row = db.get(AppSetting, CLIENT_SECRET_KEY)
    if row is None:
        db.add(AppSetting(key=CLIENT_SECRET_KEY, value={"value": stored}))
    else:
        row.value = {"value": stored}
    db.commit()


def seed_from_env(db: Session) -> None:
    """Copy any `.env` credentials into the database on first run.

    Only fills blanks, so it can never overwrite something typed in Settings --
    which matters because `.env` keeps its old value forever and would otherwise
    clobber an edit on every restart.
    """
    env = get_settings()
    present = {row[0] for row in db.execute(select(AppSetting.key))}

    if env.google_client_id and CLIENT_ID_KEY not in present:
        db.add(AppSetting(key=CLIENT_ID_KEY, value={"value": env.google_client_id}))
    if env.google_client_secret and CLIENT_SECRET_KEY not in present:
        db.add(
            AppSetting(
                key=CLIENT_SECRET_KEY, value={"value": encrypt(env.google_client_secret)}
            )
        )
    if env.public_base_url and BASE_URL_KEY not in present:
        db.add(AppSetting(key=BASE_URL_KEY, value={"value": env.public_base_url}))
    db.commit()
