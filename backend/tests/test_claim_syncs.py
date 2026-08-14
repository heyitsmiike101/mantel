"""Claiming a calendar is the same wish as syncing it."""

from datetime import datetime, timedelta

import pytest

from app.models import Calendar, LinkedAccount, User
from app.routers import calendars as calendars_router
from app.services.crypto import encrypt


@pytest.fixture
def synced_calendar(client, db):
    """An account-backed calendar, discovered the way the app discovers them:
    unclaimed and not syncing."""
    user = User(name="Mike", color="#3b82f6")
    db.add(user)
    db.flush()
    account = LinkedAccount(
        user_id=user.id,
        provider="google",
        email="mike@example.com",
        access_token_enc=encrypt("at"),
        refresh_token_enc=encrypt("rt"),
        token_expiry=datetime.utcnow() + timedelta(hours=1),
    )
    db.add(account)
    db.flush()
    cal = Calendar(
        linked_account_id=account.id,
        google_calendar_id="primary",
        name="Mike Google",
        claimed_by_user_id=None,
        sync_enabled=False,
        access_role="owner",
    )
    db.add(cal)
    db.commit()
    return {"calendar_id": cal.id, "user_id": user.id}


def test_claiming_switches_syncing_on(client, synced_calendar):
    r = client.patch(
        f"/api/calendars/{synced_calendar['calendar_id']}",
        json={"claimed_by_user_id": synced_calendar["user_id"]},
    )
    assert r.status_code == 200
    assert r.json()["sync_enabled"] is True, "a claimed calendar that shows no events is a dead end"


def test_unclaiming_switches_syncing_off(client, synced_calendar):
    cid = synced_calendar["calendar_id"]
    client.patch(f"/api/calendars/{cid}", json={"claimed_by_user_id": synced_calendar["user_id"]})

    r = client.patch(f"/api/calendars/{cid}", json={"claimed_by_user_id": None})
    assert r.json()["sync_enabled"] is False


def test_an_explicit_sync_enabled_still_wins(client, synced_calendar):
    """The UI dropped the toggle, but the API keeps it -- a script that means
    'claimed by Mike, and do not sync it' must be obeyed."""
    r = client.patch(
        f"/api/calendars/{synced_calendar['calendar_id']}",
        json={"claimed_by_user_id": synced_calendar["user_id"], "sync_enabled": False},
    )
    assert r.json()["sync_enabled"] is False


def test_a_local_calendar_is_left_alone(client, local_calendar):
    """Local calendars carry sync_enabled=false on purpose; there is nothing to sync
    them with, and flipping it on would be a lie."""
    users = client.post("/api/users", json={"name": "Chrissy"}).json()
    r = client.patch(
        f"/api/calendars/{local_calendar['id']}", json={"claimed_by_user_id": users["id"]}
    )
    assert r.status_code == 200
    assert r.json()["sync_enabled"] is False


def test_claiming_asks_the_pull_loop_to_run_now(client, synced_calendar, monkeypatch):
    """Five minutes is right for background polling and wrong for somebody watching
    the screen after assigning a calendar."""
    called = []
    monkeypatch.setattr(calendars_router, "request_pull", lambda: called.append(True))

    client.patch(
        f"/api/calendars/{synced_calendar['calendar_id']}",
        json={"claimed_by_user_id": synced_calendar["user_id"]},
    )
    assert called == [True]


def test_a_rename_does_not_wake_the_pull_loop(client, synced_calendar, monkeypatch):
    """Only switching syncing on should; otherwise every edit hits Google."""
    cid = synced_calendar["calendar_id"]
    client.patch(f"/api/calendars/{cid}", json={"claimed_by_user_id": synced_calendar["user_id"]})

    called = []
    monkeypatch.setattr(calendars_router, "request_pull", lambda: called.append(True))
    client.patch(f"/api/calendars/{cid}", json={"color_override": "#ff0000"})
    assert called == []
