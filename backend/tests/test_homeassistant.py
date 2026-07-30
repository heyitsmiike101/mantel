from app.services import homeassistant, notify


def configure(client, **overrides):
    return client.patch(
        "/api/settings",
        json={
            "ha_base_url": "http://homeassistant.local:8123",
            "ha_token": "long-lived-token",
            "ha_entity_id": "calendar.family_calendar",
            **overrides,
        },
    )


def test_settings_expose_home_assistant_fields(client):
    settings = client.get("/api/settings").json()
    assert settings["ha_base_url"] == ""
    assert settings["ha_entity_id"] == "calendar.family_calendar"

    updated = configure(client).json()
    assert updated["ha_base_url"] == "http://homeassistant.local:8123"


def test_creating_an_event_nudges_home_assistant(client, db, local_calendar, monkeypatch):
    """Remote Calendar polls every 24 hours, so without this push a family
    calendar in HA would be a day stale."""
    calls = []
    monkeypatch.setattr(
        homeassistant, "notify_async", lambda *args: calls.append(args)
    )
    configure(client)

    client.post(
        "/api/events",
        json={
            "calendar_id": local_calendar["id"],
            "title": "Soccer practice",
            "start_at": "2026-08-03T17:00:00Z",
            "end_at": "2026-08-03T18:00:00Z",
        },
    )

    assert calls, "a calendar change must tell Home Assistant to refresh"
    base, token, entity = calls[-1]
    assert base == "http://homeassistant.local:8123"
    assert token == "long-lived-token"
    assert entity == "calendar.family_calendar"


def test_editing_and_deleting_also_nudge(client, db, local_calendar, monkeypatch):
    calls = []
    monkeypatch.setattr(homeassistant, "notify_async", lambda *a: calls.append(a))
    configure(client)

    ev = client.post(
        "/api/events",
        json={
            "calendar_id": local_calendar["id"],
            "title": "Soccer",
            "start_at": "2026-08-03T17:00:00Z",
            "end_at": "2026-08-03T18:00:00Z",
        },
    ).json()
    client.patch(f"/api/events/{ev['id']}", json={"title": "Soccer game"})
    client.delete(f"/api/events/{ev['id']}")

    assert len(calls) == 3, "create, update and delete each refresh HA"


def test_nothing_happens_when_unconfigured(client, db, local_calendar, monkeypatch):
    sent = []
    monkeypatch.setattr(homeassistant, "notify", lambda *a: sent.append(a))

    client.post(
        "/api/events",
        json={
            "calendar_id": local_calendar["id"],
            "title": "Soccer",
            "start_at": "2026-08-03T17:00:00Z",
            "end_at": "2026-08-03T18:00:00Z",
        },
    )
    assert sent == [], "no HA settings means no outbound calls at all"


def test_notify_ignores_incomplete_configuration(monkeypatch):
    import httpx

    def explode(*args, **kwargs):
        raise AssertionError("must not call out with missing settings")

    monkeypatch.setattr(httpx, "post", explode)
    homeassistant.notify("", "token", "calendar.x")
    homeassistant.notify("http://ha", "", "calendar.x")
    homeassistant.notify("http://ha", "token", "")


def test_notify_swallows_a_dead_home_assistant(monkeypatch):
    """HA being powered off must never break saving an event."""
    import httpx

    def boom(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", boom)
    homeassistant.notify("http://ha", "token", "calendar.x")  # must not raise


def test_connection_test_reports_clearly(monkeypatch):
    import httpx

    ok, message = homeassistant.test_connection("", "")
    assert ok is False and "token" in message

    class Response:
        status_code = 401

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Response())
    ok, message = homeassistant.test_connection("http://ha", "bad")
    assert ok is False and "rejected" in message

    Response.status_code = 200
    ok, message = homeassistant.test_connection("http://ha", "good")
    assert ok is True


def test_calendar_changed_reads_settings_from_the_database(client, db, monkeypatch):
    calls = []
    monkeypatch.setattr(homeassistant, "notify_async", lambda *a: calls.append(a))
    configure(client, ha_entity_id="calendar.kitchen")
    notify.calendar_changed(db)
    assert calls[-1][2] == "calendar.kitchen"
