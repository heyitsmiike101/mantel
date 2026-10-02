"""Update-check tests.

GitHub is faked at the HTTP layer with httpx.MockTransport, serving the real shape of the
tags API, so the tag filtering and version comparison are exercised end to end. What
matters most is that a bad day at GitHub never breaks anything and never forgets the last
good answer.
"""

import httpx
import pytest

from app.config import Settings
from app.services import scheduler, update_check


def tags_json(*names: str) -> list[dict]:
    return [{"name": n, "commit": {"sha": "abc"}} for n in names]


def github(body=None, status=200, calls=None, error: Exception | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        if error:
            raise error
        return httpx.Response(status, json=body if body is not None else [])

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _fresh_memory_cache():
    update_check.reset_for_tests()
    yield
    update_check.reset_for_tests()


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(
        update_check,
        "get_settings",
        lambda: Settings(app_version="0.5.9", update_check_enabled=True),
    )
    # The router reads settings through its own import.
    from app.routers import meta

    monkeypatch.setattr(
        meta, "get_settings", lambda: Settings(app_version="0.5.9", update_check_enabled=True)
    )


def test_a_newer_tag_marks_an_update_available(client, db, enabled):
    update_check.check_now(db, github(tags_json("v0.5.9", "v0.5.10", "v0.5.8")))

    body = client.get("/api/version").json()
    assert body["latest_version"] == "0.5.10", "0.5.10 must beat 0.5.9 numerically, not as text"
    assert body["update_available"] is True
    assert body["checked_at"] is not None
    assert body["release_url"] == "https://github.com/heyitsmiike101/mantel/compare/v0.5.9...v0.5.10"
    assert body["version"] == "0.5.9", "existing fields feed the auto-reload and must stay"


@pytest.mark.parametrize("tag", ["v0.5.9", "v0.5.2", "v0.4.99"])
def test_same_or_older_tag_is_not_an_update(client, db, enabled, tag):
    update_check.check_now(db, github(tags_json(tag)))

    body = client.get("/api/version").json()
    assert body["update_available"] is False
    assert body["latest_version"] == tag.lstrip("v")


def test_prerelease_and_non_semver_tags_are_ignored(client, db, enabled):
    update_check.check_now(
        db, github(tags_json("v1.0.0-rc1", "latest", "nightly", "v2", "v0.5.10", "1.0.0"))
    )

    assert client.get("/api/version").json()["latest_version"] == "0.5.10"


def test_a_dev_build_never_reports_an_update(db):
    assert update_check.is_newer("9.9.9", "dev") is False
    assert update_check.is_newer("9.9.9", "0.5.9-rc1") is False


def test_github_error_keeps_the_last_known_result(client, db, enabled):
    update_check.check_now(db, github(tags_json("v0.5.10")))

    status = update_check.check_now(db, github(status=403, body={"message": "rate limited"}))

    assert status.latest_version == "0.5.10", "an outage must not forget the last good answer"
    assert status.last_error and "GitHub" in status.last_error
    assert client.get("/api/version").json()["update_available"] is True


def test_timeout_does_not_raise_and_is_remembered(client, db, enabled):
    status = update_check.check_now(db, github(error=httpx.ConnectTimeout("timed out")))

    assert status.latest_version is None
    assert status.checked_at is None, "a failed check is not a successful check"
    assert status.last_error and "GitHub" in status.last_error


def test_result_survives_a_restart(client, db, enabled):
    update_check.check_now(db, github(tags_json("v0.5.10")))

    update_check.reset_for_tests()  # what a process restart does to the memory cache

    body = client.get("/api/version").json()
    assert body["latest_version"] == "0.5.10"
    assert body["update_available"] is True


def test_disabled_check_makes_no_request_and_reports_nothing(client, db, monkeypatch):
    cfg = Settings(app_version="0.5.9", update_check_enabled=False)
    monkeypatch.setattr(update_check, "get_settings", lambda: cfg)
    from app.routers import meta

    monkeypatch.setattr(meta, "get_settings", lambda: cfg)
    calls: list[httpx.Request] = []

    update_check.check_now(db, github(tags_json("v0.5.10"), calls=calls))

    assert calls == [], "UPDATE_CHECK_ENABLED=false must mean no network at all"
    body = client.get("/api/version").json()
    assert body["latest_version"] is None
    assert body["update_available"] is False


def test_the_request_identifies_itself_and_targets_the_configured_repo(client, db, monkeypatch):
    cfg = Settings(app_version="0.5.9", update_check_enabled=True, update_check_repo="someone/fork")
    monkeypatch.setattr(update_check, "get_settings", lambda: cfg)
    calls: list[httpx.Request] = []

    update_check.check_now(db, github(tags_json("v0.5.10"), calls=calls))

    assert str(calls[0].url).startswith("https://api.github.com/repos/someone/fork/tags")
    assert "Mantel" in calls[0].headers["user-agent"]
    assert "authorization" not in calls[0].headers


@pytest.mark.anyio
async def test_scheduler_starts_the_update_loop_even_when_sync_is_off(monkeypatch):
    import asyncio

    cfg = Settings(sync_enabled=False, update_check_enabled=True)
    monkeypatch.setattr(scheduler, "get_settings", lambda: cfg)

    tasks = scheduler.start(asyncio.get_running_loop())
    try:
        assert len(tasks) == 1, "update check is independent of SYNC_ENABLED"
    finally:
        await scheduler.stop(tasks)
