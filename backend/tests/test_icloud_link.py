"""Linking an iCloud account.

A form rather than a consent screen, because Apple has no OAuth for calendars.
That makes the credential check at link time the only chance to tell somebody
their password is wrong while they are still looking at the screen.
"""

import pytest
from fake_caldav import PARTITION_HOST, FakeCalDav

from app.models import Calendar, LinkedAccount, User
from app.services import icloud_auth
from app.services.crypto import decrypt, encrypt


@pytest.fixture
def server():
    return FakeCalDav()


@pytest.fixture
def linking(server, monkeypatch):
    """Route the app's own CalDAV clients at the fake server."""
    real = icloud_auth.CalDavClient

    def build(username, password, base_url=None, http=None):
        return real(username, password, http=http or server.client())

    monkeypatch.setattr(icloud_auth, "CalDavClient", build)
    return server


@pytest.fixture
def user(client, db):
    u = User(name="Mike", color="#3b82f6")
    db.add(u)
    db.commit()
    return u


def link(client, user_id, password="abcd-efgh-ijkl-mnop", apple_id="mike@icloud.com"):
    return client.post(
        "/api/accounts/icloud",
        json={"user_id": user_id, "apple_id": apple_id, "app_password": password},
    )


# --------------------------------- linking -----------------------------------


def test_linking_stores_the_account_and_finds_its_calendars(client, db, linking, user):
    r = link(client, user.id)

    assert r.status_code == 201
    body = r.json()
    assert body["provider"] == "icloud"
    assert body["email"] == "mike@icloud.com"
    assert body["status"] == "active"

    calendars = db.query(Calendar).filter(Calendar.linked_account_id == body["id"]).all()
    assert [c.name for c in calendars] == ["Home"]


def test_new_calendars_arrive_switched_off(client, db, linking, user):
    """Linking an account must never put somebody's events on the wall by itself."""
    link(client, user.id)

    cal = db.query(Calendar).filter(Calendar.linked_account_id.is_not(None)).one()
    assert cal.sync_enabled is False
    assert cal.claimed_by_user_id is None


def test_the_password_is_encrypted_at_rest(client, db, linking, user):
    link(client, user.id, password="abcd-efgh-ijkl-mnop")

    account = db.query(LinkedAccount).one()
    assert account.password_enc
    assert "abcd" not in account.password_enc
    assert decrypt(account.password_enc) == "abcd-efgh-ijkl-mnop"


def test_the_password_is_never_returned(client, db, linking, user):
    body = link(client, user.id).json()
    assert "app_password" not in body
    assert "password_enc" not in body

    listed = client.get("/api/accounts").json()
    assert all("password_enc" not in row for row in listed)


def test_the_calendar_home_is_remembered(client, db, linking, user):
    """So the two-step principal discovery does not run on every sync."""
    link(client, user.id)

    account = db.query(LinkedAccount).one()
    assert account.calendar_home_url == f"{PARTITION_HOST}/1234567890/calendars/"


def test_spaces_in_a_pasted_password_are_forgiven(client, db, linking, user):
    """Apple shows it in dashed groups and people paste it with stray whitespace.
    The dashes are part of the password; the spaces are not."""
    link(client, user.id, password="  abcd-efgh ijkl-mnop  ")

    assert decrypt(db.query(LinkedAccount).one().password_enc) == "abcd-efghijkl-mnop"


def test_an_apple_id_is_matched_case_insensitively(client, db, linking, user):
    link(client, user.id, apple_id="Mike@iCloud.com")
    link(client, user.id, apple_id="mike@icloud.com")

    assert db.query(LinkedAccount).count() == 1, "one Apple ID, one account"


# --------------------------------- failures ----------------------------------


def test_a_wrong_password_is_refused_and_stores_nothing(client, db, linking, user):
    """The whole reason the check happens before the write. A stored-but-broken
    account looks connected and silently never syncs."""
    linking.unauthorized = True

    r = link(client, user.id)

    assert r.status_code == 400
    assert "appleid.apple.com" in r.json()["error"]["message"]
    assert db.query(LinkedAccount).count() == 0, "no half-linked account left behind"


def test_an_unreachable_icloud_is_not_reported_as_a_bad_password(client, db, linking, user):
    """Telling somebody their password is wrong when the network is down sends
    them to regenerate a perfectly good one."""
    import httpx

    def boom(request):
        raise httpx.ConnectError("no route to host")

    linking.handle = boom

    r = link(client, user.id)

    assert r.status_code == 502
    assert db.query(LinkedAccount).count() == 0


def test_an_unknown_user_is_a_404(client, db, linking):
    assert link(client, 999).status_code == 404


def test_an_empty_password_is_refused_without_calling_icloud(client, db, linking, user):
    r = client.post(
        "/api/accounts/icloud",
        json={"user_id": user.id, "apple_id": "mike@icloud.com", "app_password": "   "},
    )

    assert r.status_code == 400
    assert linking.requests == [], "no point asking iCloud about an empty password"


def test_relinking_repairs_an_account_that_needed_reauth(client, db, linking, user):
    """The recovery path after somebody revokes the password at appleid.apple.com."""
    link(client, user.id)
    account = db.query(LinkedAccount).one()
    account.status = "needs_reauth"
    account.last_error = "iCloud rejected the saved app-specific password."
    db.commit()

    r = link(client, user.id, password="new-pass-word-here")

    assert r.status_code == 201
    db.refresh(account)
    assert account.status == "active"
    assert account.last_error is None
    assert decrypt(account.password_enc) == "new-pass-word-here"


# --------------------------------- unlinking ---------------------------------


def test_unlinking_removes_the_calendars_without_touching_icloud(client, db, linking, user):
    account_id = link(client, user.id).json()["id"]
    assert db.query(Calendar).filter(Calendar.linked_account_id.is_not(None)).count() == 1

    assert client.delete(f"/api/accounts/{account_id}").status_code == 204

    assert db.query(LinkedAccount).count() == 0
    assert db.query(Calendar).filter(Calendar.linked_account_id.is_not(None)).count() == 0
    assert linking.deletes == [], "nothing is deleted from the account itself"


def test_unlinking_icloud_does_not_try_to_revoke_a_google_token(
    client, db, linking, user, monkeypatch
):
    """`revoke` posts to Google's endpoint; calling it for an Apple ID would be a
    pointless request with somebody's credentials attached."""
    from app.services import google_oauth

    called = []
    monkeypatch.setattr(google_oauth, "revoke", lambda account: called.append(account))

    account_id = link(client, user.id).json()["id"]
    client.delete(f"/api/accounts/{account_id}")

    assert called == []


# ------------------------------- sync status ---------------------------------


def test_sync_status_reports_a_linked_icloud_account(client, db, linking, user):
    assert client.get("/api/sync/status").json()["icloud_linked"] is False

    link(client, user.id)

    assert client.get("/api/sync/status").json()["icloud_linked"] is True


def test_a_broken_icloud_account_shows_up_as_needing_attention(client, db, linking, user):
    """The same list Google accounts use, so one banner covers both."""
    link(client, user.id)
    account = db.query(LinkedAccount).one()
    account.status = "needs_reauth"
    db.commit()

    status = client.get("/api/sync/status").json()
    assert status["accounts_needing_reauth"] == ["mike@icloud.com"]


# --------------------------------- messages ----------------------------------


def test_a_read_only_icloud_calendar_says_so_by_name(client, db, linking, user):
    """It used to say "read-only in Google" whatever the calendar actually was."""
    account = LinkedAccount(
        user_id=user.id, provider="icloud", email="x@icloud.com", password_enc=encrypt("p")
    )
    db.add(account)
    db.flush()
    cal = Calendar(
        linked_account_id=account.id,
        google_calendar_id="/x/calendars/shared/",
        name="Shared",
        access_role="reader",
    )
    db.add(cal)
    db.commit()

    r = client.post(
        "/api/events",
        json={
            "calendar_id": cal.id,
            "title": "Nope",
            "start_at": "2026-08-03T17:00:00Z",
            "end_at": "2026-08-03T18:00:00Z",
        },
    )

    assert r.status_code == 403
    assert "read-only in iCloud" in r.json()["error"]["message"]
