"""Home Assistant push notification.

HA's Remote Calendar integration polls an ICS feed on a **hard-coded 24-hour**
interval, which would make a family calendar useless inside HA. The escape hatch
is HA's own documented one: disable polling for that entity, then call
`homeassistant.update_entity` whenever the data changes.

So this module exists to fire that one service call after a write. The result is
a sub-second, push-updated calendar entity in Home Assistant with **no custom
integration running inside HA** -- which is why v0.2.0 ships this instead of a
HACS component that would need maintaining against every HA release.

Everything here is fire-and-forget: Home Assistant being down must never make
saving an event fail.
"""

import logging
import threading

import httpx

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 8.0

# How long to gather further changes before sending. A bulk import through the
# API produces hundreds of writes in a second; the nudge is idempotent, so they
# should collapse into one call rather than one thread each.
DEBOUNCE_SECONDS = 1.0

_worker: threading.Thread | None = None
_wake = threading.Event()
_lock = threading.Lock()
_pending: tuple[str, str, str] | None = None


def notify(base_url: str, token: str, entity_id: str) -> None:
    """Ask HA to refresh a calendar entity now. Never raises."""
    if not (base_url and token and entity_id):
        return

    url = f"{base_url.rstrip('/')}/api/services/homeassistant/update_entity"
    try:
        httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"entity_id": entity_id},
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 -- a nudge failing is not an app error
        log.warning("Home Assistant refresh failed: %s", exc)


def notify_async(base_url: str, token: str, entity_id: str) -> None:
    """Queue a refresh, off the request path.

    A write handler must not wait on someone else's server -- if HA is powered
    off, saving an event should still feel instant. Calls coalesce onto a single
    long-lived worker: importing a season's worth of fixtures through the API
    must not spawn a thread per event.
    """
    global _worker

    if not (base_url and token and entity_id):
        return

    with _lock:
        globals()["_pending"] = (base_url, token, entity_id)
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="ha-notify", daemon=True)
            _worker.start()
    _wake.set()


def _run() -> None:
    """Drain queued nudges forever, collapsing bursts into one call."""
    while True:
        # No pending work: park until something arrives. The timeout lets an idle
        # worker exit so a long-running server isn't holding a thread for nothing.
        if not _wake.wait(timeout=300):
            with _lock:
                if _pending is None:
                    return
        _wake.clear()

        # Let a burst finish arriving before sending.
        threading.Event().wait(DEBOUNCE_SECONDS)

        with _lock:
            target = _pending
            globals()["_pending"] = None
        if target is not None:
            notify(*target)


def test_connection(base_url: str, token: str) -> tuple[bool, str]:
    """Used by the settings screen so misconfiguration is visible immediately
    rather than as silently missing updates weeks later."""
    if not base_url or not token:
        return False, "Enter both the Home Assistant URL and a long-lived access token."
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not reach Home Assistant: {exc}"

    if response.status_code == 401:
        return False, "Home Assistant rejected the token."
    if response.status_code >= 400:
        return False, f"Home Assistant returned {response.status_code}."
    return True, "Connected to Home Assistant."
