"""Changing an event's calendar.

Providers cannot move a resource between calendars or accounts, so a move is a create on
the target plus a delete on the source. These tests drive both transport fakes at once --
Google for the source, CalDAV for the target -- because the interesting failures are in
the hand-off between them.
"""

from datetime import datetime

import pytest
from fake_caldav import CALENDAR, PARTITION_HOST, FakeCalDav
from fake_google import FakeGoogle, gevent
from icalendar import Calendar as ICalendar

from app.models import Calendar, Event, LinkedAccount, User
from app.services import sync_engine
from app.services.caldav_client import CalDavClient
from app.services.crypto import encrypt
from app.services.providers.google import GoogleProvider
from app.services.providers.icloud import ICloudProvider


@pytest.fixture
def google():
    return FakeGoogle()


@pytest.fixture
def caldav():
    return FakeCalDav()


@pytest.fixture(autouse=True)
def providers(google, caldav, monkeypatch):
    def build(db, account):
        if account.provider == "google":
            return GoogleProvider(client=google)
        dav = CalDavClient("someone@icloud.com", "pw", http=caldav.client())
        return ICloudProvider(dav, f"{PARTITION_HOST}/1234567890/calendars/", "UTC")

    monkeypatch.setattr(sync_engine, "provider_factory", build)


@pytest.fixture
def setup(client, db):
    user = User(name="Mike", color="#3b82f6")
    db.add(user)
    db.flush()
    g_account = LinkedAccount(
        user_id=user.id,
        provider="google",
        email="mike@example.com",
        access_token_enc=encrypt("at"),
        refresh_token_enc=encrypt("rt"),
        token_expiry=datetime(2030, 1, 1),
    )
    i_account = LinkedAccount(
        user_id=user.id,
        provider="icloud",
        email="mike@icloud.com",
        password_enc=encrypt("pw"),
        calendar_home_url=f"{PARTITION_HOST}/1234567890/calendars/",
    )
    db.add_all([g_account, i_account])
    db.flush()

    def cal(account, remote_id, name, role="owner", sync=True):
        return Calendar(
            linked_account_id=account.id,
            google_calendar_id=remote_id,
            name=name,
            claimed_by_user_id=user.id,
            sync_enabled=sync,
            access_role=role,
        )

    cals = {
        "google": cal(g_account, "primary", "Mike Google"),
        "icloud": cal(i_account, CALENDAR, "Home"),
        "readonly": cal(i_account, "/1234567890/calendars/shared/", "Shared", role="reader"),
        "off": cal(i_account, "/1234567890/calendars/off/", "Off", sync=False),
    }
    db.add_all(cals.values())
    db.commit()
    return {name: c.id for name, c in cals.items()}


def push(db):
    # The API wrote through its own session; expire so this one sees the same truth the
    # real push loop (a fresh session) would.
    db.expire_all()
    return sync_engine.push_pending(db)


def new_event(client, calendar_id, **overrides):
    payload = {
        "calendar_id": calendar_id,
        "title": "Soccer practice",
        "start_at": "2026-08-03T17:00:00Z",
        "end_at": "2026-08-03T18:30:00Z",
        "description": "Bring shin guards",
        "location": "Riverside Park",
    }
    payload.update(overrides)
    r = client.post("/api/events", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def events_in_august(client):
    return client.get(
        "/api/events", params={"start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}
    ).json()


def test_moving_a_local_event_to_another_local_calendar_replaces_the_row(client, local_calendar):
    other = client.post("/api/calendars", json={"name": "Chores"}).json()
    ev = new_event(client, local_calendar["id"], recurrence_rule="FREQ=WEEKLY;COUNT=3")

    r = client.patch(f"/api/events/{ev['id']}", json={"calendar_id": other["id"]})

    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["id"] != ev["id"], "a move is a create plus a delete, so the id changes"
    assert moved["calendar_id"] == other["id"]
    assert (moved["title"], moved["description"], moved["location"]) == (
        "Soccer practice",
        "Bring shin guards",
        "Riverside Park",
    )
    assert moved["recurrence_rule"] == "FREQ=WEEKLY;COUNT=3"
    assert moved["sync_state"] == "synced"
    assert client.get(f"/api/events/{ev['id']}").status_code == 404


def test_other_changes_in_the_same_patch_land_on_the_moved_event(client, local_calendar):
    other = client.post("/api/calendars", json={"name": "Chores"}).json()
    ev = new_event(client, local_calendar["id"])

    moved = client.patch(
        f"/api/events/{ev['id']}", json={"calendar_id": other["id"], "title": "Practice"}
    ).json()

    assert moved["title"] == "Practice"
    assert moved["location"] == "Riverside Park"


def test_moving_a_pushed_google_event_to_icloud_deletes_upstream_and_creates_there(
    client, db, setup, google, caldav
):
    ev = new_event(client, setup["google"])
    push(db)
    assert [i["id"] for i in google.inserted] == ["g1"]

    moved = client.patch(f"/api/events/{ev['id']}", json={"calendar_id": setup["icloud"]}).json()
    assert moved["sync_state"] == "pending_create"
    assert moved["calendar_id"] == setup["icloud"]

    assert push(db) == 2

    assert google.deleted == ["g1"]
    assert len(caldav.puts) == 1
    path, body = caldav.puts[0]
    assert path.startswith(CALENDAR)
    vevent = next(iter(ICalendar.from_ical(body).walk("VEVENT")))
    assert str(vevent["SUMMARY"]) == "Soccer practice"
    assert str(vevent["LOCATION"]) == "Riverside Park"

    rows = db.query(Event).all()
    assert len(rows) == 1, "the old row must be gone once its upstream delete has gone through"
    assert rows[0].calendar_id == setup["icloud"]
    assert rows[0].sync_state == "synced"
    assert rows[0].remote_id.endswith(".ics")


def test_moving_an_event_that_was_never_pushed_deletes_nothing_upstream(
    client, db, setup, google, caldav
):
    ev = new_event(client, setup["google"])  # still pending_create, no remote id

    client.patch(f"/api/events/{ev['id']}", json={"calendar_id": setup["icloud"]})

    assert db.query(Event).count() == 1, "the unpushed original is dropped outright"
    push(db)
    assert google.deleted == [] and google.inserted == []
    assert len(caldav.puts) == 1


def test_a_failed_create_push_keeps_the_moved_event_queued_for_retry(
    client, db, setup, google, caldav
):
    ev = new_event(client, setup["google"])
    push(db)
    client.patch(f"/api/events/{ev['id']}", json={"calendar_id": setup["icloud"]})
    caldav.fail_put_with = 500

    push(db)

    pending = db.query(Event).filter(Event.sync_state == "pending_create").all()
    assert len(pending) == 1, "a failed create must not lose the event"
    push(db)
    assert len(caldav.puts) == 1
    assert db.query(Event).filter(Event.sync_state == "synced").count() == 1


def test_a_pull_of_the_source_before_the_push_does_not_bring_the_old_event_back(
    client, db, setup, google
):
    ev = new_event(client, setup["google"])
    push(db)
    client.patch(f"/api/events/{ev['id']}", json={"calendar_id": setup["icloud"]})

    # Google still has the event, because the delete has not been pushed yet.
    google.pages = [
        ([gevent("g1", "Soccer practice", "2026-08-03T17:00:00Z", "2026-08-03T18:30:00Z")], "tok")
    ]
    db.expire_all()
    sync_engine.pull_calendar(db, db.get(Calendar, setup["google"]))

    listed = events_in_august(client)
    assert [e["calendar_id"] for e in listed] == [setup["icloud"]]


def test_cannot_move_to_a_read_only_calendar(client, setup):
    ev = new_event(client, setup["google"])

    r = client.patch(f"/api/events/{ev['id']}", json={"calendar_id": setup["readonly"]})

    assert r.status_code == 403
    assert "read-only in iCloud" in r.json()["error"]["message"]
    assert client.get(f"/api/events/{ev['id']}").json()["calendar_id"] == setup["google"]


def test_cannot_move_to_a_synced_calendar_with_syncing_off(client, setup):
    ev = new_event(client, setup["google"])

    r = client.patch(f"/api/events/{ev['id']}", json={"calendar_id": setup["off"]})

    assert r.status_code == 400
    assert "Off" in r.json()["error"]["message"]


def test_cannot_move_to_a_calendar_that_does_not_exist(client, setup):
    ev = new_event(client, setup["google"])
    r = client.patch(f"/api/events/{ev['id']}", json={"calendar_id": 9999})
    assert r.status_code == 404


def test_cannot_move_one_occurrence_of_a_series(client, db, setup):
    occurrence = Event(
        calendar_id=setup["google"],
        remote_id="series_20260803",
        recurring_event_id="series",
        title="Soccer practice",
        start_at=datetime(2026, 8, 3, 17),
        end_at=datetime(2026, 8, 3, 18),
        origin="google",
        sync_state="synced",
    )
    db.add(occurrence)
    db.commit()

    r = client.patch(f"/api/events/{occurrence.id}", json={"calendar_id": setup["icloud"]})

    assert r.status_code == 400
    assert "whole series" in r.json()["error"]["message"]
    db.expire_all()
    assert db.get(Event, occurrence.id).calendar_id == setup["google"]


def test_a_series_master_moves_with_its_rule_and_exclusions(client, db, setup):
    ev = new_event(client, setup["icloud"], recurrence_rule="FREQ=WEEKLY;COUNT=4")
    row = db.get(Event, ev["id"])
    row.exdates = "2026-08-10T17:00:00"
    db.commit()

    moved = client.patch(f"/api/events/{ev['id']}", json={"calendar_id": setup["google"]}).json()

    assert moved["recurrence_rule"] == "FREQ=WEEKLY;COUNT=4"
    db.expire_all()
    assert db.get(Event, moved["id"]).exdates == "2026-08-10T17:00:00"
