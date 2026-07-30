from .models import Calendar, Event
from .schemas import CalendarOut, EventOut
from .services.recurrence import describe
from .timeutil import as_utc

UNCLAIMED_COLOR = "#64748b"


def calendar_color(cal: Calendar) -> str:
    if cal.color_override:
        return cal.color_override
    if cal.claimed_by is not None:
        return cal.claimed_by.color
    return UNCLAIMED_COLOR


def calendar_out(cal: Calendar) -> CalendarOut:
    return CalendarOut(
        id=cal.id,
        name=cal.name,
        is_local=cal.is_local,
        google_calendar_id=cal.google_calendar_id,
        linked_account_id=cal.linked_account_id,
        account_email=cal.account.email if cal.account else None,
        claimed_by_user_id=cal.claimed_by_user_id,
        color=calendar_color(cal),
        sync_enabled=cal.sync_enabled,
        access_role=cal.access_role,
        writable=cal.writable,
        last_synced_at=as_utc(cal.last_synced_at),
        sync_error=cal.sync_error,
    )


def event_out(ev: Event) -> EventOut:
    cal = ev.calendar
    return EventOut(
        id=ev.id,
        calendar_id=ev.calendar_id,
        calendar_name=cal.name,
        color=calendar_color(cal),
        user_id=cal.claimed_by_user_id,
        title=ev.title,
        description=ev.description,
        location=ev.location,
        start_at=as_utc(ev.start_at),
        end_at=as_utc(ev.end_at),
        all_day=ev.all_day,
        timezone=ev.timezone,
        recurring=ev.recurring_event_id is not None or ev.recurrence_rule is not None,
        recurrence_rule=ev.recurrence_rule,
        recurrence_text=describe(ev.recurrence_rule),
        origin=ev.origin,
        sync_state=ev.sync_state,
        editable=cal.writable,
    )
