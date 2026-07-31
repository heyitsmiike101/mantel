from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import LinkedAccount, User
from ..services import google_config, google_oauth, google_sync
from ..services.crypto import read_state, sign_state

router = APIRouter(prefix="/accounts", tags=["accounts"])


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


@router.get(
    "",
    response_model=list[AccountOut],
    summary="List linked Google accounts",
    description="Tokens are never returned. `status` is 'active' or 'needs_reauth'.",
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

    google_sync.discover_calendars(db, account)
    return RedirectResponse(f"/settings?tab=google&linked={email}")


@router.delete(
    "/{account_id}",
    status_code=204,
    summary="Unlink a Google account",
    description=(
        "Revokes the token with Google and removes the account's calendars and their "
        "events from this app. Nothing is deleted from Google Calendar itself."
    ),
)
def unlink_account(account_id: int, db: Session = Depends(get_db)) -> None:
    account = db.get(LinkedAccount, account_id)
    if account is None:
        raise HTTPException(404, "Account not found")
    google_oauth.revoke(account)
    db.delete(account)
    db.commit()
