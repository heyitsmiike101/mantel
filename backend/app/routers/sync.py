from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Calendar, Event, LinkedAccount
from ..services import google_config, google_sync

router = APIRouter(prefix="/sync", tags=["sync"])


class CalendarSyncStatus(BaseModel):
    calendar_id: int
    name: str
    account_email: str | None
    sync_enabled: bool
    last_synced_at: datetime | None
    sync_error: str | None


class SyncStatusOut(BaseModel):
    google_configured: bool
    sync_enabled: bool
    interval_seconds: int
    accounts_needing_reauth: list[str]
    pending_pushes: int
    calendars: list[CalendarSyncStatus]


class SyncRunOut(BaseModel):
    pulled: int
    pushed: int
    new_calendars: int = 0


class DiscoverOut(BaseModel):
    new_calendars: int
    total_calendars: int


@router.get(
    "/status",
    response_model=SyncStatusOut,
    summary="Sync health",
    description=(
        "Shows when each calendar last synced and whether anything needs attention. "
        "`accounts_needing_reauth` lists Google accounts whose access expired -- those "
        "have to be linked again through the consent screen."
    ),
)
def sync_status(db: Session = Depends(get_db)) -> SyncStatusOut:
    s = get_settings()
    calendars = db.scalars(
        select(Calendar).where(Calendar.linked_account_id.is_not(None)).order_by(Calendar.name)
    ).all()
    reauth = db.scalars(
        select(LinkedAccount.email).where(LinkedAccount.status == "needs_reauth")
    ).all()
    pending_count = db.scalar(
        select(func.count()).select_from(Event).where(Event.sync_state != "synced")
    )

    return SyncStatusOut(
        # Credentials live in the database, not the environment -- reading them off
        # `settings` reported "not configured" on every install that set Google up
        # through the Settings page, which is now all of them.
        google_configured=google_config.load(db).configured,
        sync_enabled=s.sync_enabled,
        interval_seconds=s.sync_interval_seconds,
        accounts_needing_reauth=list(reauth),
        pending_pushes=pending_count,
        calendars=[
            CalendarSyncStatus(
                calendar_id=c.id,
                name=c.name,
                account_email=c.account.email if c.account else None,
                sync_enabled=c.sync_enabled,
                last_synced_at=c.last_synced_at,
                sync_error=c.sync_error,
            )
            for c in calendars
        ],
    )


@router.post(
    "/run",
    response_model=SyncRunOut,
    summary="Sync with Google now",
    description=(
        "Pushes anything pending, then pulls the latest from Google. Syncing also happens "
        "on a timer, so this is only needed when you don't want to wait."
    ),
)
def run_sync(db: Session = Depends(get_db)) -> SyncRunOut:
    pushed = google_sync.push_pending(db)
    # Discovery first, so a calendar added in Google is both listed *and* pulled
    # in the same run once somebody switches it on.
    new_calendars = google_sync.discover_all(db)
    pulled = google_sync.pull_all(db)
    return SyncRunOut(pulled=pulled, pushed=pushed, new_calendars=new_calendars)


@router.post(
    "/calendars",
    response_model=DiscoverOut,
    summary="Check Google for new calendars",
    description=(
        "Re-reads the calendar list of every linked Google account. A calendar created "
        "or shared with the account after it was linked shows up here. New calendars "
        "arrive with syncing switched off, so nothing appears on a display until "
        "somebody enables it."
    ),
)
def discover_calendars(db: Session = Depends(get_db)) -> DiscoverOut:
    new_calendars = google_sync.discover_all(db)
    total = db.scalar(
        select(func.count()).select_from(Calendar).where(Calendar.linked_account_id.is_not(None))
    )
    return DiscoverOut(new_calendars=new_calendars, total_calendars=total or 0)
