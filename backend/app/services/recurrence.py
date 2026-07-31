"""Recurring event expansion.

Only *local* calendars are expanded here. Google-backed recurring events are
requested with `singleEvents=true`, so Google has already expanded them into
individual instances by the time they reach us -- expanding them again would
double every occurrence.

That asymmetry is the reason for `Event.is_master`: a locally created recurring
event on a Google calendar is stored once as a master, pushed as an RRULE, and
then hidden from queries so Google's own expanded instances are the only thing
displayed. See `google_sync._push_one`.
"""

from datetime import datetime, timedelta

from dateutil import rrule as rrule_lib
from sqlalchemy.orm.attributes import set_committed_value

from ..models import Event

# A runaway rule (no COUNT, no UNTIL, DAILY) must not be able to generate a
# million rows for a wide query. A decade of daily events is far past anything a
# family calendar view asks for.
MAX_OCCURRENCES = 3660

FREQUENCIES = {
    "DAILY": rrule_lib.DAILY,
    "WEEKLY": rrule_lib.WEEKLY,
    "MONTHLY": rrule_lib.MONTHLY,
    "YEARLY": rrule_lib.YEARLY,
}


class RecurrenceError(ValueError):
    """An RRULE we can't parse. The message is safe to show the user."""


def _naive_until(rule: str) -> str:
    """Drop the trailing Z from UNTIL.

    Every datetime in this database is naive UTC. dateutil refuses to compare a
    timezone-aware UNTIL against a naive DTSTART and yields *no occurrences at
    all* rather than raising -- so `FREQ=WEEKLY;UNTIL=20261231T000000Z`, which is
    the standard form and exactly what Google emits, would silently make an event
    vanish. Stripping the Z keeps both sides naive UTC, which they already are.
    """
    out = []
    for piece in rule.split(";"):
        if piece.startswith("UNTIL=") and piece.endswith("Z"):
            piece = piece[:-1]
        out.append(piece)
    return ";".join(out)


def validate(rule: str) -> str:
    """Normalise and sanity-check an RRULE before it is stored."""
    text = rule.strip().upper()
    if text.startswith("RRULE:"):
        text = text[len("RRULE:") :]
    if not text:
        raise RecurrenceError("Empty recurrence rule")

    text = _naive_until(text)
    parts = dict(
        piece.split("=", 1) for piece in text.split(";") if "=" in piece
    )
    freq = parts.get("FREQ")
    if freq not in FREQUENCIES:
        raise RecurrenceError(
            f"Unsupported FREQ={freq!r}. Use DAILY, WEEKLY, MONTHLY or YEARLY."
        )

    # Parse it for real so a malformed BYDAY/UNTIL is caught at write time rather
    # than blowing up inside a calendar query later.
    try:
        rrule_lib.rrulestr(text, dtstart=datetime(2026, 1, 1))
    except (ValueError, TypeError) as exc:
        raise RecurrenceError(f"Could not read that recurrence rule: {exc}") from exc

    return text


def series_end(rule: str | None, dtstart: datetime, duration: timedelta) -> datetime | None:
    """When a finite series stops, or None if it never does.

    Stored on the row so `list_events` can skip finished series in SQL. Without
    it every series ever created is loaded and re-expanded on every request, and
    the cost grows with the age of the install rather than the size of the window.
    """
    if not rule:
        return None
    try:
        parsed = rrule_lib.rrulestr(_naive_until(rule), dtstart=dtstart)
    except (ValueError, TypeError):
        return None

    # An unbounded rule has neither; asking for its last occurrence would hang.
    upper = rule.upper()
    if "COUNT=" not in upper and "UNTIL=" not in upper:
        return None

    last = None
    for count, occurrence in enumerate(parsed):
        last = occurrence
        if count >= MAX_OCCURRENCES:
            return None  # pathologically long; treat as unbounded
    return None if last is None else last + duration


def occurrences(event: Event, window_start: datetime, window_end: datetime) -> list[datetime]:
    """Start times for `event` that fall inside the window.

    The window is widened backwards by the event's duration so a long occurrence
    that started before the window but is still running is included -- the same
    overlap rule single events already follow.
    """
    if not event.recurrence_rule:
        return []

    duration = event.end_at - event.start_at
    search_from = window_start - duration

    try:
        # Defensive: rules stored before normalisation existed, or written straight
        # into the database, may still carry a Z-suffixed UNTIL.
        rule = rrule_lib.rrulestr(_naive_until(event.recurrence_rule), dtstart=event.start_at)
    except (ValueError, TypeError):
        return []

    found: list[datetime] = []
    for occurrence in rule:
        if occurrence >= window_end:
            break
        if occurrence > search_from:
            found.append(occurrence)
            if len(found) >= MAX_OCCURRENCES:
                break
    return found


def materialise(event: Event, window_start: datetime, window_end: datetime) -> list[Event]:
    """Detached copies of `event`, one per occurrence in the window.

    These are never added to the session -- they exist only to be serialised. The
    id is kept so the UI can open and edit the underlying series.

    The calendar is attached with `set_committed_value` rather than a plain
    assignment. `Event.calendar` has a back_populates to `Calendar.events`, whose
    cascade includes save-update, so `instance.calendar = ...` would append these
    transient duplicate-primary-key rows to the persistent collection -- and the
    next flush would try to INSERT them. set_committed_value writes the attribute
    as if it had been loaded from the database, firing no events and touching no
    backref.
    """
    duration = event.end_at - event.start_at
    out: list[Event] = []

    for start in occurrences(event, window_start, window_end):
        instance = Event(
            id=event.id,
            calendar_id=event.calendar_id,
            google_event_id=event.google_event_id,
            title=event.title,
            description=event.description,
            location=event.location,
            start_at=start,
            end_at=start + duration,
            all_day=event.all_day,
            timezone=event.timezone,
            recurrence_rule=event.recurrence_rule,
            recurring_event_id=event.recurring_event_id,
            status=event.status,
            origin=event.origin,
            sync_state=event.sync_state,
        )
        set_committed_value(instance, "calendar", event.calendar)
        out.append(instance)

    return out


def describe(rule: str | None) -> str | None:
    """Short human phrasing for the UI, e.g. 'Every week on Mon, Wed'."""
    if not rule:
        return None
    try:
        parts = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)
    except ValueError:
        return "Repeats"

    freq = parts.get("FREQ", "")
    interval = int(parts.get("INTERVAL", 1))
    unit = {"DAILY": "day", "WEEKLY": "week", "MONTHLY": "month", "YEARLY": "year"}.get(freq)
    if unit is None:
        return "Repeats"

    text = f"Every {unit}" if interval == 1 else f"Every {interval} {unit}s"

    if freq == "WEEKLY" and parts.get("BYDAY"):
        names = {
            "MO": "Mon", "TU": "Tue", "WE": "Wed", "TH": "Thu",
            "FR": "Fri", "SA": "Sat", "SU": "Sun",
        }
        days = [names.get(d, d) for d in parts["BYDAY"].split(",")]
        text += " on " + ", ".join(days)

    if parts.get("COUNT"):
        text += f", {parts['COUNT']} times"
    elif parts.get("UNTIL"):
        raw = parts["UNTIL"]
        try:
            until = datetime.strptime(raw[:8], "%Y%m%d")
            text += f", until {until.strftime('%b %-d, %Y')}"
        except ValueError:
            pass

    return text


def next_occurrence_after(event: Event, moment: datetime) -> datetime | None:
    """First start time at or after `moment`, for countdowns and reminders."""
    found = occurrences(event, moment, moment + timedelta(days=365 * 3))
    return found[0] if found else None
