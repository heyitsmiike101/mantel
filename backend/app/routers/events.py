from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Calendar, Event
from ..schemas import EventCreate, EventOut, EventUpdate
from ..serializers import event_out
from ..services import recurrence
from ..services.pushqueue import mark_pending, request_push
from ..timeutil import to_utc

router = APIRouter(prefix="/events", tags=["events"])


def _load(db: Session, event_id: int) -> Event:
    ev = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .options(selectinload(Event.calendar).selectinload(Calendar.claimed_by))
    )
    if ev is None:
        raise HTTPException(404, "Event not found")
    return ev


def _writable_calendar(db: Session, calendar_id: int) -> Calendar:
    cal = db.get(Calendar, calendar_id)
    if cal is None:
        raise HTTPException(404, "Calendar not found")
    if not cal.writable:
        raise HTTPException(403, f"Calendar '{cal.name}' is read-only in Google")
    return cal


@router.get(
    "",
    response_model=list[EventOut],
    summary="List events in a date range",
    description=(
        "The single query endpoint every view uses. Always pass `start` and `end`; there is no "
        "pagination because a date range is the natural bound for a calendar.\n\n"
        "An event is returned when it overlaps the range at all, so a multi-day event shows up "
        "on every day it touches. Each event includes its resolved display `color` and the "
        "`user_id` of whoever owns its calendar, so no follow-up requests are needed."
    ),
)
def list_events(
    start: datetime = Query(
        description="Range start, inclusive.", examples=["2026-08-01T00:00:00Z"]
    ),
    end: datetime = Query(
        description="Range end, exclusive.", examples=["2026-08-08T00:00:00Z"]
    ),
    calendar_ids: str | None = Query(default=None, description="Comma-separated calendar ids."),
    user_ids: str | None = Query(
        default=None, description="Comma-separated user ids; matches calendars they claimed."
    ),
    q: str | None = Query(default=None, description="Case-insensitive text search on title."),
    include_unclaimed: bool = Query(
        default=True, description="Set false to hide calendars nobody has claimed."
    ),
    db: Session = Depends(get_db),
) -> list[EventOut]:
    if end <= start:
        raise HTTPException(400, "`end` must be after `start`")

    window_start, window_end = to_utc(start), to_utc(end)

    # Two shapes of row live in this table. A plain event is selected by its own
    # dates. A recurring series has only its FIRST occurrence's dates stored, so
    # it can't be date-filtered in SQL -- it is fetched by rule and expanded below.
    base = (
        select(Event)
        .join(Calendar)
        .where(
            Event.status == "confirmed",
            Event.sync_state != "pending_delete",
            # A master already pushed to Google is represented by Google's own
            # expanded instances; showing it too would duplicate every occurrence.
            Event.is_master.is_(False),
        )
        .options(selectinload(Event.calendar).selectinload(Calendar.claimed_by))
    )

    stmt = base.where(
        or_(
            and_(
                Event.recurrence_rule.is_(None),
                Event.start_at < window_end,
                Event.end_at > window_start,
            ),
            and_(Event.recurrence_rule.is_not(None), Event.start_at < window_end),
        )
    ).order_by(Event.start_at, Event.id)

    if calendar_ids:
        ids = [int(i) for i in calendar_ids.split(",") if i.strip()]
        stmt = stmt.where(Event.calendar_id.in_(ids))
    if user_ids:
        uids = [int(i) for i in user_ids.split(",") if i.strip()]
        stmt = stmt.where(Calendar.claimed_by_user_id.in_(uids))
    elif not include_unclaimed:
        stmt = stmt.where(
            or_(Calendar.claimed_by_user_id.is_not(None), Calendar.linked_account_id.is_(None))
        )
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{q}%"))

    rows = list(db.scalars(stmt))

    expanded: list[Event] = []
    for row in rows:
        if row.recurrence_rule:
            expanded.extend(recurrence.materialise(row, window_start, window_end))
        else:
            expanded.append(row)

    expanded.sort(key=lambda e: (e.start_at, e.id))
    return [event_out(e) for e in expanded]


@router.post(
    "",
    response_model=EventOut,
    status_code=201,
    summary="Create an event",
    description=(
        "Writes the event immediately and returns it. If the calendar is backed by Google, the "
        "event is queued and pushed within seconds — you do not need to wait or poll."
    ),
)
def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> EventOut:
    if payload.end_at <= payload.start_at:
        raise HTTPException(400, "`end_at` must be after `start_at`")
    cal = _writable_calendar(db, payload.calendar_id)

    data = payload.model_dump()
    data["start_at"] = to_utc(data["start_at"])
    data["end_at"] = to_utc(data["end_at"])
    if data.get("recurrence_rule"):
        try:
            data["recurrence_rule"] = recurrence.validate(data["recurrence_rule"])
        except recurrence.RecurrenceError as exc:
            raise HTTPException(400, str(exc)) from exc
    ev = Event(**data, origin="local")
    mark_pending(ev, cal, "pending_create")
    db.add(ev)
    db.commit()
    request_push()
    return event_out(_load(db, ev.id))


@router.get("/{event_id}", response_model=EventOut, summary="Get one event")
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventOut:
    return event_out(_load(db, event_id))


@router.patch(
    "/{event_id}",
    response_model=EventOut,
    summary="Update an event",
    description=(
        "Only the fields you send are changed. Google-backed events are pushed automatically."
    ),
)
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db)) -> EventOut:
    ev = _load(db, event_id)
    if not ev.calendar.writable:
        raise HTTPException(403, f"Calendar '{ev.calendar.name}' is read-only in Google")

    changes = payload.model_dump(exclude_unset=True)
    if "calendar_id" in changes and changes["calendar_id"] != ev.calendar_id:
        # Moving between calendars means deleting remotely and recreating; keep v1 simple.
        raise HTTPException(400, "Moving an event between calendars is not supported yet")
    for key in ("start_at", "end_at"):
        if changes.get(key) is not None:
            changes[key] = to_utc(changes[key])
    if changes.get("recurrence_rule"):
        try:
            changes["recurrence_rule"] = recurrence.validate(changes["recurrence_rule"])
        except recurrence.RecurrenceError as exc:
            raise HTTPException(400, str(exc)) from exc
    for key, value in changes.items():
        setattr(ev, key, value)
    if ev.end_at <= ev.start_at:
        raise HTTPException(400, "`end_at` must be after `start_at`")

    mark_pending(ev, ev.calendar, "pending_update")
    db.commit()
    request_push()
    return event_out(_load(db, event_id))


@router.delete(
    "/{event_id}",
    status_code=204,
    summary="Delete an event",
    description=(
        "Removes the event. For Google-backed calendars it is first marked for deletion, then "
        "removed from Google and this database once the push succeeds."
    ),
)
def delete_event(event_id: int, db: Session = Depends(get_db)) -> None:
    ev = _load(db, event_id)
    if not ev.calendar.writable:
        raise HTTPException(403, f"Calendar '{ev.calendar.name}' is read-only in Google")

    if ev.calendar.is_local or ev.google_event_id is None:
        db.delete(ev)
    else:
        ev.sync_state = "pending_delete"
    db.commit()
    request_push()
