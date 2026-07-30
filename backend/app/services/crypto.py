import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, URLSafeTimedSerializer

from ..config import get_settings


def _fernet() -> Fernet:
    """Accept any SECRET_KEY string: a real Fernet key is used directly, anything else is
    hashed into one so self-hosters are never blocked by key formatting."""
    raw = get_settings().secret_key
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError):
        digest = hashlib.sha256(raw.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        # SECRET_KEY changed since this token was stored; the account must re-link.
        return None


_STATE_SALT = "google-oauth-state"


def sign_state(payload: dict) -> str:
    return URLSafeTimedSerializer(get_settings().secret_key, salt=_STATE_SALT).dumps(payload)


def read_state(token: str, max_age_seconds: int = 900) -> dict | None:
    try:
        return URLSafeTimedSerializer(get_settings().secret_key, salt=_STATE_SALT).loads(
            token, max_age=max_age_seconds
        )
    except BadSignature:
        return None
