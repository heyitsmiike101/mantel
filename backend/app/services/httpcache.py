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

import httpx
from sqlalchemy.orm import Session

from ..models import WeatherCache
from ..timeutil import utcnow_naive

log = logging.getLogger(__name__)

# NWS rejects requests without a User-Agent and asks for contact details in it.
USER_AGENT = "FamilyCalendar/1.0 (+https://github.com/topics/family-calendar)"
TIMEOUT_SECONDS = 15.0


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
    """
    cached, expired = get_cached(session, key, ttl_s)
    if cached is not None and not expired:
        return cached, False

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
