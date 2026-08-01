"""Google credentials live in the database, not .env.

A self-hoster must be able to finish setup in the browser; the secret must never
come back out of a no-auth LAN endpoint.
"""

from app.models import AppSetting
from app.services import google_config, google_oauth


def configure(client, **overrides):
    body = {
        "google_client_id": "1234-abc.apps.googleusercontent.com",
        "google_client_secret": "GOCSPX-supersecret",
        "public_base_url": "http://192.168.1.50:8080",
        **overrides,
    }
    return client.patch("/api/settings", json=body)


# ------------------------------- storage -------------------------------------


def test_credentials_round_trip_through_settings(client, db):
    assert client.get("/api/settings").json()["server"]["google_configured"] is False

    configure(client)
    body = client.get("/api/settings").json()

    assert body["google_client_id"] == "1234-abc.apps.googleusercontent.com"
    assert body["public_base_url"] == "http://192.168.1.50:8080"
    assert body["server"]["google_configured"] is True
    assert body["server"]["google_client_secret_set"] is True


def test_the_secret_is_never_returned(client, db):
    """It is write-only. This endpoint has no authentication."""
    configure(client)
    body = client.get("/api/settings").json()
    assert body["google_client_secret"] == ""
    assert "supersecret" not in str(body)


def test_the_secret_is_encrypted_at_rest(client, db):
    configure(client)
    raw = db.get(AppSetting, "google_client_secret").value["value"]
    assert raw and "supersecret" not in raw, "must not be stored in the clear"
    assert google_config.load(db).client_secret == "GOCSPX-supersecret"


def test_an_empty_secret_leaves_the_stored_one_alone(client, db):
    """The settings form posts every field; a blank box must not wipe a secret
    the user never touched."""
    configure(client)
    client.patch("/api/settings", json={"google_client_secret": ""})
    assert google_config.load(db).client_secret == "GOCSPX-supersecret"
    assert client.get("/api/settings").json()["server"]["google_configured"] is True


def test_the_home_assistant_token_is_also_write_only(client, db):
    client.patch("/api/settings", json={"ha_token": "long-lived-token"})
    body = client.get("/api/settings").json()
    assert body["ha_token"] == ""
    assert body["server"]["ha_token_set"] is True


# ------------------------------ redirect URI ---------------------------------


def test_redirect_uri_is_derived_and_reported(client, db):
    configure(client)
    body = client.get("/api/settings").json()
    assert (
        body["server"]["google_redirect_uri"]
        == "http://192.168.1.50:8080/api/accounts/google/callback"
    )


def test_redirect_uri_tolerates_a_trailing_slash(client, db):
    configure(client, public_base_url="http://calendar.local:8080/")
    assert google_config.load(db).redirect_uri == (
        "http://calendar.local:8080/api/accounts/google/callback"
    )


# ------------------------------- the OAuth flow -------------------------------


def test_the_consent_url_is_built_from_the_stored_credentials(client, db):
    client.post("/api/users", json={"name": "Mike"})
    configure(client)

    url = client.get("/api/accounts/google/auth-url", params={"user_id": 1}).json()["url"]

    assert "client_id=1234-abc.apps.googleusercontent.com" in url
    assert "192.168.1.50%3A8080%2Fapi%2Faccounts%2Fgoogle%2Fcallback" in url
    assert "access_type=offline" in url, "needed for a refresh token"
    assert "prompt=consent" in url


def test_connecting_before_setup_says_what_to_do(client, db):
    client.post("/api/users", json={"name": "Mike"})
    r = client.get("/api/accounts/google/auth-url", params={"user_id": 1})
    assert r.status_code == 400
    assert "Settings" in r.json()["error"]["message"]


def test_changing_the_client_id_takes_effect_without_a_restart(client, db):
    """The whole point of moving this out of .env."""
    client.post("/api/users", json={"name": "Mike"})
    configure(client)
    configure(client, google_client_id="second-id.apps.googleusercontent.com")

    url = client.get("/api/accounts/google/auth-url", params={"user_id": 1}).json()["url"]
    assert "client_id=second-id.apps.googleusercontent.com" in url


def test_token_refresh_uses_the_stored_credentials(client, db, monkeypatch):
    from datetime import datetime

    from app.models import LinkedAccount, User
    from app.services.crypto import encrypt

    configure(client)
    user = User(name="Mike")
    db.add(user)
    db.flush()
    account = LinkedAccount(
        user_id=user.id, provider="google", email="m@e.com",
        refresh_token_enc=encrypt("refresh-me"), token_expiry=datetime(2000, 1, 1),
    )
    db.add(account)
    db.commit()

    sent = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "fresh", "expires_in": 3600}

    def fake_post(url, data=None, **kwargs):
        sent.update(data or {})
        return Response()

    monkeypatch.setattr(google_oauth.httpx, "post", fake_post)
    assert google_oauth.refresh_access_token(db, account) == "fresh"
    assert sent["client_id"] == "1234-abc.apps.googleusercontent.com"
    assert sent["client_secret"] == "GOCSPX-supersecret"


# --------------------------- migrating from .env ------------------------------


def test_env_credentials_seed_the_database_once(client, db, monkeypatch):
    """An install that already had .env credentials keeps working, and the value
    shows up in Settings from then on."""
    from app.config import get_settings

    db.query(AppSetting).filter(
        AppSetting.key.in_(["google_client_id", "google_client_secret", "public_base_url"])
    ).delete(synchronize_session=False)
    db.commit()

    env = get_settings()
    monkeypatch.setattr(env, "google_client_id", "from-env", raising=False)
    monkeypatch.setattr(env, "google_client_secret", "env-secret", raising=False)

    google_config.seed_from_env(db)

    cfg = google_config.load(db)
    assert cfg.client_id == "from-env"
    assert cfg.client_secret == "env-secret"
    assert db.get(AppSetting, "google_client_id") is not None


def test_seeding_never_overwrites_what_was_typed_in_settings(client, db, monkeypatch):
    """.env keeps its old value forever; without this guard every restart would
    clobber the edit."""
    from app.config import get_settings

    configure(client)
    env = get_settings()
    monkeypatch.setattr(env, "google_client_id", "stale-env-value", raising=False)

    google_config.seed_from_env(db)

    assert google_config.load(db).client_id == "1234-abc.apps.googleusercontent.com"


def test_callback_refuses_a_token_without_calendar_access(client, monkeypatch):
    """Google grants what it can and drops the rest.

    A token with only `email` looks valid, links fine, and then 403s on every
    sync. The old code stored the account and let the 403 escape as a 500.
    """
    from app.services import google_oauth

    assert google_oauth.missing_calendar_scope(
        {"scope": "email https://www.googleapis.com/auth/userinfo.email openid"}
    )
    assert not google_oauth.missing_calendar_scope(
        {"scope": "https://www.googleapis.com/auth/calendar openid"}
    )
    # An unexpected shape must not block a working account.
    assert not google_oauth.missing_calendar_scope({})


def test_missing_calendar_scope_is_not_fooled_by_a_prefix():
    """`.../auth/calendar.readonly` is not `.../auth/calendar`, and a substring
    check would have accepted it."""
    from app.services import google_oauth

    assert google_oauth.missing_calendar_scope(
        {"scope": "https://www.googleapis.com/auth/calendar.readonly"}
    )


def test_sync_status_reports_google_configured_from_the_database(client):
    """Credentials moved out of .env in 0.2.2, and this endpoint kept reading the
    environment -- so it said "not configured" on every install that used Settings."""
    assert client.get("/api/sync/status").json()["google_configured"] is False

    configure(client)

    assert client.get("/api/sync/status").json()["google_configured"] is True
