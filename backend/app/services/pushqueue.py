import asyncio

from ..models import Calendar, Event

# Set by the push loop at startup. Writing to it wakes the loop immediately instead of
# waiting out the poll interval, so an edit on the wall display reaches Google in seconds.
_push_event: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None


def register_push_signal(event: asyncio.Event, loop: asyncio.AbstractEventLoop) -> None:
    global _push_event, _loop
    _push_event, _loop = event, loop


def request_push() -> None:
    """Called from sync request handlers, which run in a threadpool, so the wakeup has to
    be handed back to the event loop thread."""
    if _push_event is None or _loop is None or _loop.is_closed():
        return
    _loop.call_soon_threadsafe(_push_event.set)


def mark_pending(event: Event, calendar: Calendar, state: str) -> None:
    """Google-backed events go into the push queue; local-only events are already final."""
    if calendar.is_local:
        event.sync_state = "synced"
        return
    if state == "pending_update" and event.sync_state == "pending_create":
        return  # still un-created remotely; keep the stronger state
    event.sync_state = state
