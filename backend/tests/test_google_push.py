from datetime import datetime, timedelta

import pytest
from fake_google import FakeGoogle, gevent

from app.models import Calendar, Event, LinkedAccount, User
from app.services import google_sync
from app.services.crypto import encrypt


@pytest.fixture
def fake(monkeypatch):
    f = FakeGoogle()
    monkeypatch.setattr(google_sync, "client_factory", f)
    monkeypatch.setattr(google_sync, "access_token_for", lambda db, account: "fake-token")
    return f


@pytest.fixture
def setup(client, db, fake):
    user = User(name="Mike", color="#3b82f6")
    db.add(user)
    db.flush()
    account = LinkedAccount(
        user_id=user.id,
        provider="google",
        email="mike@example.com",
        access_token_enc=encrypt("at"),
        refresh_token_enc=encrypt("rt"),
        token_expiry=datetime(2030, 1, 1),
    )
    db.add(account)
    db.flush()
    writable = Calendar(
        linked_account_id=account.id,
        google_calendar_id="primary",
        name="Mike Google",
        claimed_by_user_id=user.id,
        sync_enabled=True,
        access_role="owner",
    )
    readonly = Calendar(
        linked_account_id=account.id,
        google_calendar_id="holidays",
        name="Holidays",
        claimed_by_user_id=user.id,
        sync_enabled=True,
        access_role="reader",
    )
    db.add_all([writable, readonly])
    db.commit()
    return {"user": user, "account": account, "cal": writable, "readonly": readonly}


def new_event(client, calendar_id, title="Soccer practice"):
    return client.post(
        "/api/events",
        json={
            "calendar_id": calendar_id,
            "title": title,
            "start_at": "2026-08-03T17:00:00Z",
            "end_at": "2026-08-03T18:30:00Z",
        },
    )


# ------------------------------- queueing ------------------------------------


def test_creating_on_a_google_calendar_queues_a_push(client, db, setup):
    ev = new_event(client, setup["cal"].id).json()
    assert ev["sync_state"] == "pending_create"
    assert ev["editable"] is True


def test_editing_a_synced_event_queues_an_update(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    google_sync.push_pending(db)

    updated = client.patch(f"/api/events/{ev['id']}", json={"title": "Soccer game"}).json()
    assert updated["sync_state"] == "pending_update"


def test_editing_an_uncreated_event_stays_pending_create(client, db, setup):
    """An event that never reached Google must still be inserted, not patched."""
    ev = new_event(client, setup["cal"].id).json()
    updated = client.patch(f"/api/events/{ev['id']}", json={"title": "Renamed"}).json()
    assert updated["sync_state"] == "pending_create"


def test_local_calendar_events_are_never_queued(client, local_calendar):
    ev = new_event(client, local_calendar["id"]).json()
    assert ev["sync_state"] == "synced"


# --------------------------------- push --------------------------------------


def test_push_creates_event_in_google_and_stores_its_id(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    assert google_sync.push_pending(db) == 1

    assert len(fake.inserted) == 1
    sent = fake.inserted[0]
    assert sent["calendar_id"] == "primary"
    assert sent["body"]["summary"] == "Soccer practice"
    assert sent["body"]["start"]["dateTime"].startswith("2026-08-03T17:00:00")

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.google_event_id == "g1"
    assert stored.sync_state == "synced"


def test_push_patches_an_edited_event(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    google_sync.push_pending(db)
    client.patch(f"/api/events/{ev['id']}", json={"title": "Soccer game", "location": "Field 3"})
    google_sync.push_pending(db)

    assert len(fake.patched) == 1
    event_id, body = fake.patched[0]
    assert event_id == "g1"
    assert body["summary"] == "Soccer game"
    assert body["location"] == "Field 3"


def test_push_deletes_remotely_then_locally(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    google_sync.push_pending(db)

    client.delete(f"/api/events/{ev['id']}")
    assert db.get(Event, ev["id"]).sync_state == "pending_delete"
    assert client.get(f"/api/events/{ev['id']}").status_code == 200

    google_sync.push_pending(db)
    assert fake.deleted == ["g1"]
    assert db.get(Event, ev["id"]) is None


def test_delete_of_event_google_already_lost_still_succeeds(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    google_sync.push_pending(db)
    client.delete(f"/api/events/{ev['id']}")

    fake.fail_delete_with = 404
    google_sync.push_pending(db)
    assert db.get(Event, ev["id"]) is None, "an event already gone in Google is simply removed"


def test_patch_on_a_remotely_deleted_event_recreates_it(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    google_sync.push_pending(db)
    client.patch(f"/api/events/{ev['id']}", json={"title": "Still happening"})

    fake.fail_patch_with = 404
    google_sync.push_pending(db)

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.sync_state == "synced"
    assert stored.google_event_id == "g2", "recreated rather than silently lost"
    assert len(fake.inserted) == 2


def test_push_failure_records_error_and_keeps_the_event_queued(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    fake.fail_patch_with = None

    def boom(calendar_id, body):
        from app.services.google_api import GoogleApiError

        raise GoogleApiError(500, "Google is down")

    fake.insert_event = boom
    assert google_sync.push_pending(db) == 0

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.sync_state == "pending_create", "must retry on the next pass"
    db.refresh(setup["cal"])
    assert "Google is down" in setup["cal"].sync_error


def test_all_day_event_pushes_as_dates_not_times(client, db, setup, fake):
    client.post(
        "/api/events",
        json={
            "calendar_id": setup["cal"].id,
            "title": "Beach trip",
            "all_day": True,
            "start_at": "2026-08-01T00:00:00Z",
            "end_at": "2026-08-03T00:00:00Z",
        },
    )
    google_sync.push_pending(db)

    body = fake.inserted[0]["body"]
    assert body["start"] == {"date": "2026-08-01"}
    assert body["end"] == {"date": "2026-08-03"}


# ------------------------- read-only calendars --------------------------------


def test_cannot_create_on_a_read_only_calendar(client, setup):
    r = new_event(client, setup["readonly"].id)
    assert r.status_code == 403
    assert "read-only" in r.json()["error"]["message"]


def test_cannot_edit_or_delete_a_read_only_event(client, db, setup, fake):
    ev = Event(
        calendar_id=setup["readonly"].id,
        google_event_id="ext1",
        title="Company holiday",
        start_at=datetime(2026, 8, 3, 12),
        end_at=datetime(2026, 8, 3, 13),
        origin="google",
    )
    db.add(ev)
    db.commit()

    assert client.patch(f"/api/events/{ev.id}", json={"title": "nope"}).status_code == 403
    assert client.delete(f"/api/events/{ev.id}").status_code == 403
    assert client.get(f"/api/events/{ev.id}").json()["editable"] is False


# --------------------------- conflict resolution ------------------------------


def test_remote_change_does_not_clobber_an_unpushed_local_edit(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    google_sync.push_pending(db)
    client.patch(f"/api/events/{ev['id']}", json={"title": "Local wins"})

    # Google reports an older version while our edit is still queued.
    fake.pages = [
        (
            [
                gevent(
                    "g1",
                    "Remote is stale",
                    "2026-08-03T17:00:00Z",
                    "2026-08-03T18:30:00Z",
                    updated="2020-01-01T00:00:00Z",
                )
            ],
            "t1",
        )
    ]
    google_sync.pull_calendar(db, setup["cal"])

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.title == "Local wins"
    assert stored.sync_state == "pending_update"


def test_newer_remote_change_wins_over_a_stale_local_edit(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    google_sync.push_pending(db)
    client.patch(f"/api/events/{ev['id']}", json={"title": "Local edit"})

    stored = db.get(Event, ev["id"])
    stored.local_updated_at = datetime.utcnow() - timedelta(hours=2)
    db.commit()

    fake.pages = [
        (
            [
                gevent(
                    "g1",
                    "Remote is newer",
                    "2026-08-03T19:00:00Z",
                    "2026-08-03T20:00:00Z",
                    updated=datetime.utcnow().isoformat() + "Z",
                )
            ],
            "t1",
        )
    ]
    google_sync.pull_calendar(db, setup["cal"])

    db.refresh(stored)
    assert stored.title == "Remote is newer"
    assert stored.sync_state == "synced"


def test_sync_status_reports_pending_and_errors(client, db, setup, fake):
    new_event(client, setup["cal"].id)
    body = client.get("/api/sync/status").json()
    assert body["pending_pushes"] == 1
    assert {c["name"] for c in body["calendars"]} == {"Mike Google", "Holidays"}


def test_sync_run_endpoint_pushes_then_pulls(client, db, setup, fake):
    new_event(client, setup["cal"].id)
    fake.pages = [([], "t1"), ([], "t2")]
    body = client.post("/api/sync/run").json()
    assert body["pushed"] == 1
    assert len(fake.inserted) == 1


# --------------------------- recurring events --------------------------------


def test_recurring_event_pushes_an_rrule(client, db, setup, fake):
    client.post(
        "/api/events",
        json={
            "calendar_id": setup["cal"].id,
            "title": "Weekly sync",
            "start_at": "2026-08-03T13:00:00Z",
            "end_at": "2026-08-03T13:30:00Z",
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO",
        },
    )
    google_sync.push_pending(db)

    body = fake.inserted[0]["body"]
    assert body["recurrence"] == ["RRULE:FREQ=WEEKLY;BYDAY=MO"]


def test_pushed_series_stops_being_expanded_locally(client, db, setup, fake):
    """The duplication trap: our pull asks Google for expanded instances, so once
    Google owns the series our own master must disappear from queries or every
    occurrence would render twice."""
    ev = client.post(
        "/api/events",
        json={
            "calendar_id": setup["cal"].id,
            "title": "Weekly sync",
            "start_at": "2026-08-03T13:00:00Z",
            "end_at": "2026-08-03T13:30:00Z",
            "recurrence_rule": "FREQ=WEEKLY;COUNT=4",
        },
    ).json()

    params = {"start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}
    before = client.get("/api/events", params=params).json()
    assert len(before) == 4, "expanded locally while it is still ours"

    google_sync.push_pending(db)

    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.is_master is True

    after = client.get("/api/events", params=params).json()
    assert after == [], "Google's instances are now the only source"


def test_single_events_never_become_masters(client, db, setup, fake):
    ev = new_event(client, setup["cal"].id).json()
    google_sync.push_pending(db)
    stored = db.get(Event, ev["id"])
    db.refresh(stored)
    assert stored.is_master is False


def test_local_recurring_events_are_never_masters(client, db, local_calendar):
    """Nothing pushes a local calendar anywhere, so it keeps expanding forever."""
    ev = client.post(
        "/api/events",
        json={
            "calendar_id": local_calendar["id"],
            "title": "Chores",
            "start_at": "2026-08-03T13:00:00Z",
            "end_at": "2026-08-03T13:30:00Z",
            "recurrence_rule": "FREQ=DAILY;COUNT=3",
        },
    ).json()
    assert ev["sync_state"] == "synced"
    listed = client.get(
        "/api/events", params={"start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}
    ).json()
    assert len(listed) == 3
