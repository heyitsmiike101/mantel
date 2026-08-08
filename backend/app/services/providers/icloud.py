"""iCloud, expressed as a CalendarProvider.

Everything iCalendar-shaped lives here: VEVENT properties, the difference between
a date and a datetime, and the fact that one CalDAV resource can hold a whole
recurring series -- the master plus every occurrence somebody has since moved or
renamed. The transport is `caldav_client`; this only translates.

The important asymmetry with Google: Google is asked for `singleEvents` and hands
back individual occurrences, so it owns the expansion. CalDAV hands back the
master with its RRULE and expects the client to expand it -- which this app
already does for its own local events, in `services/recurrence.py`. So iCloud
series are stored as masters and expanded here, and `expands_recurrence` is False.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import parser as dateparser
from icalendar import Calendar as ICalendar
from icalendar import Event as IEvent

from ..caldav_client import CalDavClient
from .base import OCCURRENCE_SEP, ProviderError, RemoteCalendar, RemoteEvent

log = logging.getLogger(__name__)

PRODID = "-//Mantel//Family Calendar//EN"


class ICloudProvider:
    # CalDAV returns the master untouched, so our copy stays the one that is drawn
    # and `recurrence.py` expands it. See the module docstring.
    expands_recurrence = False

    def __init__(self, client: CalDavClient, home_url: str, home_timezone: str = "UTC"):
        self._dav = client
        self._home = home_url
        self._tz = _zone(home_timezone)

    # ------------------------------ calendars --------------------------------

    def list_calendars(self) -> list[RemoteCalendar]:
        return [
            RemoteCalendar(id=cal.path, name=cal.name, access_role=cal.access_role)
            for cal in self._dav.list_calendars(self._home)
        ]

    # -------------------------------- reading --------------------------------

    def list_events(
        self,
        calendar_id: str,
        sync_token: str | None = None,
        time_min: str | None = None,
    ) -> tuple[list[RemoteEvent], str | None]:
        collection = self._collection(calendar_id)

        if sync_token:
            changed, next_token = self._dav.sync_collection(collection, sync_token)
            deleted = [RemoteEvent(id=_name_of(r.href), deleted=True) for r in changed if r.deleted]
            wanted = [r.href for r in changed if not r.deleted]
            return deleted + self._fetch_events(collection, wanted), next_token

        # Take the cursor *before* reading, never after. A change landing between
        # the two requests is then reported again by the next delta and re-applied
        # harmlessly; the other order drops it on the floor for good.
        next_token = self._dav.baseline_sync_token(collection)
        hrefs = self._dav.list_hrefs_in_window(collection, _window_start(time_min))
        return self._fetch_events(collection, [r.href for r in hrefs]), next_token

    def _fetch_events(self, collection: str, hrefs: list[str]) -> list[RemoteEvent]:
        if not hrefs:
            return []
        out: list[RemoteEvent] = []
        for resource in self._dav.fetch(collection, hrefs):
            try:
                out.extend(self._parse(resource.href, resource.etag, resource.data))
            except Exception as exc:  # noqa: BLE001 - one bad event must not stop the sync
                log.warning("Skipping unreadable event %s: %s", resource.href, exc)
        return out

    def _parse(self, href: str, etag: str | None, ics: str | None) -> list[RemoteEvent]:
        if not ics:
            return []
        name = _name_of(href)
        components = [c for c in ICalendar.from_ical(ics).walk("VEVENT")]

        master: RemoteEvent | None = None
        overrides: list[RemoteEvent] = []
        override_starts: list[datetime] = []

        for component in components:
            recurrence_id = component.get("RECURRENCE-ID")
            if recurrence_id is None:
                master = self._from_vevent(component, id=name, etag=etag)
                continue

            moment = self._naive_utc(recurrence_id.dt)
            override_starts.append(moment)
            overrides.append(
                self._from_vevent(
                    component,
                    id=f"{name}{OCCURRENCE_SEP}{_occurrence_key(recurrence_id.dt)}",
                    etag=etag,
                    recurring_event_id=name,
                )
            )

        if master is None:
            # An orphan override: the series master is outside the window we asked
            # for. The occurrence is still real, so keep it.
            return overrides

        # Every override is also drawn by the master's rule unless it is excluded.
        # The server does not send an EXDATE for these -- the RECURRENCE-ID *is* the
        # exclusion -- so without this each moved occurrence appears twice.
        master.exdates = sorted(set(master.exdates) | set(override_starts))
        return [master, *overrides]

    def _from_vevent(
        self,
        component,
        id: str,
        etag: str | None,
        recurring_event_id: str | None = None,
    ) -> RemoteEvent:
        start_prop = component.get("DTSTART")
        if start_prop is None:
            raise ValueError("VEVENT has no DTSTART")

        raw_start = start_prop.dt
        all_day = isinstance(raw_start, date) and not isinstance(raw_start, datetime)
        start = self._naive_utc(raw_start)
        end = self._end_of(component, raw_start, start, all_day)

        return RemoteEvent(
            id=id,
            etag=etag,
            title=_text(component.get("SUMMARY")) or "(no title)",
            description=_text(component.get("DESCRIPTION")),
            location=_text(component.get("LOCATION")),
            start=start,
            end=end,
            all_day=all_day,
            timezone=_tzid_of(start_prop),
            recurrence_rule=_rrule_of(component),
            recurring_event_id=recurring_event_id,
            exdates=[self._naive_utc(d) for d in _exdates_of(component)],
            updated=self._naive_utc(
                _dt_of(component.get("LAST-MODIFIED")) or _dt_of(component.get("DTSTAMP"))
            ),
        )

    def _end_of(self, component, raw_start, start: datetime, all_day: bool) -> datetime:
        end_prop = component.get("DTEND")
        if end_prop is not None:
            return self._naive_utc(end_prop.dt)

        duration = component.get("DURATION")
        if duration is not None:
            return start + duration.dt

        # RFC 5545: a day-long event with no end lasts one day; a timed one is
        # instantaneous. Both still need an end here, because the calendar query
        # selects on it.
        return start + timedelta(days=1) if all_day else start

    def _naive_utc(self, value):
        """Everything in this database is naive UTC; all-day dates stay dates."""
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                # A floating time means "whatever the clock says where you are".
                # Reading it as UTC would shift the school run by hours.
                return value.replace(tzinfo=self._tz).astimezone(UTC).replace(tzinfo=None)
            return value.astimezone(UTC).replace(tzinfo=None)
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        return None

    # -------------------------------- writing --------------------------------

    def create_event(self, calendar_id: str, event: RemoteEvent) -> RemoteEvent:
        collection = self._collection(calendar_id)
        name = _new_resource_name()
        # The UID and the filename are the same thing for events this app creates.
        # Nothing requires that, but it makes a resource identifiable from its name
        # alone when reading server logs.
        uid = name.removesuffix(".ics")

        url = self._dav.resolve(collection, name)
        etag = self._dav.put(url, _build_vcalendar(event, uid), create=True)
        return RemoteEvent(id=name, etag=etag or self._reread_etag(url), updated=_now())

    def update_event(self, calendar_id: str, event: RemoteEvent) -> RemoteEvent:
        """Edits the existing resource in place rather than replacing it.

        A VEVENT carries far more than this app models -- alarms, guests,
        categories, the original UID. Rebuilding it from our fields would silently
        throw all of that away, so somebody renaming an event on the wall display
        would delete the reminder they set on their phone. So: read it, change the
        handful of properties we own, and write it back.
        """
        collection = self._collection(calendar_id)
        name, occurrence = _split_id(event.id)
        url = self._dav.resolve(collection, name)

        resource = self._dav.get(url)
        calendar = ICalendar.from_ical(resource.data)
        component = _component_for(calendar, occurrence)
        if component is None:
            raise ProviderError(404, "That event is no longer in the calendar")

        _apply(component, event)
        etag = self._write(url, calendar, resource.etag)
        return RemoteEvent(id=event.id, etag=etag, updated=_now())

    def delete_event(self, calendar_id: str, remote_id: str, etag: str | None = None) -> None:
        collection = self._collection(calendar_id)
        name, occurrence = _split_id(remote_id)
        url = self._dav.resolve(collection, name)

        if occurrence is None:
            self._dav.delete(url, etag)
            return

        # One occurrence of a series. The resource stays; the moved copy is removed
        # and the date excluded, which is how iCalendar says "this one is cancelled".
        # Deleting the resource here would silently cancel the whole series.
        resource = self._dav.get(url)
        calendar = ICalendar.from_ical(resource.data)
        component = _component_for(calendar, occurrence)
        if component is not None:
            calendar.subcomponents.remove(component)

        master = _component_for(calendar, None)
        if master is None:
            # Nothing left to exclude the occurrence from.
            self._dav.delete(url, resource.etag)
            return

        _exclude(master, component, occurrence)
        self._write(url, calendar, resource.etag)

    # -------------------------------- helpers --------------------------------

    def _write(self, url: str, calendar: ICalendar, etag: str | None) -> str | None:
        """PUT with If-Match, re-reading once if somebody got there first.

        A 412 means the resource changed between our read and our write. This app's
        rule everywhere else is last write wins, so re-read and apply -- but only
        once, so a genuinely contended resource fails and is retried by the queue
        rather than spinning here.
        """
        body = calendar.to_ical().decode()
        try:
            new_etag = self._dav.put(url, body, etag=etag)
        except ProviderError as exc:
            if exc.status != 412:
                raise
            new_etag = self._dav.put(url, body, etag=self._dav.get(url).etag)
        return new_etag or self._reread_etag(url)

    def _reread_etag(self, url: str) -> str | None:
        """The spec lets a PUT answer without an ETag, and iCloud sometimes does.
        Leaving it unset means the next update sends a stale If-Match and 412s."""
        try:
            return self._dav.get(url).etag
        except ProviderError:
            return None

    # -------------------------------- helpers --------------------------------

    def _collection(self, calendar_id: str) -> str:
        return self._dav.resolve(self._home, calendar_id)


# ------------------------------ iCalendar bits -------------------------------


def _text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tzid_of(prop) -> str | None:
    tzid = getattr(prop, "params", {}).get("TZID")
    return str(tzid) if tzid else None


def _rrule_of(component) -> str | None:
    rule = component.get("RRULE")
    if rule is None:
        return None
    # A component may legally carry several; this app stores one, and the first is
    # the one Apple's own UI writes.
    if isinstance(rule, list):
        rule = rule[0]
    return rule.to_ical().decode().strip() or None


def _exdates_of(component) -> list:
    raw = component.get("EXDATE")
    if raw is None:
        return []
    groups = raw if isinstance(raw, list) else [raw]
    return [item.dt for group in groups for item in getattr(group, "dts", [])]


def _dt_of(prop):
    return prop.dt if prop is not None else None


def _occurrence_key(value) -> str:
    """A stable, filename-safe name for one occurrence of a series."""
    if isinstance(value, datetime):
        moment = value.astimezone(UTC) if value.tzinfo else value
        return moment.strftime("%Y%m%dT%H%M%SZ")
    return value.strftime("%Y%m%d")


def _split_id(remote_id: str) -> tuple[str, str | None]:
    """Splits a stored id into its resource and, if it names one, its occurrence."""
    name, sep, occurrence = remote_id.partition(OCCURRENCE_SEP)
    return name, (occurrence if sep else None)


def _component_for(calendar: ICalendar, occurrence: str | None):
    """The master VEVENT, or the override for one occurrence."""
    for component in calendar.walk("VEVENT"):
        recurrence_id = component.get("RECURRENCE-ID")
        if occurrence is None:
            if recurrence_id is None:
                return component
        elif recurrence_id is not None and _occurrence_key(recurrence_id.dt) == occurrence:
            return component
    return None


def _exclude(master, removed, occurrence: str) -> None:
    """Adds the occurrence to the master's EXDATE list.

    Appended to whatever is already there rather than replacing it, or cancelling
    a second week would quietly reinstate the first.
    """
    moment = None
    if removed is not None and removed.get("RECURRENCE-ID") is not None:
        moment = removed["RECURRENCE-ID"].dt
    else:
        moment = _parse_occurrence_key(occurrence)
    if moment is None:
        return

    existing = _exdates_of(master)
    master.pop("EXDATE", None)
    for value in [*existing, moment]:
        master.add("exdate", value)


def _parse_occurrence_key(key: str):
    for pattern, kind in (("%Y%m%dT%H%M%SZ", "dt"), ("%Y%m%d", "date")):
        try:
            parsed = datetime.strptime(key, pattern)
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC) if kind == "dt" else parsed.date()
    return None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _name_of(href: str) -> str:
    """The resource filename. Stored rather than the full path, so that moving a
    collection does not orphan every event in it."""
    return href.rstrip("/").rsplit("/", 1)[-1]


def _window_start(time_min: str | None) -> datetime:
    if not time_min:
        return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=90)
    parsed = dateparser.isoparse(time_min)
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Unknown home timezone %r; treating floating times as UTC", name)
        return ZoneInfo("UTC")


def _new_resource_name() -> str:
    return f"{uuid.uuid4().hex.upper()}.ics"


def _build_vcalendar(event: RemoteEvent, uid: str) -> str:
    cal = ICalendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add_component(_build_vevent(event, uid))
    return cal.to_ical().decode()


def _build_vevent(event: RemoteEvent, uid: str) -> IEvent:
    component = IEvent()
    component.add("uid", uid)
    _apply(component, event)
    return component


def _apply(component, event: RemoteEvent) -> None:
    """Writes this app's fields onto a VEVENT, leaving everything else alone.

    Only the properties the app actually owns are touched, so an alarm or a guest
    list somebody set on their phone survives an edit made on the wall display.
    """
    for name in ("SUMMARY", "DESCRIPTION", "LOCATION", "DTSTART", "DTEND", "RRULE", "DURATION"):
        component.pop(name, None)

    component.add("summary", event.title or "(no title)")
    if event.description:
        component.add("description", event.description)
    if event.location:
        component.add("location", event.location)

    if event.all_day:
        component.add("dtstart", event.start.date())
        component.add("dtend", event.end.date())
    else:
        component.add("dtstart", event.start.replace(tzinfo=UTC))
        component.add("dtend", event.end.replace(tzinfo=UTC))

    if event.recurrence_rule:
        component.add("rrule", _vrecur(event.recurrence_rule))

    component.pop("DTSTAMP", None)
    component.add("dtstamp", datetime.now(UTC))
    component.pop("LAST-MODIFIED", None)
    component.add("last-modified", datetime.now(UTC))


def _vrecur(rule: str):
    from icalendar.prop import vRecur

    try:
        return vRecur.from_ical(rule)
    except ValueError as exc:
        raise ProviderError(0, f"Could not express the repeat rule in iCalendar: {exc}") from exc
