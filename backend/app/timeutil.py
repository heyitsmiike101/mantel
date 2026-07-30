from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    """Current UTC time in the naive form everything is persisted as."""
    return datetime.now(UTC).replace(tzinfo=None)


def to_utc(dt: datetime) -> datetime:
    """SQLite has no native timezone storage, so everything is persisted as naive UTC.
    A naive input is assumed to already be UTC."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def as_utc(dt: datetime | None) -> datetime | None:
    """Re-attach UTC when reading back, so the API always emits offset-aware ISO-8601."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
