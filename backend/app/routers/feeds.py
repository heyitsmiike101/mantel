from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..models import Calendar, Event
from ..services import ics, recurrence
from ..services.crypto import feed_token, valid_feed_token

router = APIRouter(prefix="/feeds", tags=["feeds"])


def _events(db: Session, calendar_id: int | None) -> tuple[list[Event], str]:
    start, end = ics.default_window()

    stmt = (
        select(Event)
        .join(Calendar)
        .where(
            Event.status == "confirmed",
            Event.sync_state != "pending_delete",
            Event.start_at < end,
        )
        .options(selectinload(Event.calendar))
        .order_by(Event.start_at, Event.id)
    )
    if calendar_id is not None:
        stmt = stmt.where(Event.calendar_id == calendar_id)

    rows = []
    for row in db.scalars(stmt):
        # A series is exported once, with its RRULE -- subscribers expand it
        # themselves, which is both smaller and what they expect.
        if row.recurrence_rule or row.end_at > start:
            rows.append(row)

    if calendar_id is not None:
        cal = db.get(Calendar, calendar_id)
        return rows, (cal.name if cal else "Calendar")
    return rows, "Family Calendar"


@router.get(
    "/token",
    summary="Get the subscription token",
    description=(
        "Returns the secret token that the feed URLs require. It is derived from "
        "SECRET_KEY, so it is stable across restarts and changes if you rotate that key."
    ),
)
def get_token() -> dict:
    base = get_settings().public_base_url.rstrip("/")
    token = feed_token()
    return {
        "token": token,
        "all_calendars_url": f"{base}/api/feeds/all.ics?token={token}",
        "hint": (
            "Subscribe to this URL in Apple Calendar, Outlook, or Home Assistant's "
            "Remote Calendar integration. Treat it like a password: anyone with the "
            "link can read the family's schedule."
        ),
    }


@router.get(
    "/all.ics",
    response_class=PlainTextResponse,
    summary="Subscribe to every calendar",
    description=(
        "A read-only iCalendar feed of the whole family schedule, covering the last "
        "90 days and the next year. Point Apple Calendar, Outlook, or Home Assistant's "
        "Remote Calendar at it.\n\n"
        "Requires `?token=`, because unlike the rest of this API a feed URL is the one "
        "thing likely to be pasted into a service outside the house."
    ),
)
def all_calendars(
    token: str = Query(description="From GET /api/feeds/token."),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    return _feed_response(db, None, token)


@router.get(
    "/{calendar_id}.ics",
    response_class=PlainTextResponse,
    summary="Subscribe to one calendar",
)
def one_calendar(
    calendar_id: int,
    token: str = Query(description="From GET /api/feeds/token."),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    if db.get(Calendar, calendar_id) is None:
        raise HTTPException(404, "Calendar not found")
    return _feed_response(db, calendar_id, token)


def _feed_response(db: Session, calendar_id: int | None, token: str) -> PlainTextResponse:
    if not valid_feed_token(token):
        raise HTTPException(403, "Invalid feed token")

    events, name = _events(db, calendar_id)
    body = ics.build(events, name)
    return PlainTextResponse(
        body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="family-calendar.ics"',
            "Cache-Control": "no-cache",
        },
    )


# Re-exported so the events router can nudge subscribers without importing the
# service module directly.
__all__ = ["router", "recurrence"]
