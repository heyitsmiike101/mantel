"""Pulling from iCloud.

Mirrors `test_google_sync.py` case for case, because the guarantee is that an
iCloud calendar behaves exactly like a Google one once it is switched on. Where
the two genuinely differ -- floating times, a resource holding several
components -- there are extra cases here.
"""

from datetime import datetime

import pytest
from fake_caldav import CALENDAR, PARTITION_HOST, FakeCalDav, vallday, vevent

from app.models import Calendar, Event, LinkedAccount, User
from app.services import sync_engine
from app.services.caldav_client import CalDavClient
from app.services.crypto import encrypt
from app.services.providers.icloud import ICloudProvider


@pytest.fixture
def server():
    return FakeCalDav()


@pytest.fixture
def provider(server, monkeypatch):
    """The fake sits at the HTTP layer, so the XML and iCalendar handling that this
    feature actually rests on is exercised rather than stubbed past."""

    def build(db, account, tz="UTC"):
        dav = CalDavClient("someone@icloud.com", "pw", http=server.client())
        return ICloudProvider(dav, f"{PARTITION_HOST}{CALENDAR}".rsplit("/", 2)[0] + "/", tz)

    holder = {"tz": "UTC"}
    monkeypatch.setattr(
        sync_engine,
        "provider_factory",
        lambda db, account: build(db, account, holder["tz"]),
    )
    return holder


@pytest.fixture
def icloud(client, db, provider):
    user = User(name="Mike", color="#3b82f6")
    db.add(user)
    db.flush()
    account = LinkedAccount(
        user_id=user.id,
        provider="icloud",
        email="mike@icloud.com",
        password_enc=encrypt("app-specific-password"),
        calendar_home_url=f"{PARTITION_HOST}/1234567890/calendars/",
    )
    db.add(account)
    db.flush()
    cal = Calendar(
        linked_account_id=account.id,
        google_calendar_id=CALENDAR,
        name="Home",
        claimed_by_user_id=user.id,
        sync_enabled=True,
        access_role="writer",
    )
    db.add(cal)
    db.commit()
    return cal


# ------------------------------ discovery ------------------------------------


def test_discovery_records_calendars_unclaimed_and_not_syncing(client, db, provider, icloud):
    """Same rule as Google: nothing reaches the wall until somebody opts in."""
    account = db.get(LinkedAccount, icloud.linked_account_id)
    db.delete(icloud)
    db.commit()

    found = sync_engine.discover_calendars(db, account)

    assert [c.name for c in found] == ["Home"]
    assert found[0].sync_enabled is False
    assert found[0].claimed_by_user_id is None
    assert found[0].remote_id == CALENDAR


def test_discovery_is_idempotent(client, db, provider, icloud):
    account = db.get(LinkedAccount, icloud.linked_account_id)
    sync_engine.discover_calendars(db, account)
    sync_engine.discover_calendars(db, account)

    assert db.query(Calendar).filter(Calendar.linked_account_id == account.id).count() == 1


def test_write_privileges_make_the_calendar_writable(client, db, provider, icloud):
    account = db.get(LinkedAccount, icloud.linked_account_id)
    found = sync_engine.discover_calendars(db, account)
    assert found[0].access_role == "writer"
    assert found[0].writable is True


# -------------------------------- pull ---------------------------------------


def test_initial_pull_takes_the_token_before_reading(client, db, provider, icloud, server):
    """Order matters. Taking the cursor after the read would lose anything that
    changed in between, permanently."""
    server.add_event("a.ics", vevent("a", "Dentist", "20260803T170000Z", "20260803T180000Z"))

    assert sync_engine.pull_calendar(db, icloud) == 1

    assert server.reports == ["baseline", "query", "multiget"], (
        "the cursor must be taken before the read; the other order silently drops "
        "anything that changes in between"
    )
    assert server.last_time_range is not None, "the read must still be bounded"
    db.refresh(icloud)
    assert icloud.sync_token == "sync-1"


def test_pulled_events_are_stored_with_the_icloud_origin(client, db, provider, icloud, server):
    server.add_event("a.ics", vevent("a", "Dentist", "20260803T170000Z", "20260803T180000Z"))
    sync_engine.pull_calendar(db, icloud)

    stored = db.query(Event).one()
    assert stored.title == "Dentist"
    assert stored.origin == "icloud"
    assert stored.remote_id == "a.ics", "the filename, not the whole path"
    assert stored.start_at == datetime(2026, 8, 3, 17, 0)
    assert stored.sync_state == "synced"


def test_second_pull_uses_the_sync_token(client, db, provider, icloud, server):
    server.add_event("a.ics", vevent("a", "Dentist", "20260803T170000Z", "20260803T180000Z"))
    sync_engine.pull_calendar(db, icloud)

    server.changed = []
    sync_engine.pull_calendar(db, icloud)

    assert server.last_sync_token == "sync-1"


def test_an_updated_event_is_changed_not_duplicated(client, db, provider, icloud, server):
    href = server.add_event(
        "a.ics", vevent("a", "Dentist", "20260803T170000Z", "20260803T180000Z")
    )
    sync_engine.pull_calendar(db, icloud)

    server.resources[href] = (
        '"e2"',
        vevent("a", "Dentist (moved)", "20260803T190000Z", "20260803T200000Z"),
    )
    server.changed = [(href, False)]
    sync_engine.pull_calendar(db, icloud)

    stored = db.query(Event).one()
    assert stored.title == "Dentist (moved)"
    assert stored.start_at == datetime(2026, 8, 3, 19, 0)


def test_a_deleted_resource_removes_the_event(client, db, provider, icloud, server):
    href = server.add_event(
        "a.ics", vevent("a", "Dentist", "20260803T170000Z", "20260803T180000Z")
    )
    sync_engine.pull_calendar(db, icloud)
    assert db.query(Event).count() == 1

    del server.resources[href]
    server.changed = [(href, True)]
    sync_engine.pull_calendar(db, icloud)

    assert db.query(Event).count() == 0


def test_all_day_dates_survive_the_round_trip(client, db, provider, icloud, server):
    """No timezone conversion may happen here, or a birthday drifts a day."""
    server.add_event("b.ics", vallday("b", "Beach trip", "20260801", "20260803"))
    sync_engine.pull_calendar(db, icloud)

    stored = db.query(Event).one()
    assert stored.all_day is True
    assert stored.start_at == datetime(2026, 8, 1, 0, 0)
    assert stored.end_at == datetime(2026, 8, 3, 0, 0)


def test_a_floating_time_is_read_in_the_home_timezone(client, db, provider, icloud, server):
    """A VEVENT with no TZID and no Z means "whatever the clock says here".
    Reading it as UTC would move a 3pm pickup by hours."""
    provider["tz"] = "America/New_York"
    server.add_event("c.ics", vevent("c", "Pickup", "20260803T150000", "20260803T160000"))

    sync_engine.pull_calendar(db, icloud)

    stored = db.query(Event).one()
    assert stored.start_at == datetime(2026, 8, 3, 19, 0), "15:00 EDT is 19:00 UTC"


def test_a_zoned_time_is_converted_to_utc(client, db, provider, icloud, server):
    server.add_event(
        "d.ics",
        vevent("d", "Standup", "20260803T090000", "20260803T093000").replace(
            "DTSTART:", "DTSTART;TZID=America/New_York:"
        ).replace("DTEND:", "DTEND;TZID=America/New_York:"),
    )
    sync_engine.pull_calendar(db, icloud)

    stored = db.query(Event).one()
    assert stored.start_at == datetime(2026, 8, 3, 13, 0)
    assert stored.timezone == "America/New_York"


def test_an_event_with_no_end_still_gets_one(client, db, provider, icloud, server):
    ics = vevent("e", "Reminder", "20260803T170000Z", "20260803T180000Z").replace(
        "DTEND:20260803T180000Z\r\n", ""
    )
    server.add_event("e.ics", ics)
    sync_engine.pull_calendar(db, icloud)

    stored = db.query(Event).one()
    assert stored.end_at == stored.start_at


# ---------------------------- resync and errors ------------------------------


def test_expired_token_resyncs_without_losing_unpushed_local_events(
    client, db, provider, icloud, server
):
    """The most valuable case in the Google suite, and just as true here: a full
    resync clears what iCloud gave us, never what is still queued to go out."""
    server.add_event("a.ics", vevent("a", "Dentist", "20260803T170000Z", "20260803T180000Z"))
    sync_engine.pull_calendar(db, icloud)

    mine = client.post(
        "/api/events",
        json={
            "calendar_id": icloud.id,
            "title": "Mine, not yet pushed",
            "start_at": "2026-08-04T17:00:00Z",
            "end_at": "2026-08-04T18:00:00Z",
        },
    ).json()
    assert db.get(Event, mine["id"]).sync_state == "pending_create"

    server.expire_next_sync_token = True
    server.changed = []
    sync_engine.pull_calendar(db, icloud)

    survivor = db.get(Event, mine["id"])
    assert survivor is not None, "a local edit must never be collateral of a resync"
    assert survivor.sync_state == "pending_create"
    assert db.query(Event).filter(Event.origin == "icloud").count() == 1


def test_a_resync_does_not_touch_another_providers_events(client, db, provider, icloud, server):
    """The delete is scoped by origin, so a Google calendar in the same install is
    untouched by an iCloud resync."""
    other = Event(
        calendar_id=icloud.id,
        google_event_id="from-google",
        title="Google event",
        start_at=datetime(2026, 8, 3, 12),
        end_at=datetime(2026, 8, 3, 13),
        origin="google",
    )
    db.add(other)
    db.commit()

    server.expire_next_sync_token = True
    sync_engine.pull_calendar(db, icloud)

    assert db.get(Event, other.id) is not None


def test_a_disabled_calendar_is_skipped(client, db, provider, icloud, server):
    icloud.sync_enabled = False
    db.commit()
    server.add_event("a.ics", vevent("a", "Dentist", "20260803T170000Z", "20260803T180000Z"))

    assert sync_engine.pull_calendar(db, icloud) == 0
    assert db.query(Event).count() == 0


def test_a_rejected_password_is_recorded_not_raised(client, db, provider, icloud, server):
    server.unauthorized = True

    assert sync_engine.pull_all(db) == 0

    db.refresh(icloud)
    assert "appleid.apple.com" in icloud.sync_error


def test_one_unreadable_event_does_not_stop_the_others(client, db, provider, icloud, server):
    """A single malformed VEVENT must not cost the family the whole sync."""
    server.add_event("bad.ics", "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nEND:VEVENT\r\n")
    server.add_event("ok.ics", vevent("ok", "Dentist", "20260803T170000Z", "20260803T180000Z"))

    sync_engine.pull_calendar(db, icloud)

    assert [e.title for e in db.query(Event)] == ["Dentist"]
