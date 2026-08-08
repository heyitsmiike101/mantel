from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LinkedAccount, User
from ..services import google_config, google_oauth, icloud_auth, sync_engine
from ..services.crypto import read_state, sign_state
from ..services.google_api import GoogleApiError
from ..services.providers.base import ProviderAuthError, ProviderError

router = APIRouter(prefix="/accounts", tags=["accounts"])

# Codes handed to the UI in ?error=, which turns them into an explanation.
ERROR_NO_CALENDAR_SCOPE = "no_calendar_scope"
ERROR_DISCOVERY_FAILED = "calendar_list_failed"


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    provider: str
    email: str
    status: str
    last_error: str | None
    created_at: datetime


class AuthUrlOut(BaseModel):
    url: str


class ICloudLinkIn(BaseModel):
    user_id: int
    apple_id: str
    app_password: str


@router.get(
    "",
    response_model=list[AccountOut],
    summary="List linked calendar accounts",
    description=(
        "Both Google and iCloud accounts, distinguished by `provider`. Credentials "
        "are never returned. `status` is 'active' or 'needs_reauth'."
    ),
)
def list_accounts(db: Session = Depends(get_db)) -> list[LinkedAccount]:
    return list(db.scalars(select(LinkedAccount).order_by(LinkedAccount.email)))


@router.get(
    "/google/auth-url",
    response_model=AuthUrlOut,
    summary="Start linking a Google account",
    description=(
        "Returns the Google consent URL to send the family member to. After they approve, "
        "Google redirects back to /api/accounts/google/callback and the account is linked "
        "to the given user. One person can link as many Google accounts as they like."
    ),
)
def google_auth_url(
    user_id: int = Query(description="Which family member this Google account belongs to."),
    db: Session = Depends(get_db),
) -> AuthUrlOut:
    cfg = google_config.load(db)
    if not cfg.configured:
        raise HTTPException(
            400,
            "Google isn't set up yet. Add your Client ID and Client secret under "
            "Settings -> Google; the page walks you through creating them.",
        )
    if db.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    return AuthUrlOut(url=google_oauth.build_auth_url(cfg, sign_state({"user_id": user_id})))


@router.get(
    "/google/callback",
    include_in_schema=False,
    summary="OAuth redirect target",
)
def google_callback(
    state: str = Query(),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if error:
        return RedirectResponse(f"/settings?tab=google&error={error}")

    payload = read_state(state)
    if payload is None:
        raise HTTPException(400, "The link request expired or was tampered with. Try again.")
    user = db.get(User, payload["user_id"])
    if user is None:
        raise HTTPException(404, "User not found")
    if not code:
        raise HTTPException(400, "Google did not return an authorization code")

    tokens = google_oauth.exchange_code(google_config.load(db), code)

    # Google grants what it can and silently drops the rest. Linking an account
    # whose token cannot read a calendar leaves a row that looks connected and
    # fails on every sync, so refuse it here while we can still explain why.
    if google_oauth.missing_calendar_scope(tokens):
        return RedirectResponse(f"/settings?tab=google&error={ERROR_NO_CALENDAR_SCOPE}")

    email = google_oauth.fetch_email(tokens["access_token"])

    account = db.scalar(
        select(LinkedAccount).where(
            LinkedAccount.provider == "google", LinkedAccount.email == email
        )
    )
    if account is None:
        account = LinkedAccount(user_id=user.id, provider="google", email=email)
        db.add(account)
    else:
        account.user_id = user.id
    google_oauth.store_tokens(account, tokens)
    db.commit()

    try:
        sync_engine.discover_calendars(db, account)
    except GoogleApiError as exc:
        # The account is linked and the token is stored; only the first calendar
        # listing failed. Record why and send the person somewhere that explains
        # it, rather than returning a 500 that reads like the app is broken.
        account.status = "needs_reauth"
        account.last_error = f"Could not list calendars: {exc}"[:500]
        db.commit()
        return RedirectResponse(f"/settings?tab=google&error={ERROR_DISCOVERY_FAILED}")

    return RedirectResponse(f"/settings?tab=google&linked={email}")


@router.post(
    "/icloud",
    response_model=AccountOut,
    status_code=201,
    summary="Link an iCloud account",
    description=(
        "Apple has no OAuth for calendars, so this is a form rather than a consent "
        "screen: an Apple ID and an app-specific password generated at "
        "appleid.apple.com. The password is checked against iCloud before anything "
        "is saved, and stored encrypted. Calendars arrive with syncing switched off."
    ),
)
def link_icloud(payload: ICloudLinkIn, db: Session = Depends(get_db)) -> LinkedAccount:
    user = db.get(User, payload.user_id)
    if user is None:
        raise HTTPException(404, "User not found")

    apple_id = payload.apple_id.strip().lower()
    # Apple presents the password in groups separated by dashes and people paste it
    # that way, sometimes with a stray space. The dashes are part of it; spaces are not.
    password = "".join(payload.app_password.split())
    if not apple_id or not password:
        raise HTTPException(400, "Both the Apple ID and an app-specific password are needed")

    account = db.scalar(
        select(LinkedAccount).where(
            LinkedAccount.provider == "icloud", LinkedAccount.email == apple_id
        )
    )
    if account is None:
        account = LinkedAccount(user_id=user.id, provider="icloud", email=apple_id)
        db.add(account)
        db.flush()
    else:
        account.user_id = user.id

    try:
        icloud_auth.verify_and_store(db, account, password)
    except ProviderAuthError as exc:
        # Nothing has been written, so a wrong password leaves no trace of a
        # half-linked account behind.
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except ProviderError as exc:
        db.rollback()
        raise HTTPException(502, f"Could not reach iCloud: {exc.message}") from exc

    try:
        sync_engine.discover_calendars(db, account)
    except (ProviderError, ProviderAuthError) as exc:
        # The account is linked and the password is stored; only the first calendar
        # listing failed. Record why rather than returning a 500 that reads like the
        # app is broken -- the Calendars page will fill in on the next sync.
        account.status = "needs_reauth"
        account.last_error = f"Could not list calendars: {exc}"[:500]
        db.commit()

    return account


@router.delete(
    "/{account_id}",
    status_code=204,
    summary="Unlink a calendar account",
    description=(
        "Removes the account's calendars and their events from this app. Nothing is "
        "deleted from Google Calendar or iCloud itself.\n\n"
        "A Google token is revoked on the way out. An iCloud app-specific password "
        "cannot be revoked over CalDAV -- delete it at appleid.apple.com if you want "
        "it gone for good."
    ),
)
def unlink_account(account_id: int, db: Session = Depends(get_db)) -> None:
    account = db.get(LinkedAccount, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    if account.provider == "google":
        google_oauth.revoke(account)
    db.delete(account)
    db.commit()
