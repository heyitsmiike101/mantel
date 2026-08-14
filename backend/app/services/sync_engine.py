"""Two-way sync, for any provider.

Nothing here knows about Google or CalDAV. It knows about calendars that have a
remote counterpart, events that carry a pending state, and a cursor that can go
stale -- and it applies the same conflict rule, the same queue drain and the same
recovery to all of them. The service-specific parts live in `services/providers/`.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Calendar, Event, LinkedAccount
from ..timeutil import utcnow_naive
from . import recurrence
from .notify import calendar_changed
from .providers.base import (
    OCCURRENCE_SEP,
    ProviderAuthError,
    ProviderError,
    RemoteEvent,
    SyncTokenExpired,
)
from .providers.registry import for_account

log = logging.getLogger(__name__)

# Injected by tests so the sync logic can be exercised without touching a real service.
provider_factory = for_account

# Both are "the remote side would not cooperate", and every loop here treats them
# the same way: record it against the calendar and keep going.
REMOTE_FAILURES = (ProviderError, ProviderAuthError)


# --------------------------- Calendar discovery -------------------------------


def discover_calendars(db: Session, account: LinkedAccount) -> list[Calendar]:
    """Records every calendar the linked account can see. They start unclaimed, so nothing
    appears on the wall display until a family member deliberately claims it."""
    entries = provider_factory(db, account).list_calendars()
    existing = {
        c.remote_id: c
        for c in db.scalars(select(Calendar).where(Calendar.linked_account_id == account.id))
    }
    result = []
    for entry in entries:
        cal = existing.get(entry.id)
        if cal is None:
            cal = Calendar(
                linked_account_id=account.id,
                remote_id=entry.id,
                # A provider that gives no title leaves the id, which is at least
                # something to recognise the row by on the Calendars page.
                name=entry.name or entry.id,
                access_role=entry.access_role,
                sync_enabled=False,
            )
            db.add(cal)
        else:
            cal.name = entry.name or cal.name
            cal.access_role = entry.access_role or cal.access_role
        result.append(cal)
    db.commit()
    return result


# -------------------------------- Pull ---------------------------------------


def discover_all(db: Session) -> int:
    """Re-read every linked account's calendar list, and report how many are new.

    Discovery used to run once, when an account was linked. A calendar created or
    shared afterwards was invisible here until the account was unlinked and
    reconnected -- which loses nothing but looks like the app is broken. It is one
    cheap call per account, so it now runs on every sync.

    A failure for one account must not stop the others: an expired token should
    not stop a working account from picking up its new calendars.
    """
    accounts = db.scalars(
        select(LinkedAccount).where(LinkedAccount.status == "active")
    ).all()

    added = 0
    for account in accounts:
        known = set(
            db.scalars(
                select(Calendar.google_calendar_id).where(
                    Calendar.linked_account_id == account.id
                )
            )
        )
        try:
            found = discover_calendars(db, account)
        except REMOTE_FAILURES as exc:
            log.warning("Calendar discovery failed for %s: %s", account.email, exc)
            db.rollback()
            continue
        added += sum(1 for cal in found if cal.remote_id not in known)

    return added


def pull_calendar(db: Session, cal: Calendar) -> int:
    """Brings one calendar up to date from its provider. Returns the changes applied."""
    account = cal.account
    if account is None or not cal.sync_enabled:
        return 0

    provider = provider_factory(db, account)
    time_min = (
        datetime.now(UTC) - timedelta(days=get_settings().sync_past_days)
    ).isoformat()

    try:
        items, next_token = provider.list_events(
            cal.remote_id, sync_token=cal.sync_token, time_min=time_min
        )
    except SyncTokenExpired:
        # The provider discarded our incremental cursor. Drop everything it gave us
        # before and start clean -- anything created locally and not yet pushed is
        # preserved, because it does not carry this provider's origin.
        log.info("Sync token expired for calendar %s; doing a full resync", cal.id)
        db.execute(
            delete(Event).where(
                Event.calendar_id == cal.id, Event.origin == account.provider
            )
        )
        cal.sync_token = None
        db.commit()
        items, next_token = provider.list_events(cal.remote_id, time_min=time_min)

    changes = 0
    for item in items:
        changes += _apply_remote_event(db, cal, item)
    changes += _prune_stale_occurrences(db, cal, items)

    cal.sync_token = next_token
    cal.last_synced_at = utcnow_naive()
    cal.sync_error = None
    db.commit()
    return changes


def _apply_remote_event(db: Session, cal: Calendar, item: RemoteEvent) -> int:
    if not item.id:
        return 0

    existing = db.scalar(
        select(Event).where(Event.calendar_id == cal.id, Event.google_event_id == item.id)
    )

    if item.deleted:
        return _forget_resource(db, cal, item.id)

    if item.start is None or item.end is None:
        return 0

    if existing is None:
        event = Event(
            calendar_id=cal.id,
            remote_id=item.id,
            remote_etag=item.etag,
            title=item.title,
            description=item.description,
            location=item.location,
            start_at=item.start,
            end_at=item.end,
            all_day=item.all_day,
            timezone=item.timezone,
            recurring_event_id=item.recurring_event_id,
            origin=cal.account.provider,
            sync_state="synced",
            remote_updated_at=item.updated,
        )
        _apply_recurrence(event, item)
        db.add(event)
        return 1

    # Last write wins: a local edit still waiting to be pushed is newer than whatever
    # the provider is reporting, so don't clobber it here -- the push loop will send it.
    if existing.sync_state != "synced":
        local_at = existing.local_updated_at
        if item.updated and local_at and item.updated > local_at:
            existing.sync_state = "synced"
        else:
            return 0

    existing.title = item.title
    existing.description = item.description
    existing.location = item.location
    existing.start_at = item.start
    existing.end_at = item.end
    existing.all_day = item.all_day
    existing.timezone = item.timezone
    existing.remote_etag = item.etag
    existing.recurring_event_id = item.recurring_event_id
    existing.remote_updated_at = item.updated
    _apply_recurrence(existing, item)
    return 1


def _apply_recurrence(event: Event, item: RemoteEvent) -> None:
    """Carries a series' rule, its exclusions, and when it stops.

    Only providers that hand back masters set any of this -- Google expands its own
    series, so every one of its items looks like a plain event here.

    `recurrence_end` is stored rather than derived on demand so `list_events` can
    skip a series that finished years ago in SQL, instead of loading and
    re-expanding it on every calendar request.
    """
    event.recurrence_rule = item.recurrence_rule
    event.exdates = _pack_exdates(item.exdates)
    event.recurrence_end = recurrence.series_end(
        item.recurrence_rule, event.start_at, event.end_at - event.start_at
    )


def _pack_exdates(moments: list[datetime]) -> str | None:
    return ",".join(m.isoformat() for m in sorted(set(moments))) or None


def _forget_resource(db: Session, cal: Calendar, remote_id: str) -> int:
    """Removes an event, and every occurrence that shared its remote resource.

    A CalDAV resource holds the whole series: the master and each occurrence
    somebody moved. When the server reports that resource gone, all of those rows
    have to go -- matching only the exact id would leave the moved occurrences
    behind as events with no series, which then never disappear.
    """
    rows = db.scalars(
        select(Event).where(
            Event.calendar_id == cal.id,
            or_(
                Event.google_event_id == remote_id,
                # autoescape matters: a Google id can contain '_', which LIKE would
                # otherwise read as a wildcard and over-match.
                Event.google_event_id.startswith(
                    f"{remote_id}{OCCURRENCE_SEP}", autoescape=True
                ),
            ),
        )
    ).all()
    for row in rows:
        db.delete(row)
    return len(rows)


def _prune_stale_occurrences(db: Session, cal: Calendar, items: list[RemoteEvent]) -> int:
    """Drops occurrence rows the provider has stopped sending.

    A resource arrives whole, so an occurrence that was moved and has now been put
    back simply isn't in the payload any more -- there is no deletion to report.
    Diffing component by component would be fragile, so anything belonging to a
    resource we just read and that did not appear in it is removed.

    Rows still queued for push are left alone. They are a local edit that has not
    reached the server yet, so the server not mentioning them means nothing.
    """
    seen: dict[str, set[str]] = {}
    for item in items:
        if item.deleted or not item.id:
            continue
        seen.setdefault(item.id.split(OCCURRENCE_SEP, 1)[0], set()).add(item.id)

    removed = 0
    for resource, ids in seen.items():
        rows = db.scalars(
            select(Event).where(
                Event.calendar_id == cal.id,
                Event.sync_state == "synced",
                Event.google_event_id.startswith(
                    f"{resource}{OCCURRENCE_SEP}", autoescape=True
                ),
            )
        ).all()
        for row in rows:
            if row.remote_id not in ids:
                db.delete(row)
                removed += 1
    return removed


def pull_all(db: Session) -> int:
    # Look for calendars added remotely since the last run, so a new one appears
    # on the Calendars page by itself. New calendars arrive with syncing off, so
    # this can never drop unexpected events onto the wall.
    discover_all(db)

    total = 0
    calendars = db.scalars(
        select(Calendar).where(
            Calendar.linked_account_id.is_not(None), Calendar.sync_enabled.is_(True)
        )
    ).all()
    for cal in calendars:
        try:
            total += pull_calendar(db, cal)
        except REMOTE_FAILURES as exc:
            log.warning("Pull failed for calendar %s: %s", cal.id, exc)
            db.rollback()
            cal.sync_error = str(exc)[:1000]
            db.commit()

    if total:
        # An event added on someone's phone arrives here, not through the API, so
        # this is the only place that can tell Home Assistant about it. Without this
        # -- and with HA's own polling switched off, as the setup guide instructs --
        # remotely-originated changes would never show up in Home Assistant at all.
        calendar_changed(db)

    return total


# -------------------------------- Push ---------------------------------------


def push_pending(db: Session) -> int:
    """Sends locally-made changes upstream. Each event carries its own pending state, so
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
        except REMOTE_FAILURES as exc:
            log.warning("Push failed for event %s: %s", event.id, exc)
            db.rollback()
            cal.sync_error = str(exc)[:1000]
            db.commit()
    return pushed


def _push_one(db: Session, cal: Calendar, event: Event) -> None:
    provider = provider_factory(db, cal.account)
    state = event.sync_state

    if state == "pending_delete":
        if event.remote_id:
            try:
                provider.delete_event(cal.remote_id, event.remote_id, event.remote_etag)
            except ProviderError as exc:
                if exc.status not in (404, 410):
                    raise  # already gone upstream is a success for our purposes
        db.delete(event)
        db.commit()
        return

    payload = _to_remote_event(event)

    if state == "pending_create" or not event.remote_id:
        created = provider.create_event(cal.remote_id, payload)
    else:
        try:
            created = provider.update_event(cal.remote_id, payload)
        except ProviderError as exc:
            if exc.status in (404, 410):
                # Deleted upstream while we were editing; recreate it rather than
                # losing it. A new remote id comes back, so clear the stale one.
                payload.id = ""
                created = provider.create_event(cal.remote_id, payload)
            else:
                raise

    event.remote_id = created.id or event.remote_id
    event.remote_etag = created.etag
    event.remote_updated_at = created.updated
    event.sync_state = "synced"
    # A provider that expands series itself now owns this one; stop rendering our
    # copy of it, or every occurrence appears twice.
    if event.recurrence_rule:
        event.is_master = provider.expands_recurrence
    db.commit()


def _to_remote_event(event: Event) -> RemoteEvent:
    return RemoteEvent(
        id=event.remote_id or "",
        etag=event.remote_etag,
        title=event.title,
        description=event.description,
        location=event.location,
        start=event.start_at,
        end=event.end_at,
        all_day=event.all_day,
        timezone=event.timezone,
        recurrence_rule=event.recurrence_rule,
    )
