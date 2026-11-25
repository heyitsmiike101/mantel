from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from ..models import Calendar, Event, EventHistory, EventIdentifier

FIELDS = (
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


def _snapshot(event_id: int, calendar: Calendar, values: dict, action: str) -> dict:
    return {
        "event_id": event_id,
        "calendar_id": calendar.id,
        "calendar_name": calendar.name,
        "calendar_source": calendar.account.provider if calendar.account else "local",
        "calendar_created_at": calendar.created_at,
        "action": action,
        **{field: values[field] for field in FIELDS},
    }


def _insert(db: Session, data: dict) -> None:
    db.connection().execute(EventHistory.__table__.insert().values(**data))


def snapshot(db: Session, event: Event, action: str) -> None:
    calendar = event.calendar or db.get(Calendar, event.calendar_id)
    _insert(db, _snapshot(event.id, calendar, {f: getattr(event, f) for f in FIELDS}, action))


def allocate_ids(db: Session, flush_context, instances) -> None:
    for row in db.new:
        if not isinstance(row, Event) or row.id is not None:
            continue
        connection = db.connection()
        reserved = connection.execute(
            EventIdentifier.__table__.insert().values()
        ).inserted_primary_key[0]
        highest_live = connection.scalar(select(func.max(Event.id))) or 0
        highest_recorded = connection.scalar(select(func.max(EventHistory.event_id))) or 0
        row.id = max(reserved, highest_live + 1, highest_recorded + 1)
        if row.id != reserved:
            connection.execute(
                EventIdentifier.__table__.update()
                .where(EventIdentifier.id == reserved)
                .values(id=row.id)
            )


def capture_changes(db: Session, flush_context, instances) -> None:
    for row in db.deleted:
        if isinstance(row, Event) and row.id is not None and row.sync_state != "pending_delete":
            snapshot(db, row, "deleted")

    for row in db.dirty:
        if not isinstance(row, Event) or row in db.deleted or row.id is None:
            continue
        previous = db.connection().execute(
            select(Event.__table__).where(Event.id == row.id)
        ).mappings().first()
        if previous is None:
            continue
        current = {field: getattr(row, field) for field in FIELDS}
        if any(previous[field] != current[field] for field in FIELDS):
            calendar = row.calendar or db.get(Calendar, row.calendar_id)
            _insert(db, _snapshot(row.id, calendar, previous, "before_update"))
            _insert(db, _snapshot(row.id, calendar, current, "updated"))
        elif row.sync_state == "pending_delete" and previous["sync_state"] != "pending_delete":
            snapshot(db, row, "deleted")


def capture_created(db: Session, flush_context) -> None:
    for row in db.new:
        if isinstance(row, Event):
            snapshot(db, row, "created")


def register(session_factory) -> None:
    event.listen(session_factory, "before_flush", allocate_ids)
    event.listen(session_factory, "before_flush", capture_changes)
    event.listen(session_factory, "after_flush", capture_created)
