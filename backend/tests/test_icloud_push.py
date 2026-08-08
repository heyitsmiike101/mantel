"""Pushing local changes to iCloud.

Mirrors `test_google_push.py`, plus the things CalDAV makes possible that the
Google API does not: writing over somebody else's change, and a resource that
holds a whole series.
"""

from datetime import datetime

import httpx
import pytest
from fake_caldav import CALENDAR, PARTITION_HOST, FakeCalDav, vevent
from icalendar import Calendar as ICalendar

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
    def build(db, account):
        dav = CalDavClient("someone@icloud.com", "pw", http=server.client())
        return ICloudProvider(dav, f"{PARTITION_HOST}/1234567890/calendars/", "UTC")

    monkeypatch.setattr(sync_engine, "provider_factory", build)


@pytest.fixture
def setup(client, db, provider):
    user = User(name="Mike", color="#3b82f6")
    db.add(user)
    db.flush()
    account = LinkedAccount(
        user_id=user.id,
        provider="icloud",
        email="mike@icloud.com",
        password_enc=encrypt("pw"),
        calendar_home_url=f"{PARTITION_HOST}/1234567890/calendars/",
    )
    db.add(account)
    db.flush()
    writable = Calendar(
        linked_account_id=account.id,
        google_calendar_id=CALENDAR,
        name="Home",
        claimed_by_user_id=user.id,
        sync_enabled=True,
        access_role="writer",
    )
    readonly = Calendar(
        linked_account_id=account.id,
        google_calendar_id="/1234567890/calendars/shared/",
        name="Shared",
        claimed_by_user_id=user.id,
        sync_enabled=True,
        access_role="reader",
    )
    db.add_all([writable, readonly])
    db.commit()
    return {"cal": writable, "readonly": readonly, "account": account}


def push(db):
    """Drain the queue the way the scheduler does.

    The API writes through its own session, so anything this test session already
    loaded is stale by the time we get here. The real push loop runs in a fresh
    session and sees the truth; expiring first gives this one the same view,
    instead of quietly re-committing the values it read before the request.
    """
    db.expire_all()
    return sync_engine.push_pending(db)


def new_event(client, calendar_id, **overrides):
    payload = {
        "calendar_id": calendar_id,
        "title": "Soccer practice",
        "start_at": "2026-08-03T17:00:00Z",
        "end_at": "2026-08-03T18:30:00Z",
    }
    payload.update(overrides)
    return client.post("/api/events", json=payload)


def vevent_of(server, index=-1):
    return next(iter(ICalendar.from_ical(server.puts[index][1]).walk("VEVENT")))


# --------------------------------- create ------------------------------------


def test_creating_queues_and_then_writes_a_resource(client, db, setup, server):
    ev = new_event(client, setup["cal"].id).json()
    assert ev["sync_state"] == "pending_create"

    assert push(db) == 1

    assert len(server.puts) == 1
    path, _ = server.puts[0]
    assert path.startswith(CALENDAR) and path.endswith(".ics")

    component = vevent_of(server)
    assert str(component["SUMMARY"]) == "Soccer practice"
    assert component["DTSTART"].dt == datetime.fromisoformat("2026-08-03T17:00:00+00:00")

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.sync_state == "synced"
    assert stored.remote_id.endswith(".ics")
    assert stored.remote_etag == '"v1"'


def test_the_uid_matches_the_filename(client, db, setup, server):
    new_event(client, setup["cal"].id)
    push(db)

    path, _ = server.puts[0]
    assert str(vevent_of(server)["UID"]) == path.rsplit("/", 1)[-1].removesuffix(".ics")


def test_an_all_day_event_is_written_as_dates(client, db, setup, server):
    new_event(
        client,
        setup["cal"].id,
        title="Beach trip",
        all_day=True,
        start_at="2026-08-01T00:00:00Z",
        end_at="2026-08-03T00:00:00Z",
    )
    push(db)

    component = vevent_of(server)
    assert component["DTSTART"].dt.isoformat() == "2026-08-01"
    assert component["DTEND"].dt.isoformat() == "2026-08-03"


def test_a_series_is_written_as_one_rrule_and_stays_expanded_here(client, db, setup, server):
    """Unlike Google, iCloud does not expand. Our master must keep being drawn."""
    ev = new_event(client, setup["cal"].id, recurrence_rule="FREQ=WEEKLY;COUNT=4").json()
    push(db)

    assert "FREQ=WEEKLY" in vevent_of(server)["RRULE"].to_ical().decode()

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.is_master is False, "nothing else will draw this series"
    assert len(client.get("/api/events", params={
        "start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}).json()) == 4


def test_a_put_without_an_etag_is_followed_by_a_read(client, db, setup, server):
    """Leaving the etag unset would make every later update send a stale If-Match."""
    server.omit_etag_on_put = True
    ev = new_event(client, setup["cal"].id).json()

    push(db)

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.remote_etag == '"v1"', "read back from the server after the PUT"


# --------------------------------- update ------------------------------------


def test_an_edit_preserves_properties_this_app_does_not_model(client, db, setup, server):
    """The reason an update reads before it writes. Renaming an event on the wall
    display must not delete the alarm somebody set on their phone."""
    href = server.add_event(
        "phone.ics",
        vevent(
            "phone-uid",
            "Dentist",
            "20260803T170000Z",
            "20260803T180000Z",
            extra="BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT30M\r\nEND:VALARM\r\n"
            "CATEGORIES:Health\r\n",
        ),
    )
    sync_engine.pull_calendar(db, setup["cal"])
    stored = db.query(Event).one()

    client.patch(f"/api/events/{stored.id}", json={"title": "Dentist (moved)"})
    push(db)

    written = server.resources[href][1]
    assert "SUMMARY:Dentist (moved)" in written
    assert "BEGIN:VALARM" in written, "the alarm must survive an edit made here"
    assert "CATEGORIES:Health" in written
    assert "UID:phone-uid" in written, "the original UID must not be replaced"


def test_a_stale_etag_is_retried_once_with_a_fresh_read(client, db, setup, server):
    """Somebody changed it between our read and our write. This app is last-write-
    wins everywhere else, so the edit goes through rather than being lost."""
    server.add_event(
        "phone.ics", vevent("phone-uid", "Dentist", "20260803T170000Z", "20260803T180000Z")
    )
    sync_engine.pull_calendar(db, setup["cal"])
    stored = db.query(Event).one()

    client.patch(f"/api/events/{stored.id}", json={"title": "Renamed"})
    server.fail_put_with = 412
    push(db)

    db.refresh(stored)
    assert stored.sync_state == "synced"
    assert "SUMMARY:Renamed" in server.resources["/1234567890/calendars/home/phone.ics"][1]


def test_a_persistent_conflict_keeps_the_event_queued(client, db, setup, server, monkeypatch):
    """One retry, not a spin. The push loop tries again on its own schedule."""
    server.add_event(
        "phone.ics", vevent("phone-uid", "Dentist", "20260803T170000Z", "20260803T180000Z")
    )
    sync_engine.pull_calendar(db, setup["cal"])
    stored = db.query(Event).one()
    client.patch(f"/api/events/{stored.id}", json={"title": "Renamed"})

    original = server._put
    monkeypatch.setattr(
        server, "_put", lambda request, path: httpx.Response(412, text="conflict")
    )
    assert push(db) == 0

    db.refresh(stored)
    assert stored.sync_state == "pending_update", "must retry on the next pass"
    monkeypatch.setattr(server, "_put", original)


def test_an_event_deleted_upstream_is_recreated_not_lost(client, db, setup, server):
    server.add_event(
        "phone.ics", vevent("phone-uid", "Dentist", "20260803T170000Z", "20260803T180000Z")
    )
    sync_engine.pull_calendar(db, setup["cal"])
    stored = db.query(Event).one()
    client.patch(f"/api/events/{stored.id}", json={"title": "Still happening"})

    del server.resources["/1234567890/calendars/home/phone.ics"]
    push(db)

    db.refresh(stored)
    assert stored.sync_state == "synced"
    assert stored.remote_id != "phone.ics", "recreated under a new name"
    assert len(server.puts) == 1


# --------------------------------- delete ------------------------------------


def test_deleting_removes_the_resource(client, db, setup, server):
    ev = new_event(client, setup["cal"].id).json()
    push(db)
    path = server.puts[0][0]

    client.delete(f"/api/events/{ev['id']}")
    assert db.get(Event, ev["id"]).sync_state == "pending_delete"

    push(db)
    assert server.deletes == [path]
    assert db.get(Event, ev["id"]) is None


def test_deleting_something_already_gone_still_succeeds(client, db, setup, server):
    ev = new_event(client, setup["cal"].id).json()
    push(db)
    server.resources.clear()

    client.delete(f"/api/events/{ev['id']}")
    push(db)

    assert db.get(Event, ev["id"]) is None, "already gone upstream is a success"


def test_deleting_one_occurrence_excludes_it_without_cancelling_the_series(
    client, db, setup, server
):
    """The dangerous case. Removing the resource here would silently cancel every
    remaining week of a series somebody still relies on."""
    href = server.add_event(
        "swim.ics",
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:swim\r\nSUMMARY:Swimming\r\n"
        "DTSTART:20260803T170000Z\r\nDTEND:20260803T180000Z\r\n"
        "DTSTAMP:20260730T100000Z\r\nRRULE:FREQ=WEEKLY;COUNT=4\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\nUID:swim\r\nRECURRENCE-ID:20260810T170000Z\r\n"
        "SUMMARY:Swimming (late)\r\nDTSTART:20260810T190000Z\r\n"
        "DTEND:20260810T200000Z\r\nDTSTAMP:20260730T100000Z\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n",
    )
    sync_engine.pull_calendar(db, setup["cal"])
    moved = db.query(Event).filter(Event.google_event_id.like("%#%")).one()

    client.delete(f"/api/events/{moved.id}")
    push(db)

    assert server.deletes == [], "the series resource must survive"
    written = server.resources[href][1]
    assert "RECURRENCE-ID" not in written, "the moved copy is gone"
    assert "EXDATE" in written and "20260810T170000Z" in written
    assert "RRULE:FREQ=WEEKLY;COUNT=4" in written, "the rest of the series is untouched"


# ------------------------------ read-only ------------------------------------


def test_a_read_only_calendar_refuses_writes(client, setup):
    r = new_event(client, setup["readonly"].id)
    assert r.status_code == 403
    assert "read-only" in r.json()["error"]["message"]


def test_a_failed_push_records_the_error_and_stays_queued(client, db, setup, server):
    ev = new_event(client, setup["cal"].id).json()
    server.fail_put_with = 507

    assert push(db) == 0

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.sync_state == "pending_create"
    db.refresh(setup["cal"])
    assert setup["cal"].sync_error
