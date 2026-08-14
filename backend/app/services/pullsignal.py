"""Waking the pull loop early.

The mirror image of the push signal in `pushqueue`: outbound changes already wake
their loop the moment somebody saves an event, but inbound ones only arrived on the
5-minute tick. That is the right cadence for background polling and the wrong one for
the moment you assign a calendar to somebody — you are looking straight at the screen,
waiting for their events to appear, and five minutes reads as broken.

So the interval stays at five minutes and this exists to short-circuit it for the one
case where somebody is watching.
"""

import asyncio

_pull_event: asyncio.Event | None = None
_loop: asyncio.AbstractEventLoop | None = None


def register_pull_signal(event: asyncio.Event, loop: asyncio.AbstractEventLoop) -> None:
    global _pull_event, _loop
    _pull_event, _loop = event, loop


def request_pull() -> None:
    """Called from request handlers, which run in a threadpool, so the wakeup has to be
    handed back to the event loop thread. A no-op when the scheduler isn't running --
    sync disabled, or a test — so callers never have to check."""
    if _pull_event is None or _loop is None or _loop.is_closed():
        return
    _loop.call_soon_threadsafe(_pull_event.set)
