from concurrent.futures import ThreadPoolExecutor

from app.db import engine


def test_sqlite_uses_wal(client):
    """WAL is what lets every screen in the house keep reading while someone edits."""
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode.lower() == "wal"


def test_concurrent_writes_from_many_screens(client, local_calendar):
    """Several people adding events at the same moment must all succeed --
    no 'database is locked' errors."""

    def add(i: int):
        return client.post(
            "/api/events",
            json={
                "calendar_id": local_calendar["id"],
                "title": f"Event {i}",
                "start_at": "2026-08-03T17:00:00Z",
                "end_at": "2026-08-03T18:00:00Z",
            },
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(add, range(30)))

    assert all(r.status_code == 201 for r in results)
    listed = client.get(
        "/api/events", params={"start": "2026-08-03T00:00:00Z", "end": "2026-08-04T00:00:00Z"}
    ).json()
    assert len(listed) == 30


def test_reads_during_writes(client, local_calendar):
    """Readers must never be blocked out or see a partial write."""

    def write(i: int):
        return client.post(
            "/api/events",
            json={
                "calendar_id": local_calendar["id"],
                "title": f"W{i}",
                "start_at": "2026-08-03T17:00:00Z",
                "end_at": "2026-08-03T18:00:00Z",
            },
        ).status_code

    def read(_):
        r = client.get(
            "/api/events", params={"start": "2026-08-03T00:00:00Z", "end": "2026-08-04T00:00:00Z"}
        )
        return r.status_code

    with ThreadPoolExecutor(max_workers=16) as pool:
        writes = pool.map(write, range(20))
        reads = pool.map(read, range(40))
        assert all(s == 201 for s in writes)
        assert all(s == 200 for s in reads)
