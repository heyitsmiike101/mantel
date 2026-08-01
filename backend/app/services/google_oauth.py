from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from ..models import LinkedAccount
from ..timeutil import utcnow_naive
from .crypto import decrypt, encrypt
from .google_config import GoogleConfig, load

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleAuthError(Exception):
    """Raised when Google refuses the stored credentials and the user must re-link."""


def build_auth_url(cfg: GoogleConfig, state: str) -> str:
    params = {
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        # offline + consent guarantees a refresh token even on a repeat authorization,
        # which is what lets the app keep syncing without anyone signing in again.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return str(httpx.URL(AUTH_URL, params=params))


CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"


def missing_calendar_scope(tokens: dict) -> bool:
    """Did Google hand back a token that cannot touch the calendar?

    Asking for a scope is not the same as getting it. Google drops a scope it
    cannot grant -- most often because the Calendar API is not enabled on the
    project, or the scope is not configured under Data Access -- and returns a
    perfectly valid token for the scopes that survived. The failure then surfaces
    much later as a 403 from the first calendar call, which is a terrible place to
    discover it. The token response tells us up front, so check there.

    A response with no `scope` field at all is treated as fine: Google always
    sends one, and guessing "broken" would turn an unexpected shape into a
    refusal to link a working account.
    """
    granted = tokens.get("scope")
    if not granted:
        return False
    return CALENDAR_SCOPE not in granted.split()


def exchange_code(cfg: GoogleConfig, code: str) -> dict:
    resp = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "redirect_uri": cfg.redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise GoogleAuthError(f"Token exchange failed: {resp.text}")
    return resp.json()


def fetch_email(access_token: str) -> str:
    resp = httpx.get(
        USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=30
    )
    if resp.status_code != 200:
        raise GoogleAuthError(f"Could not read account email: {resp.text}")
    return resp.json()["email"]


def store_tokens(account: LinkedAccount, tokens: dict) -> None:
    account.access_token_enc = encrypt(tokens["access_token"])
    if tokens.get("refresh_token"):
        account.refresh_token_enc = encrypt(tokens["refresh_token"])
    account.token_expiry = utcnow_naive() + timedelta(
        seconds=int(tokens.get("expires_in", 3600))
    )
    account.status = "active"
    account.last_error = None


def access_token_for(db: Session, account: LinkedAccount) -> str:
    """Returns a usable access token, refreshing it first if it is close to expiring."""
    expiry = account.token_expiry
    fresh_enough = expiry is not None and expiry - timedelta(minutes=2) > utcnow_naive()
    token = decrypt(account.access_token_enc)
    if token and fresh_enough:
        return token
    return refresh_access_token(db, account)


def refresh_access_token(db: Session, account: LinkedAccount) -> str:
    cfg = load(db)
    refresh_token = decrypt(account.refresh_token_enc)
    if not refresh_token:
        _mark_needs_reauth(db, account, "No refresh token stored")
        raise GoogleAuthError("No refresh token stored; the account must be re-linked")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        # invalid_grant means the user revoked access or the token expired (Google
        # expires refresh tokens for OAuth apps left in "Testing" mode after 7 days).
        _mark_needs_reauth(db, account, resp.text)
        raise GoogleAuthError(f"Token refresh failed: {resp.text}")

    tokens = resp.json()
    store_tokens(account, tokens)
    db.commit()
    return tokens["access_token"]


def revoke(account: LinkedAccount) -> None:
    token = decrypt(account.refresh_token_enc) or decrypt(account.access_token_enc)
    if not token:
        return
    try:
        httpx.post(REVOKE_URL, data={"token": token}, timeout=15)
    except httpx.HTTPError:
        pass  # Local unlink should succeed even if Google is unreachable.


def _mark_needs_reauth(db: Session, account: LinkedAccount, error: str) -> None:
    account.status = "needs_reauth"
    account.last_error = error[:1000]
    db.commit()
