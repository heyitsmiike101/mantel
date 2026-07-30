"""iCalendar export.

One small feature that does two jobs:

* a family member's iPhone or Outlook can **subscribe** to the family calendar
  natively, without us implementing CalDAV;
* Home Assistant's Remote Calendar integration can consume it, which — paired
  with a push to `homeassistant.update_entity` — gives a live calendar entity
  inside HA with no custom Python running there at all.

Written by hand rather than with a library because the output is small, the
escaping rules are short, and a dependency that formats text is a poor trade for
a file this size.
"""

from datetime import datetime, timedelta

from ..models import Event
from ..timeutil import utcnow_naive

PRODID = "-//Family Calendar//EN"
LINE_LIMIT = 75


def _escape(text: str | None) -> str:
    """RFC 5545 §3.3.11: backslash, semicolon, comma and newline are special."""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 §3.1 caps content lines at 75 octets, continued with a leading
    space. Strict parsers -- including the one Home Assistant uses -- reject a
    file that ignores this, so a long description must not be left unfolded."""
    encoded = line.encode("utf-8")
    if len(encoded) <= LINE_LIMIT:
        return line

    chunks: list[str] = []
    current = b""
    for char in line:
        char_bytes = char.encode("utf-8")
        # Continuation lines carry a leading space, so they hold one octet less.
        limit = LINE_LIMIT if not chunks else LINE_LIMIT - 1
        if len(current) + len(char_bytes) > limit:
            chunks.append(current.decode("utf-8"))
            current = b""
        current += char_bytes
    if current:
        chunks.append(current.decode("utf-8"))

    return "\r\n ".join(chunks)


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _date(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _uid(event: Event) -> str:
    # Stable across exports so subscribers update an event rather than duplicating it.
    return f"famcal-{event.id}@family-calendar"


def event_lines(event: Event) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{_uid(event)}", f"DTSTAMP:{_stamp(utcnow_naive())}"]

    if event.all_day:
        # All-day events are DATE values with an exclusive end, which is exactly
        # how they are stored, so no conversion is needed.
        lines.append(f"DTSTART;VALUE=DATE:{_date(event.start_at)}")
        lines.append(f"DTEND;VALUE=DATE:{_date(event.end_at)}")
    else:
        lines.append(f"DTSTART:{_stamp(event.start_at)}")
        lines.append(f"DTEND:{_stamp(event.end_at)}")

    lines.append(f"SUMMARY:{_escape(event.title)}")
    if event.description:
        lines.append(f"DESCRIPTION:{_escape(event.description)}")
    if event.location:
        lines.append(f"LOCATION:{_escape(event.location)}")
    if event.recurrence_rule:
        lines.append(f"RRULE:{event.recurrence_rule}")
    lines.append("END:VEVENT")
    return lines


def build(events: list[Event], name: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        # Tells well-behaved subscribers how often to re-poll. Apple honours the
        # X- form; RFC 7986's REFRESH-INTERVAL covers everyone else.
        "REFRESH-INTERVAL;VALUE=DURATION:PT30M",
        "X-PUBLISHED-TTL:PT30M",
    ]
    for event in events:
        lines.extend(event_lines(event))
    lines.append("END:VCALENDAR")

    # CRLF endings are required, and a trailing one terminates the last line.
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def default_window() -> tuple[datetime, datetime]:
    """What a subscriber gets: recent history plus a year ahead. Unbounded would
    mean re-sending the family's entire past on every poll."""
    now = utcnow_naive()
    return now - timedelta(days=90), now + timedelta(days=365)
