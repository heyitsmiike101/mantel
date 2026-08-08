import httpx

from .providers.base import ProviderError, SyncTokenExpired

BASE = "https://www.googleapis.com/calendar/v3"

# Google's failures are just provider failures. Keeping the old name as an alias
# means one `except` in the engine covers every provider, while the call sites and
# tests that say "GoogleApiError" still read like they mean it.
GoogleApiError = ProviderError

__all__ = ["BASE", "GoogleApiError", "GoogleCalendarClient", "SyncTokenExpired"]


class GoogleCalendarClient:
    """Thin wrapper over the Calendar REST API. Kept dependency-free and synchronous so it
    is trivial to fake in tests -- the sync logic is what needs covering, not Google."""

    def __init__(self, access_token: str, http: httpx.Client | None = None):
        self._token = access_token
        self._http = http or httpx.Client(timeout=60)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._http.request(
            method,
            f"{BASE}{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            **kwargs,
        )
        if resp.status_code == 410:
            raise SyncTokenExpired(410, resp.text)
        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            raise GoogleApiError(resp.status_code, resp.text)
        return resp.json()

    def list_calendars(self) -> list[dict]:
        items: list[dict] = []
        page_token = None
        while True:
            params = {"maxResults": 250}
            if page_token:
                params["pageToken"] = page_token
            data = self._request("GET", "/users/me/calendarList", params=params)
            items.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                return items

    def list_events(
        self,
        calendar_id: str,
        sync_token: str | None = None,
        time_min: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """Returns (events, next_sync_token). With a sync_token this is incremental and
        includes cancelled events so deletions propagate."""
        items: list[dict] = []
        page_token = None
        next_sync_token = None
        while True:
            params: dict[str, object] = {"maxResults": 2500, "singleEvents": True}
            if sync_token:
                params["syncToken"] = sync_token
            else:
                params["showDeleted"] = False
                if time_min:
                    params["timeMin"] = time_min
            if page_token:
                params["pageToken"] = page_token

            data = self._request("GET", f"/calendars/{_q(calendar_id)}/events", params=params)
            items.extend(data.get("items", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                next_sync_token = data.get("nextSyncToken")
                return items, next_sync_token

    def insert_event(self, calendar_id: str, body: dict) -> dict:
        return self._request("POST", f"/calendars/{_q(calendar_id)}/events", json=body)

    def patch_event(self, calendar_id: str, event_id: str, body: dict) -> dict:
        return self._request(
            "PATCH", f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}", json=body
        )

    def get_event(self, calendar_id: str, event_id: str) -> dict:
        return self._request("GET", f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}")

    def delete_event(self, calendar_id: str, event_id: str) -> None:
        self._request("DELETE", f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}")


def _q(value: str) -> str:
    return httpx.URL(path=f"/{value}").path[1:]
