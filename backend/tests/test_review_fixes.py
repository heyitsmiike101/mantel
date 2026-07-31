"""Regression tests for the issues found in code review of v0.2.0."""

import threading
import time
from datetime import datetime

import pytest
from fake_google import FakeGoogle, gevent
from sqlalchemy import inspect

from app.db import engine
from app.models import Base, Calendar, Event, LinkedAccount, User
from app.schema_sync import SchemaUpgradeError, sync
from app.services import google_sync, homeassistant, httpcache, recurrence
from app.services.crypto import encrypt, feed_token


@pytest.fixture
def fake(monkeypatch):
    f = FakeGoogle()
    monkeypatch.setattr(google_sync, "client_factory", f)
    monkeypatch.setattr(google_sync, "access_token_for", lambda db, a: "t")
    return f


@pytest.fixture
def gcal(client, db, fake):
    u = User(name="Mike", color="#3b82f6")
    db.add(u)
    db.flush()
    acc = LinkedAccount(
        user_id=u.id, provider="google", email="m@e.com",
        access_token_enc=encrypt("a"), refresh_token_enc=encrypt("r"),
        token_expiry=datetime(2030, 1, 1),
    )
    db.add(acc)
    db.flush()
    cal = Calendar(
        linked_account_id=acc.id, google_calendar_id="primary", name="G",
        claimed_by_user_id=u.id, sync_enabled=True, access_role="owner",
    )
    db.add(cal)
    db.commit()
    return cal


# --------------------- 1. feed must not export the master --------------------


def test_feed_excludes_a_series_google_now_owns(client, db, gcal, fake):
    """Once pushed, Google's expanded instances are the record. Exporting the
    master's RRULE as well made every subscriber render the series twice."""
    client.post("/api/events", json={
        "calendar_id": gcal.id, "title": "Weekly sync",
        "start_at": "2026-08-03T13:00:00Z", "end_at": "2026-08-03T13:30:00Z",
        "recurrence_rule": "FREQ=WEEKLY;COUNT=4"})
    google_sync.push_pending(db)

    fake.pages = [([
        gevent("g1_1", "Weekly sync", "2026-08-03T13:00:00Z", "2026-08-03T13:30:00Z",
               recurringEventId="g1"),
        gevent("g1_2", "Weekly sync", "2026-08-10T13:00:00Z", "2026-08-10T13:30:00Z",
               recurringEventId="g1"),
    ], "t1")]
    google_sync.pull_calendar(db, gcal)

    feed = client.get("/api/feeds/all.ics", params={"token": feed_token()}).text
    assert feed.count("BEGIN:VEVENT") == 2, "the pushed master must not be exported too"
    assert "RRULE:" not in feed, "no master means no rule to double-expand"


def test_feed_still_exports_a_local_series_as_one_rrule(client, local_calendar):
    """The guard must not swallow series this app still owns."""
    client.post("/api/events", json={
        "calendar_id": local_calendar["id"], "title": "Piano",
        "start_at": "2026-08-03T17:00:00Z", "end_at": "2026-08-03T18:00:00Z",
        "recurrence_rule": "FREQ=WEEKLY;COUNT=6"})
    feed = client.get("/api/feeds/all.ics", params={"token": feed_token()}).text
    assert feed.count("BEGIN:VEVENT") == 1
    assert "RRULE:FREQ=WEEKLY;COUNT=6" in feed


# ------------- 2. expansion must not touch the ORM relationship --------------


def test_materialise_leaves_the_calendar_collection_alone(client, db, local_calendar):
    """A plain `instance.calendar = ...` back-populated transient duplicate-PK
    rows into Calendar.events, which the next flush would try to INSERT."""
    client.post("/api/events", json={
        "calendar_id": local_calendar["id"], "title": "Daily",
        "start_at": "2026-08-03T13:00:00Z", "end_at": "2026-08-03T14:00:00Z",
        "recurrence_rule": "FREQ=DAILY;COUNT=5"})

    cal = db.get(Calendar, local_calendar["id"])
    before = len(cal.events)
    series = db.query(Event).filter(Event.recurrence_rule.is_not(None)).one()
    instances = recurrence.materialise(series, datetime(2026, 8, 1), datetime(2026, 9, 1))

    assert len(instances) == 5
    assert len(cal.events) == before, "transient copies must stay out of the session"
    assert all(i.calendar is cal for i in instances), "serialisation still needs the calendar"


def test_a_flush_after_expansion_inserts_nothing(client, db, local_calendar):
    """The concrete failure the old code was one query away from."""
    client.post("/api/events", json={
        "calendar_id": local_calendar["id"], "title": "Daily",
        "start_at": "2026-08-03T13:00:00Z", "end_at": "2026-08-03T14:00:00Z",
        "recurrence_rule": "FREQ=DAILY;COUNT=5"})

    series = db.query(Event).filter(Event.recurrence_rule.is_not(None)).one()
    recurrence.materialise(series, datetime(2026, 8, 1), datetime(2026, 9, 1))

    db.flush()  # would raise IntegrityError, or silently insert, before the fix
    assert db.query(Event).count() == 1


# ---------------- 3. Google-originated changes must notify HA ----------------


def test_pulling_from_google_notifies_home_assistant(client, db, gcal, fake, monkeypatch):
    """With HA's own polling switched off as the setup guide instructs, this is
    the only thing that can tell HA about an event added on someone's phone."""
    calls = []
    monkeypatch.setattr(homeassistant, "notify_async", lambda *a: calls.append(a))
    client.patch("/api/settings", json={
        "ha_base_url": "http://ha:8123", "ha_token": "tok",
        "ha_entity_id": "calendar.family"})

    fake.pages = [([gevent("g1", "Dentist", "2026-08-05T14:00:00Z",
                           "2026-08-05T15:00:00Z")], "t1")]
    google_sync.pull_all(db)

    assert calls, "a pull that changed something must refresh Home Assistant"
    assert calls[-1][2] == "calendar.family"


def test_a_pull_with_no_changes_does_not_notify(client, db, gcal, fake, monkeypatch):
    calls = []
    monkeypatch.setattr(homeassistant, "notify_async", lambda *a: calls.append(a))
    client.patch("/api/settings", json={
        "ha_base_url": "http://ha:8123", "ha_token": "tok",
        "ha_entity_id": "calendar.family"})

    fake.pages = [([], "t1")]
    google_sync.pull_all(db)
    assert calls == [], "an idle sync should not wake Home Assistant"


# --------------- 4. an unaddable required column must fail loudly ------------


def test_upgrade_refuses_to_start_on_a_column_it_cannot_add(monkeypatch):
    """Skipping it left a database missing a required column while the container
    reported a clean boot."""
    from sqlalchemy import Column, Integer

    bad = Column("needs_manual_migration", Integer, nullable=False)
    events = Base.metadata.tables["events"]
    events.append_column(bad)
    try:
        with pytest.raises(SchemaUpgradeError, match="manual migration"):
            sync(engine)
    finally:
        events._columns.remove(bad)


# ------------------ 5. one upstream request per cache key --------------------


def test_a_second_caller_gets_stale_data_instead_of_queueing(client, db, monkeypatch):
    """Four wall displays refreshing on the same TTL boundary should cost one
    upstream request and one blocked worker, not four of each."""
    httpcache.put_cached(db, "probe", "old-body")
    started = threading.Event()
    release = threading.Event()
    calls = []

    def slow(session, key, url, ttl_s, params, cached):
        calls.append(url)
        started.set()
        release.wait(timeout=5)
        httpcache.put_cached(session, key, "fresh-body")
        return "fresh-body", False

    monkeypatch.setattr(httpcache, "_fetch_locked", slow)

    from app.db import SessionLocal

    def refresher():
        with SessionLocal() as s:
            httpcache.fetch(s, "probe", "https://example.invalid", ttl_s=0)

    t = threading.Thread(target=refresher, daemon=True)
    t.start()
    assert started.wait(timeout=5)

    began = time.monotonic()
    body, stale = httpcache.fetch(db, "probe", "https://example.invalid", ttl_s=0)
    elapsed = time.monotonic() - began

    release.set()
    t.join(timeout=5)

    assert body == "old-body" and stale is True, "second caller serves what it has"
    assert elapsed < 1.0, "and must not block behind the in-flight refresh"
    assert len(calls) == 1, "only one upstream request per key"


# --------------- 6. HA nudges coalesce onto one worker thread ----------------


def test_a_burst_of_writes_uses_one_thread_and_one_call(monkeypatch):
    """A season import through the API used to spawn a thread per event."""
    monkeypatch.setattr(homeassistant, "DEBOUNCE_SECONDS", 0.05)
    sent = []
    monkeypatch.setattr(homeassistant, "notify", lambda *a: sent.append(a))

    for _ in range(200):
        homeassistant.notify_async("http://ha:8123", "tok", "calendar.family")

    workers = [t for t in threading.enumerate() if t.name == "ha-notify"]
    assert len(workers) <= 1, f"expected one coalescing worker, found {len(workers)}"

    deadline = time.monotonic() + 3
    while not sent and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(sent) == 1, f"200 writes should collapse into one nudge, got {len(sent)}"


# ------------- 7. finished series stop being scanned every request -----------


def test_series_end_is_recorded_for_a_finite_rule(client, local_calendar):
    ev = client.post("/api/events", json={
        "calendar_id": local_calendar["id"], "title": "Six weeks",
        "start_at": "2026-08-03T17:00:00Z", "end_at": "2026-08-03T18:00:00Z",
        "recurrence_rule": "FREQ=WEEKLY;COUNT=3"}).json()

    from app.db import SessionLocal

    with SessionLocal() as s:
        row = s.get(Event, ev["id"])
        assert row.recurrence_end is not None
        # third occurrence is Aug 17, ending an hour later
        assert row.recurrence_end == datetime(2026, 8, 17, 18, 0)


def test_an_endless_rule_records_no_end(client, local_calendar):
    ev = client.post("/api/events", json={
        "calendar_id": local_calendar["id"], "title": "Forever",
        "start_at": "2026-08-03T17:00:00Z", "end_at": "2026-08-03T18:00:00Z",
        "recurrence_rule": "FREQ=WEEKLY"}).json()

    from app.db import SessionLocal

    with SessionLocal() as s:
        assert s.get(Event, ev["id"]).recurrence_end is None


def test_a_finished_series_is_not_loaded_for_a_later_window(client, db, local_calendar):
    """The whole point: cost should track the window, not the age of the install."""
    client.post("/api/events", json={
        "calendar_id": local_calendar["id"], "title": "Old club",
        "start_at": "2020-01-06T17:00:00Z", "end_at": "2020-01-06T18:00:00Z",
        "recurrence_rule": "FREQ=WEEKLY;COUNT=4"})

    expansions = []
    original = recurrence.materialise

    def counting(event, ws, we):
        expansions.append(event.id)
        return original(event, ws, we)

    import app.routers.events as events_router

    events_router.recurrence.materialise = counting
    try:
        body = client.get("/api/events", params={
            "start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}).json()
    finally:
        events_router.recurrence.materialise = original

    assert body == []
    assert expansions == [], "a series that ended in 2020 must not be re-expanded in 2026"


def test_a_live_series_is_still_expanded(client, local_calendar):
    client.post("/api/events", json={
        "calendar_id": local_calendar["id"], "title": "Ongoing",
        "start_at": "2026-08-03T17:00:00Z", "end_at": "2026-08-03T18:00:00Z",
        "recurrence_rule": "FREQ=WEEKLY;COUNT=4"})
    body = client.get("/api/events", params={
        "start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}).json()
    assert len(body) == 4


def test_shortening_a_series_updates_its_end(client, local_calendar):
    """recurrence_end must be recomputed on edit, or a shortened series would
    keep being scanned (or worse, a lengthened one would be skipped)."""
    ev = client.post("/api/events", json={
        "calendar_id": local_calendar["id"], "title": "Club",
        "start_at": "2026-08-03T17:00:00Z", "end_at": "2026-08-03T18:00:00Z",
        "recurrence_rule": "FREQ=WEEKLY;COUNT=10"}).json()
    client.patch(f"/api/events/{ev['id']}", json={"recurrence_rule": "FREQ=WEEKLY;COUNT=2"})

    from app.db import SessionLocal

    with SessionLocal() as s:
        assert s.get(Event, ev["id"]).recurrence_end == datetime(2026, 8, 10, 18, 0)

    body = client.get("/api/events", params={
        "start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}).json()
    assert len(body) == 2


def test_recurrence_end_column_exists_after_upgrade():
    assert "recurrence_end" in {c["name"] for c in inspect(engine).get_columns("events")}
