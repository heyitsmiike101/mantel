"""Cached outbound HTTP with graceful degradation.

Ported from life-dash's weather service, whose governing rule applies here too:
**the wall display must never break because an upstream API is having a bad day.**
Every fetch either returns fresh data, returns the last good response with a
`stale` flag, or reports unavailable -- it never raises at the caller.

Note what this deliberately does *not* do: fetch a URL supplied by a user. Every
URL is built here from validated coordinates. Handing a server-side fetcher an
arbitrary URL is how MagicMirror shipped a critical SSRF in 2026, and it is the
reason ICS subscription import is not in this release.
"""

import logging
import threading

import httpx
from sqlalchemy.orm import Session

from ..models import WeatherCache
from ..timeutil import utcnow_naive

log = logging.getLogger(__name__)

# NWS rejects requests without a User-Agent and asks for contact details in it.
USER_AGENT = "FamilyCalendar/1.0 (+https://github.com/topics/family-calendar)"
# Four sequential NWS calls at 15s each could pin a threadpool worker for a
# minute; 8s keeps the worst case bounded while still tolerating a slow upstream.
TIMEOUT_SECONDS = 8.0

# One in-flight request per cache key. See `fetch`.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def get_cached(session: Session, key: str, ttl_s: int) -> tuple[str | None, bool]:
    """(payload, expired). A missing entry counts as expired."""
    row = session.get(WeatherCache, key)
    if row is None:
        return None, True
    age = (utcnow_naive() - row.fetched_at).total_seconds()
    return row.payload, age > ttl_s


def put_cached(session: Session, key: str, payload: str) -> None:
    row = session.get(WeatherCache, key)
    if row is None:
        session.add(WeatherCache(key=key, payload=payload, fetched_at=utcnow_naive()))
    else:
        row.payload = payload
        row.fetched_at = utcnow_naive()
    session.commit()


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def fetch(
    session: Session,
    key: str,
    url: str,
    ttl_s: int,
    params: dict | None = None,
) -> tuple[str | None, bool]:
    """Returns (body, stale).

    A warm cache short-circuits the network. A failed request falls back to
    whatever is cached, however old, rather than propagating the error -- a
    yesterday's forecast is far better than an empty panel.

    Only one caller per key talks to the network at a time. Everyone else gets
    the stale copy immediately instead of queueing behind it: four wall displays
    refreshing on the same TTL boundary should cost one upstream request and one
    blocked worker, not four of each. Callers with nothing cached at all do wait,
    because on a cold start there is nothing better to show them.
    """
    cached, expired = get_cached(session, key, ttl_s)
    if cached is not None and not expired:
        return cached, False

    lock = _lock_for(key)
    if not lock.acquire(blocking=cached is None):
        return cached, True

    try:
        # Another thread may have refreshed while this one waited for the lock.
        # The read above opened a transaction, so this session is still on the
        # pre-refresh snapshot and would re-fetch needlessly; ending it first is
        # what lets the re-check actually see the other thread's commit. Safe on
        # a read path, which is the only place this runs.
        session.rollback()
        cached, expired = get_cached(session, key, ttl_s)
        if cached is not None and not expired:
            return cached, False
        return _fetch_locked(session, key, url, ttl_s, params, cached)
    finally:
        lock.release()


def _fetch_locked(
    session: Session,
    key: str,
    url: str,
    ttl_s: int,
    params: dict | None,
    cached: str | None,
) -> tuple[str | None, bool]:
    try:
        with httpx.Client(
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        ) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            body = response.text
        put_cached(session, key, body)
        return body, False
    except Exception as exc:  # noqa: BLE001 -- degrade, never raise
        log.warning("weather fetch failed for %s: %s", url, exc)
        return (cached, True) if cached is not None else (None, True)
