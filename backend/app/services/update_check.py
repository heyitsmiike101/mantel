"""Once-a-day "is there a newer Mantel?" check against GitHub.

Mantel is self-hosted and nothing pushes a new version to an install, so a wall display can
run an old build for months without anyone noticing. This only *reports* that a newer tag
exists; it never downloads or applies anything.

Releases are git tags (`v<version>`) created by `.github/workflows/release.yml`, and that
workflow does not create GitHub *Release* objects, so `/releases/latest` would 404 forever.
The tags API is queried instead and the highest `vX.Y.Z` wins.

Like weather, the rule is that a flaky upstream must never break the app: every failure is
logged, remembered, and the last good answer keeps being served.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..timeutil import as_utc, utcnow_naive
from .httpcache import get_cached, put_cached

log = logging.getLogger(__name__)

# GitHub rejects requests without a User-Agent, and asks that it identify the client.
USER_AGENT = "Mantel-update-check (+https://github.com/heyitsmiike101/mantel)"
TIMEOUT_SECONDS = 8.0

# Persisted in the weather_cache table (a generic key/payload/fetched_at store) rather than
# app_settings: every app_settings row is echoed by GET /api/settings and must be a key the
# settings screen can send back, and this is server bookkeeping, not a preference.
_CACHE_KEY = "update_check"

# Strictly X.Y.Z. Pre-releases (v1.0.0-rc1) and anything else must never be offered as
# "the" update, so they simply don't match.
_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

Semver = tuple[int, int, int]


@dataclass
class UpdateStatus:
    latest_version: str | None = None
    checked_at: datetime | None = None  # naive UTC, time of the last *successful* check
    last_error: str | None = None


_status: UpdateStatus | None = None


def parse_version(text: str) -> Semver | None:
    """`0.5.10` or `v0.5.10` as a comparable tuple; None for `dev`, pre-releases, junk."""
    m = _VERSION.match(text.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def newest_release(tag_names: list[str]) -> str | None:
    """Highest `vX.Y.Z` tag as a bare version. Compared numerically: 0.5.10 > 0.5.9."""
    best: Semver | None = None
    for name in tag_names:
        m = _TAG.match(name)
        if m:
            candidate = (int(m[1]), int(m[2]), int(m[3]))
            if best is None or candidate > best:
                best = candidate
    return ".".join(map(str, best)) if best else None


def is_newer(latest: str | None, running: str) -> bool:
    """False whenever either side isn't plain semver, so a `dev` build never nags."""
    if latest is None:
        return False
    a, b = parse_version(latest), parse_version(running)
    return a is not None and b is not None and a > b


def release_url(repo: str, latest: str, running: str) -> str:
    """Compare page when an upgrade is on offer (shows what changed), else the tag page.
    Tag pages render without a Release object, which is all this project publishes."""
    if is_newer(latest, running):
        return f"https://github.com/{repo}/compare/v{running.lstrip('v')}...v{latest}"
    return f"https://github.com/{repo}/releases/tag/v{latest}"


def _load(db: Session) -> UpdateStatus:
    payload, _ = get_cached(db, _CACHE_KEY, 0)
    if payload is None:
        return UpdateStatus()
    try:
        data = json.loads(payload)
        checked = data.get("checked_at")
        return UpdateStatus(
            latest_version=data.get("latest_version"),
            checked_at=datetime.fromisoformat(checked) if checked else None,
            last_error=data.get("last_error"),
        )
    except (ValueError, TypeError, AttributeError):
        return UpdateStatus()


def _save(db: Session, status: UpdateStatus) -> None:
    put_cached(
        db,
        _CACHE_KEY,
        json.dumps(
            {
                "latest_version": status.latest_version,
                "checked_at": status.checked_at.isoformat() if status.checked_at else None,
                "last_error": status.last_error,
            }
        ),
    )


def get_status(db: Session) -> UpdateStatus:
    """The last known result: memory first, then what survived the last restart."""
    global _status
    if _status is None:
        _status = _load(db)
    return _status


def reset_for_tests() -> None:
    global _status
    _status = None


def check_now(db: Session, transport: httpx.BaseTransport | None = None) -> UpdateStatus:
    """Ask GitHub for the newest tag. Never raises; a failure keeps the previous answer.

    `transport` exists so tests can stand in for GitHub's JSON at the HTTP layer.
    Makes no request at all when UPDATE_CHECK_ENABLED is false.
    """
    s = get_settings()
    current = get_status(db)
    if not s.update_check_enabled:
        return current

    url = f"https://api.github.com/repos/{s.update_check_repo}/tags"
    try:
        with httpx.Client(
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
            follow_redirects=True,
            transport=transport,
        ) as client:
            response = client.get(url, params={"per_page": 100})
            response.raise_for_status()
            tags = [t["name"] for t in response.json()]
    except Exception as exc:  # noqa: BLE001 -- a failed check must not take the loop down
        log.warning("Update check against GitHub (%s) failed: %s", s.update_check_repo, exc)
        current.last_error = f"GitHub: {exc}"[:300]
        _try_save(db, current)
        return current

    latest = newest_release(tags)
    if latest is None:
        # A reachable repo with no vX.Y.Z tag is not an upgrade, and should not erase a
        # version we already know about.
        log.warning("GitHub repo %s has no vX.Y.Z tags", s.update_check_repo)
        current.last_error = f"GitHub: no vX.Y.Z tags found in {s.update_check_repo}"
    else:
        current.latest_version = latest
        current.last_error = None
    current.checked_at = utcnow_naive()
    _try_save(db, current)
    return current


def _try_save(db: Session, status: UpdateStatus) -> None:
    try:
        _save(db, status)
    except Exception:  # noqa: BLE001 -- persistence is a nicety; memory still has the answer
        log.warning("Could not persist the update-check result", exc_info=True)
        db.rollback()


def checked_at_utc(status: UpdateStatus) -> datetime | None:
    return as_utc(status.checked_at)
