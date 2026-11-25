from datetime import datetime

from app.models import Calendar, Event, EventHistory, LinkedAccount, User
from app.services import sync_engine
from app.services.providers.base import RemoteEvent, SyncTokenExpired


def create(client, calendar_id, title="Original"):
    response = client.post(
        "/api/events",
        json={
            "calendar_id": calendar_id,
            "title": title,
            "start_at": "2026-08-03T17:00:00Z",
            "end_at": "2026-08-03T18:00:00Z",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def history(client, event_id=None):
    params = {"event_id": event_id} if event_id is not None else {}
    response = client.get("/api/events/history", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def linked(db, provider="google", role="owner", enabled=True):
    user = User(name="Owner")
    db.add(user)
    db.flush()
    account = LinkedAccount(user_id=user.id, provider=provider, email=f"{provider}@example.com")
    db.add(account)
    db.flush()
    calendar = Calendar(
        linked_account_id=account.id,
        google_calendar_id="primary",
        name="Original remote",
        access_role=role,
        sync_enabled=enabled,
    )
    db.add(calendar)
    db.commit()
    return calendar


def remote_event(event_id="remote-1", title="Remote"):
    return RemoteEvent(
        id=event_id,
        etag="etag",
        title=title,
        description="A description",
        location="The park",
        start=datetime(2026, 8, 3, 17),
        end=datetime(2026, 8, 3, 18),
        all_day=False,
        timezone="UTC",
    )


def test_create_edit_delete_history_restores_an_earlier_snapshot(client, local_calendar):
    original = create(client, local_calendar["id"])
    client.patch(f"/api/events/{original['id']}", json={"title": "Edited"})
    client.delete(f"/api/events/{original['id']}")

    entries = history(client, original["id"])
    assert entries["total"] == 4
    assert [entry["action"] for entry in entries["items"]] == [
        "deleted", "updated", "before_update", "created"
    ]
    assert [entry["title"] for entry in entries["items"]] == [
        "Edited", "Edited", "Original", "Original"
    ]
    assert entries["items"][0]["calendar_name"] == "Family"
    assert entries["items"][0]["calendar_source"] == "local"
    assert "google_event_id" not in entries["items"][0]
    page = client.get("/api/events/history", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 4
    assert page["items"][0]["action"] == "updated"

    restored = client.post(
        f"/api/events/history/{entries['items'][2]['id']}/restore", json={}
    )
    assert restored.status_code == 201, restored.text
    assert restored.json()["id"] != original["id"]
    assert restored.json()["title"] == "Original"
    assert restored.json()["sync_state"] == "synced"
    assert history(client, restored.json()["id"])["items"][0]["action"] == "created"


def test_new_event_ids_do_not_reuse_deleted_event_history(client, local_calendar):
    original = create(client, local_calendar["id"])
    client.delete(f"/api/events/{original['id']}")
    replacement = create(client, local_calendar["id"], title="Replacement")
    assert replacement["id"] > original["id"]
    assert [entry["title"] for entry in history(client, original["id"])["items"]] == [
        "Original", "Original"
    ]
    assert [entry["title"] for entry in history(client, replacement["id"])["items"]] == [
        "Replacement"
    ]


def test_restore_and_ordinary_create_keep_distinct_histories(client, local_calendar):
    original = create(client, local_calendar["id"])
    client.delete(f"/api/events/{original['id']}")
    restored = client.post(
        f"/api/events/history/{history(client, original['id'])['items'][0]['id']}/restore",
        json={},
    ).json()
    client.delete(f"/api/events/{restored['id']}")
    replacement = create(client, local_calendar["id"], title="Later")
    assert replacement["id"] > restored["id"]
    assert {entry["title"] for entry in history(client, replacement["id"])["items"]} == {
        "Later"
    }


def test_moving_remote_to_local_keeps_source_and_new_copy_independent(client, db, local_calendar):
    calendar = linked(db)
    original = create(client, calendar.id)
    db.expire_all()
    source = db.get(Event, original["id"])
    source.remote_id = "google-id"
    source.sync_state = "synced"
    db.commit()

    moved = client.patch(
        f"/api/events/{original['id']}", json={"calendar_id": local_calendar["id"]}
    ).json()
    assert moved["id"] != original["id"]
    entries = history(client, original["id"])
    assert entries["items"][0]["action"] == "deleted"
    assert entries["items"][0]["calendar_source"] == "google"
    restored = client.post(f"/api/events/history/{entries['items'][0]['id']}/restore", json={})
    assert restored.status_code == 201, restored.text
    assert restored.json()["id"] not in (moved["id"], original["id"])
    assert restored.json()["sync_state"] == "pending_create"
    db.expire_all()
    assert db.get(Event, restored.json()["id"]).remote_id is None
    assert db.get(Event, original["id"]).sync_state == "pending_delete"
    assert db.get(Event, moved["id"]) is not None


def test_remote_deletion_and_expired_token_preserve_snapshots(client, db, monkeypatch):
    calendar = linked(db)
    sync_engine._apply_remote_event(db, calendar, remote_event())
    db.commit()
    remote = db.query(Event).filter_by(google_event_id="remote-1").one()
    event_id = remote.id
    sync_engine._apply_remote_event(db, calendar, remote_event(title="Changed remotely"))
    db.commit()
    deleted = remote_event()
    deleted.deleted = True
    sync_engine._apply_remote_event(db, calendar, deleted)
    db.commit()
    assert [entry["action"] for entry in history(client, event_id)["items"]] == [
        "deleted", "updated", "before_update", "created"
    ]

    sync_engine._apply_remote_event(db, calendar, remote_event("remote-2"))
    db.commit()
    second_id = db.query(Event).filter_by(google_event_id="remote-2").one().id
    calendar.sync_token = "expired"
    db.commit()

    class Provider:
        def list_events(self, calendar_id, sync_token=None, time_min=None):
            if sync_token:
                raise SyncTokenExpired(410, "expired")
            return [], "fresh"

    monkeypatch.setattr(sync_engine, "provider_factory", lambda db, account: Provider())
    sync_engine.pull_calendar(db, calendar)
    assert db.get(Event, second_id) is None
    assert history(client, second_id)["items"][0]["action"] == "deleted"
    assert history(client, second_id)["items"][0]["calendar_source"] == "google"


def test_cascade_deletes_keep_history_and_require_destination(client, db, local_calendar):
    local = create(client, local_calendar["id"])
    client.delete(f"/api/calendars/{local_calendar['id']}")
    entry = history(client, local["id"])["items"][0]
    assert entry["action"] == "deleted"
    assert client.post(f"/api/events/history/{entry['id']}/restore", json={}).status_code == 400
    destination = client.post("/api/calendars", json={"name": "New home"}).json()["id"]
    assert client.post(f"/api/events/history/{entry['id']}/restore", json={}).status_code == 400
    restored = client.post(
        f"/api/events/history/{entry['id']}/restore", json={"calendar_id": destination}
    )
    assert restored.status_code == 201
    assert restored.json()["calendar_id"] == destination

    remote = linked(db)
    event = create(client, remote.id)
    account_id = remote.linked_account_id
    client.delete(f"/api/accounts/{account_id}")
    assert history(client, event["id"])["items"][0]["action"] == "deleted"


def test_restore_rejects_bad_destinations_without_creating_events(client, db, local_calendar):
    remote = linked(db, role="reader")
    disabled = Calendar(
        linked_account_id=remote.linked_account_id,
        google_calendar_id="disabled",
        name="Disabled",
        sync_enabled=False,
    )
    db.add(disabled)
    db.commit()
    original = create(client, local_calendar["id"])
    snapshot_id = history(client, original["id"])["items"][0]["id"]
    count = db.query(Event).count()
    for calendar_id, expected in ((remote.id, 403), (disabled.id, 400), (9999, 404)):
        response = client.post(
            f"/api/events/history/{snapshot_id}/restore", json={"calendar_id": calendar_id}
        )
        assert response.status_code == expected, response.text
    assert client.post("/api/events/history/9999/restore", json={}).status_code == 404
    db.expire_all()
    assert db.query(Event).count() == count
    assert history(client)["total"] == 1


def test_rolled_back_event_and_snapshot_both_disappear(client, db, local_calendar):
    row = Event(
        calendar_id=local_calendar["id"],
        title="Temporary",
        start_at=datetime(2026, 8, 3, 17),
        end_at=datetime(2026, 8, 3, 18),
    )
    db.add(row)
    db.flush()
    event_id = row.id
    db.rollback()
    assert db.get(Event, event_id) is None
    assert db.query(EventHistory).filter_by(event_id=event_id).count() == 0
