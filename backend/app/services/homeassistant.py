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
    """Same, off the request path.

    A write handler must not wait on someone else's server -- if HA is powered
    off, saving an event should still feel instant.
    """
    if not (base_url and token and entity_id):
        return
    threading.Thread(
        target=notify, args=(base_url, token, entity_id), daemon=True
    ).start()


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
