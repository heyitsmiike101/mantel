import asyncio
import contextlib
import logging

from ..config import get_settings
from ..db import SessionLocal
from . import sync_engine
from .pushqueue import register_push_signal

log = logging.getLogger(__name__)


async def _pull_loop() -> None:
    interval = get_settings().sync_interval_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            # Google's client is blocking, so it runs off the event loop.
            changed = await asyncio.to_thread(_pull_once)
            if changed:
                log.info("Pulled %s changes from Google", changed)
        except Exception:
            log.exception("Scheduled pull failed")


async def _push_loop(signal: asyncio.Event) -> None:
    interval = get_settings().push_interval_seconds
    while True:
        # Wakes immediately when someone saves an event, otherwise ticks on the interval
        # so a push that failed earlier gets retried.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(signal.wait(), timeout=interval)
        signal.clear()
        try:
            pushed = await asyncio.to_thread(_push_once)
            if pushed:
                log.info("Pushed %s changes to Google", pushed)
        except Exception:
            log.exception("Scheduled push failed")


def _pull_once() -> int:
    with SessionLocal() as db:
        return sync_engine.pull_all(db)


def _push_once() -> int:
    with SessionLocal() as db:
        return sync_engine.push_pending(db)


def start(loop: asyncio.AbstractEventLoop) -> list[asyncio.Task]:
    if not get_settings().sync_enabled:
        log.info("Google sync is disabled (SYNC_ENABLED=false)")
        return []
    signal = asyncio.Event()
    register_push_signal(signal, loop)
    return [asyncio.create_task(_pull_loop()), asyncio.create_task(_push_loop(signal))]


async def stop(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task
