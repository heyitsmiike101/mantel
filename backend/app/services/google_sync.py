import logging
from datetime import UTC, datetime, timedelta

from dateutil import parser as dateparser
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Calendar, Event, LinkedAccount
from ..timeutil import utcnow_naive
from .google_api import GoogleApiError, GoogleCalendarClient, SyncTokenExpired
from .google_oauth import GoogleAuthError, access_token_for

log = logging.getLogger(__name__)

# Injected by tests so the sync logic can be exercised without touching Google.
client_factory = GoogleCalendarClient


def _client(db: Session, account: LinkedAccount) -> GoogleCalendarClient:
    return client_factory(access_token_for(db, account))


# --------------------------- Calendar discovery -------------------------------


def discover_calendars(db: Session, account: LinkedAccount) -> list[Calendar]:
    """Records every calendar the linked account can see. They start unclaimed, so nothing
    appears on the wall display until a family member deliberately claims it."""
    entries = _client(db, account).list_calendars()
    existing = {
        c.google_calendar_id: c
        for c in db.scalars(select(Calendar).where(Calendar.linked_account_id == account.id))
    }
    result = []
    for entry in entries:
        gid = entry["id"]
        cal = existing.get(gid)
        if cal is None:
            cal = Calendar(
                linked_account_id=account.id,
                google_calendar_id=gid,
                name=entry.get("summary", gid),
                access_role=entry.get("accessRole", "reader"),
                sync_enabled=False,
            )
            db.add(cal)
        else:
            cal.name = entry.get("summary", cal.name)
            cal.access_role = entry.get("accessRole", cal.access_role)
        result.append(cal)
    db.commit()
    return result


# -------------------------------- Pull ---------------------------------------


def pull_calendar(db: Session, cal: Calendar) -> int:
    """Brings one calendar up to date from Google. Returns the number of changes applied."""
    account = cal.account
    if account is None or not cal.sync_enabled:
        return 0

    client = _client(db, account)
    time_min = (
        datetime.now(UTC) - timedelta(days=get_settings().sync_past_days)
    ).isoformat()

    try:
        items, next_token = client.list_events(
            cal.google_calendar_id, sync_token=cal.sync_token, time_min=time_min
        )
    except SyncTokenExpired:
        # Google discarded our incremental cursor. Drop everything it gave us before and
        # start clean -- anything created locally and not yet pushed is preserved.
        log.info("Sync token expired for calendar %s; doing a full resync", cal.id)
        db.execute(
            delete(Event).where(Event.calendar_id == cal.id, Event.origin == "google")
        )
        cal.sync_token = None
        db.commit()
        items, next_token = client.list_events(cal.google_calendar_id, time_min=time_min)

    changes = 0
    for item in items:
        changes += _apply_remote_event(db, cal, item)

    cal.sync_token = next_token
    cal.last_synced_at = utcnow_naive()
    cal.sync_error = None
    db.commit()
    return changes


def _apply_remote_event(db: Session, cal: Calendar, item: dict) -> int:
    gid = item.get("id")
    if not gid:
        return 0

    existing = db.scalar(
        select(Event).where(Event.calendar_id == cal.id, Event.google_event_id == gid)
    )

    if item.get("status") == "cancelled":
        if existing is not None:
            db.delete(existing)
            return 1
        return 0

    start, end, all_day = _parse_times(item)
    if start is None or end is None:
        return 0

    remote_updated = _parse_dt(item.get("updated"))

    if existing is None:
        db.add(
            Event(
                calendar_id=cal.id,
                google_event_id=gid,
                google_etag=item.get("etag"),
                title=item.get("summary") or "(no title)",
                description=item.get("description"),
                location=item.get("location"),
                start_at=start,
                end_at=end,
                all_day=all_day,
                timezone=item.get("start", {}).get("timeZone"),
                recurring_event_id=item.get("recurringEventId"),
                origin="google",
                sync_state="synced",
                remote_updated_at=remote_updated,
            )
        )
        return 1

    # Last write wins: a local edit still waiting to be pushed is newer than whatever
    # Google is reporting, so don't clobber it here -- the push loop will send it.
    if existing.sync_state != "synced":
        local_at = existing.local_updated_at
        if remote_updated and local_at and remote_updated > local_at:
            existing.sync_state = "synced"
        else:
            return 0

    existing.title = item.get("summary") or "(no title)"
    existing.description = item.get("description")
    existing.location = item.get("location")
    existing.start_at = start
    existing.end_at = end
    existing.all_day = all_day
    existing.timezone = item.get("start", {}).get("timeZone")
    existing.google_etag = item.get("etag")
    existing.recurring_event_id = item.get("recurringEventId")
    existing.remote_updated_at = remote_updated
    return 1


def pull_all(db: Session) -> int:
    total = 0
    calendars = db.scalars(
        select(Calendar).where(
            Calendar.linked_account_id.is_not(None), Calendar.sync_enabled.is_(True)
        )
    ).all()
    for cal in calendars:
        try:
            total += pull_calendar(db, cal)
        except (GoogleApiError, GoogleAuthError) as exc:
            log.warning("Pull failed for calendar %s: %s", cal.id, exc)
            db.rollback()
            cal.sync_error = str(exc)[:1000]
            db.commit()
    return total


# -------------------------------- Push ---------------------------------------


def push_pending(db: Session) -> int:
    """Sends locally-made changes to Google. Each event carries its own pending state, so
    this is just a queue drain -- no separate table to keep in step."""
    queued = ["pending_create", "pending_update", "pending_delete"]
    pending = db.scalars(select(Event).where(Event.sync_state.in_(queued))).all()

    pushed = 0
    for event in pending:
        cal = event.calendar
        if cal is None or cal.account is None or not cal.sync_enabled:
            continue
        try:
            _push_one(db, cal, event)
            pushed += 1
        except (GoogleApiError, GoogleAuthError) as exc:
            log.warning("Push failed for event %s: %s", event.id, exc)
            db.rollback()
            cal.sync_error = str(exc)[:1000]
            db.commit()
    return pushed


def _push_one(db: Session, cal: Calendar, event: Event) -> None:
    client = _client(db, cal.account)
    state = event.sync_state

    if state == "pending_delete":
        if event.google_event_id:
            try:
                client.delete_event(cal.google_calendar_id, event.google_event_id)
            except GoogleApiError as exc:
                if exc.status not in (404, 410):
                    raise  # already gone in Google is a success for our purposes
        db.delete(event)
        db.commit()
        return

    body = _to_google_body(event)

    if state == "pending_create" or not event.google_event_id:
        created = client.insert_event(cal.google_calendar_id, body)
        event.google_event_id = created.get("id")
        event.google_etag = created.get("etag")
        event.remote_updated_at = _parse_dt(created.get("updated"))
    else:
        try:
            updated = client.patch_event(cal.google_calendar_id, event.google_event_id, body)
        except GoogleApiError as exc:
            if exc.status in (404, 410):
                # Deleted in Google while we were editing; recreate it rather than losing it.
                updated = client.insert_event(cal.google_calendar_id, body)
                event.google_event_id = updated.get("id")
            else:
                raise
        event.google_etag = updated.get("etag")
        event.remote_updated_at = _parse_dt(updated.get("updated"))

    event.sync_state = "synced"
    db.commit()


def _to_google_body(event: Event) -> dict:
    if event.all_day:
        start = {"date": event.start_at.date().isoformat()}
        end = {"date": event.end_at.date().isoformat()}
    else:
        start = {"dateTime": _iso_utc(event.start_at)}
        end = {"dateTime": _iso_utc(event.end_at)}
    return {
        "summary": event.title,
        "description": event.description,
        "location": event.location,
        "start": start,
        "end": end,
    }


# ------------------------------- helpers -------------------------------------


def _iso_utc(dt: datetime) -> str:
    aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = dateparser.isoparse(value)
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


def _parse_times(item: dict) -> tuple[datetime | None, datetime | None, bool]:
    start_obj = item.get("start") or {}
    end_obj = item.get("end") or {}

    if "date" in start_obj:
        # All-day: Google gives plain dates with an exclusive end, which is exactly how
        # they are stored here, so no timezone conversion should happen.
        start = dateparser.isoparse(start_obj["date"])
        end = dateparser.isoparse(end_obj.get("date", start_obj["date"]))
        return start, end, True

    start = _parse_dt(start_obj.get("dateTime"))
    end = _parse_dt(end_obj.get("dateTime"))
    return start, end, False
