"""Upgrade-path tests.

`create_all` adds missing tables but never missing columns, so without this the
first write after `git pull` would 500 on an existing install. These tests
simulate an older database by dropping columns back out.
"""

import pytest
from sqlalchemy import inspect, text

from app.db import engine
from app.models import Base
from app.schema_sync import sync


def columns(table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


@pytest.fixture
def fresh_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def drop_column(conn, table: str, column: str) -> None:
    """SQLite refuses to drop a column an index still references, so the index
    goes first -- which is also exactly the state an older release left behind."""
    for index in inspect(engine).get_indexes(table):
        if column in index["column_names"]:
            conn.execute(text(f'DROP INDEX IF EXISTS "{index["name"]}"'))
    conn.execute(text(f'ALTER TABLE "{table}" DROP COLUMN "{column}"'))


def test_adds_a_column_an_older_release_did_not_have(fresh_schema):
    with engine.begin() as conn:
        drop_column(conn, "events", "is_master")
    assert "is_master" not in columns("events")

    applied = sync(engine)

    assert "events.is_master" in applied
    assert "is_master" in columns("events")


def test_recreates_the_index_for_a_newly_added_column(fresh_schema):
    with engine.begin() as conn:
        drop_column(conn, "events", "is_master")

    applied = sync(engine)

    names = {ix["name"] for ix in inspect(engine).get_indexes("events")}
    assert "ix_events_is_master" in names
    assert "index ix_events_is_master" in applied


def test_existing_rows_get_the_column_default(fresh_schema):
    """A row written by the old version must come back with a usable value, not
    something that breaks the query that now filters on it."""
    now = "2026-07-01 12:00:00"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO calendars (name, sync_enabled, access_role, created_at, updated_at)"
                f" VALUES ('Family', 0, 'owner', '{now}', '{now}')"
            )
        )
        drop_column(conn, "events", "is_master")
        conn.execute(
            text(
                "INSERT INTO events (calendar_id, title, start_at, end_at, all_day, status,"
                " origin, sync_state, local_updated_at, created_at, updated_at)"
                " VALUES (1, 'Old event', '2026-08-03 17:00:00', '2026-08-03 18:00:00', 0,"
                f" 'confirmed', 'local', 'synced', '{now}', '{now}', '{now}')"
            )
        )

    sync(engine)

    with engine.begin() as conn:
        value = conn.execute(text("SELECT is_master FROM events")).scalar()
    assert value == 0, "pre-existing rows must not be left NULL for a filtered column"


def test_creates_a_table_an_older_release_did_not_have(fresh_schema):
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE photos"))
    assert "photos" not in inspect(engine).get_table_names()

    sync(engine)
    assert "photos" in inspect(engine).get_table_names()


def test_is_idempotent(fresh_schema):
    assert sync(engine) == []
    assert sync(engine) == [], "a second run on an up-to-date schema changes nothing"


def test_upgraded_database_actually_serves_requests(client, fresh_schema):
    """The end-to-end shape of the bug: an old database, then a write."""
    with engine.begin() as conn:
        drop_column(conn, "events", "is_master")
        drop_column(conn, "events", "recurrence_rule")

    sync(engine)

    cal = client.post("/api/calendars", json={"name": "Family"}).json()
    r = client.post(
        "/api/events",
        json={
            "calendar_id": cal["id"],
            "title": "After upgrade",
            "start_at": "2026-08-03T17:00:00Z",
            "end_at": "2026-08-03T18:00:00Z",
            "recurrence_rule": "FREQ=WEEKLY;COUNT=2",
        },
    )
    assert r.status_code == 201
    listed = client.get(
        "/api/events", params={"start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}
    ).json()
    assert len(listed) == 2
