"""Google Calendar, expressed as a CalendarProvider.

Everything Google-shaped lives here: its JSON field names, its cancelled-event
convention, and its habit of describing all-day events with plain dates. The
transport itself is still `google_api.GoogleCalendarClient` -- this only
translates.
"""

from datetime import UTC, datetime

from dateutil import parser as dateparser

from ..google_api import GoogleCalendarClient
from .base import RemoteCalendar, RemoteEvent


class GoogleProvider:
    # Events are requested with singleEvents, so Google hands back the individual
    # occurrences of a series and our copy of the master must stop being drawn.
    expands_recurrence = True

    def __init__(
        self, access_token: str | None = None, client: GoogleCalendarClient | None = None
    ):
        # `client` is how tests substitute a fake without going through a token.
        self._client = client if client is not None else GoogleCalendarClient(access_token or "")

    def list_calendars(self) -> list[RemoteCalendar]:
        return [
            RemoteCalendar(
                id=entry["id"],
                name=entry.get("summary") or "",
                access_role=entry.get("accessRole") or "reader",
            )
            for entry in self._client.list_calendars()
            if entry.get("id")
        ]

    def list_events(
        self,
        calendar_id: str,
        sync_token: str | None = None,
        time_min: str | None = None,
    ) -> tuple[list[RemoteEvent], str | None]:
        items, next_token = self._client.list_events(
            calendar_id, sync_token=sync_token, time_min=time_min
        )
        return [_to_remote(item) for item in items if item.get("id")], next_token

    def create_event(self, calendar_id: str, event: RemoteEvent) -> RemoteEvent:
        return _to_remote(self._client.insert_event(calendar_id, _to_body(event)))

    def update_event(self, calendar_id: str, event: RemoteEvent) -> RemoteEvent:
        return _to_remote(self._client.patch_event(calendar_id, event.id, _to_body(event)))

    def delete_event(self, calendar_id: str, remote_id: str, etag: str | None = None) -> None:
        # Google has no If-Match on this endpoint; the etag is accepted and ignored
        # so the engine can call every provider the same way.
        self._client.delete_event(calendar_id, remote_id)


# ----------------------------- translation -----------------------------------


def _to_remote(item: dict) -> RemoteEvent:
    if item.get("status") == "cancelled":
        return RemoteEvent(id=item.get("id", ""), deleted=True)

    start, end, all_day = _parse_times(item)
    return RemoteEvent(
        id=item.get("id", ""),
        etag=item.get("etag"),
        title=item.get("summary") or "(no title)",
        description=item.get("description"),
        location=item.get("location"),
        start=start,
        end=end,
        all_day=all_day,
        timezone=(item.get("start") or {}).get("timeZone"),
        recurring_event_id=item.get("recurringEventId"),
        updated=_parse_dt(item.get("updated")),
    )


def _to_body(event: RemoteEvent) -> dict:
    if event.all_day:
        start = {"date": event.start.date().isoformat()}
        end = {"date": event.end.date().isoformat()}
    else:
        start = {"dateTime": _iso_utc(event.start)}
        end = {"dateTime": _iso_utc(event.end)}
    body = {
        "summary": event.title,
        "description": event.description,
        "location": event.location,
        "start": start,
        "end": end,
    }
    if event.recurrence_rule:
        # Google owns the expansion from here. Our pull asks for singleEvents, so
        # what comes back are individual instances -- which is why the master gets
        # hidden from queries once this push succeeds.
        body["recurrence"] = [f"RRULE:{event.recurrence_rule}"]
    return body


def _iso_utc(dt: datetime) -> str:
    aware = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = dateparser.isoparse(value)
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


def _parse_times(item: dict) -> tuple[datetime | None, datetime | None, bool]:
    start_obj = item.get("start") or {}
    end_obj = item.get("end") or {}

    if "date" in start_obj:
        # All-day: Google gives plain dates with an exclusive end, which is exactly how
        # they are stored here, so no timezone conversion should happen.
        start = dateparser.isoparse(start_obj["date"])
        end = dateparser.isoparse(end_obj.get("date", start_obj["date"]))
        return start, end, True

    return _parse_dt(start_obj.get("dateTime")), _parse_dt(end_obj.get("dateTime")), False
