from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Calendar, Event
from ..schemas import EventCreate, EventOut, EventUpdate
from ..serializers import event_out
from ..services import recurrence
from ..services.notify import calendar_changed
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


def _id_list(raw: str, field: str) -> list[int]:
    """Parse a comma-separated id filter, or 400 if it isn't one.

    Without this, a non-numeric value reaches `int()` and raises ValueError,
    which FastAPI turns into a 500 — reporting a caller's typo as a server
    fault. Every other bad input on this endpoint answers 400.
    """
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            raise HTTPException(400, f"`{field}` must be comma-separated integers") from None
    return out


PROVIDER_NAMES = {"google": "Google", "icloud": "iCloud"}


def _read_only(cal: Calendar) -> str:
    """Name the service that made it read-only, not whichever one we shipped first."""
    provider = cal.account.provider if cal.account else ""
    where = PROVIDER_NAMES.get(provider, "the account it came from")
    return f"Calendar '{cal.name}' is read-only in {where}"


def _writable_calendar(db: Session, calendar_id: int) -> Calendar:
    cal = db.get(Calendar, calendar_id)
    if cal is None:
        raise HTTPException(404, "Calendar not found")
    if not cal.writable:
        raise HTTPException(403, _read_only(cal))
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
            and_(
                Event.recurrence_rule.is_not(None),
                Event.start_at < window_end,
                # A finished series is skipped here rather than being loaded and
                # re-expanded only to yield nothing. NULL means it never ends.
                or_(
                    Event.recurrence_end.is_(None),
                    Event.recurrence_end > window_start,
                ),
            ),
        )
    ).order_by(Event.start_at, Event.id)

    if calendar_ids:
        stmt = stmt.where(Event.calendar_id.in_(_id_list(calendar_ids, "calendar_ids")))
    if user_ids:
        stmt = stmt.where(Calendar.claimed_by_user_id.in_(_id_list(user_ids, "user_ids")))
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
    ev.recurrence_end = recurrence.series_end(
        ev.recurrence_rule, ev.start_at, ev.end_at - ev.start_at
    )
    mark_pending(ev, cal, "pending_create")
    db.add(ev)
    db.commit()
    request_push()
    calendar_changed(db)
    return event_out(_load(db, ev.id))


@router.get("/{event_id}", response_model=EventOut, summary="Get one event")
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventOut:
    return event_out(_load(db, event_id))


# What a moved event carries over. Everything a person can see or set, and nothing that
# belongs to the provider (remote id, etag) -- the copy is a new resource upstream.
_MOVED_FIELDS = (
    "title",
    "description",
    "location",
    "start_at",
    "end_at",
    "all_day",
    "timezone",
    "recurrence_rule",
    "exdates",
    "status",
)


_NULLABLE = {"description", "location", "timezone", "recurrence_rule"}


def _move_target(db: Session, ev: Event, calendar_id: int) -> Calendar:
    """The calendar an event may be moved to, or an HTTPException saying why not."""
    if ev.recurring_event_id is not None:
        # Google's instances and iCloud's moved occurrences are rows of their own that
        # point back at a series. Moving one would copy a single occurrence out and
        # leave the series behind, or delete it and punch a hole in the series.
        raise HTTPException(
            400,
            "This is one occurrence of a repeating event, and a single occurrence can't be "
            "moved to another calendar. Move the whole series from the calendar it was "
            "created on.",
        )
    target = _writable_calendar(db, calendar_id)
    if not target.is_local and not target.sync_enabled:
        # The push queue skips calendars with syncing off, so the event would save here
        # and never reach the provider.
        raise HTTPException(
            400,
            f"Syncing is switched off for calendar '{target.name}', so an event moved there "
            "would never be sent. Turn syncing on for it first.",
        )
    return target


def _move_event(db: Session, ev: Event, target: Calendar, changes: dict) -> Event:
    """Move by creating on the target and deleting from the source.

    Providers cannot move a resource between calendars, let alone between accounts, so
    the move is a new event plus a delete. Both happen in one commit: if the create push
    later fails the new row stays `pending_create` and is retried, so nothing is lost,
    and the old row is already `pending_delete` so a background pull of the source
    calendar neither shows it (list_events hides it) nor overwrites it
    (`_apply_remote_event` leaves unsynced rows alone).
    """
    values = {field: getattr(ev, field) for field in _MOVED_FIELDS}
    # An explicit null on a required field is ignored, as it would otherwise erase it.
    values.update({k: v for k, v in changes.items() if v is not None or k in _NULLABLE})
    if values["end_at"] <= values["start_at"]:
        raise HTTPException(400, "`end_at` must be after `start_at`")
    if not values["recurrence_rule"]:
        values["exdates"] = None  # exclusions mean nothing without a series

    moved = Event(calendar_id=target.id, origin="local", **values)
    moved.recurrence_end = recurrence.series_end(
        moved.recurrence_rule, moved.start_at, moved.end_at - moved.start_at
    )
    mark_pending(moved, target, "pending_create")
    db.add(moved)

    if ev.calendar.is_local or ev.google_event_id is None:
        db.delete(ev)  # nothing upstream to clean up
    else:
        ev.sync_state = "pending_delete"
    db.commit()
    return moved


@router.patch(
    "/{event_id}",
    response_model=EventOut,
    summary="Update an event",
    description=(
        "Only the fields you send are changed. Google- and iCloud-backed events are pushed "
        "automatically.\n\n"
        "Sending a different `calendar_id` **moves** the event to that calendar, which can "
        "belong to another account or service. A move is a create on the new calendar plus a "
        "delete on the old one, so the response carries a **new `id`** and the old id stops "
        "working. The target must be writable, and a synced calendar must have syncing "
        "switched on. A repeating event moves as a whole series; a single occurrence of a "
        "series (`recurring` true with no `recurrence_rule`) cannot be moved and answers 400."
    ),
)
def update_event(event_id: int, payload: EventUpdate, db: Session = Depends(get_db)) -> EventOut:
    ev = _load(db, event_id)
    if not ev.calendar.writable:
        raise HTTPException(403, _read_only(ev.calendar))

    changes = payload.model_dump(exclude_unset=True)
    new_calendar_id = changes.pop("calendar_id", None)
    moving = new_calendar_id is not None and new_calendar_id != ev.calendar_id
    target = _move_target(db, ev, new_calendar_id) if moving else None
    for key in ("start_at", "end_at"):
        if changes.get(key) is not None:
            changes[key] = to_utc(changes[key])
    if changes.get("recurrence_rule"):
        try:
            changes["recurrence_rule"] = recurrence.validate(changes["recurrence_rule"])
        except recurrence.RecurrenceError as exc:
            raise HTTPException(400, str(exc)) from exc

    if target is not None:
        moved = _move_event(db, ev, target, changes)
        request_push()
        calendar_changed(db)
        return event_out(_load(db, moved.id))

    for key, value in changes.items():
        setattr(ev, key, value)
    if ev.end_at <= ev.start_at:
        raise HTTPException(400, "`end_at` must be after `start_at`")
    ev.recurrence_end = recurrence.series_end(
        ev.recurrence_rule, ev.start_at, ev.end_at - ev.start_at
    )

    mark_pending(ev, ev.calendar, "pending_update")
    db.commit()
    request_push()
    calendar_changed(db)
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
        raise HTTPException(403, _read_only(ev.calendar))

    if ev.calendar.is_local or ev.google_event_id is None:
        db.delete(ev)
    else:
        ev.sync_state = "pending_delete"
    db.commit()
    request_push()
    calendar_changed(db)
