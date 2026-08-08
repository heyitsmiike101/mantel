from app.services.google_api import GoogleApiError, SyncTokenExpired


class FakeGoogle:
    """Stands in for Google Calendar. Records what was sent so push behavior can be
    asserted, and can be told to expire a sync token or fail a call."""

    def __init__(self):
        self.calendars: list[dict] = []
        self.pages: list[tuple[list[dict], str | None]] = []
        self.expire_next_sync_token = False
        self.inserted: list[dict] = []
        self.patched: list[tuple[str, dict]] = []
        self.deleted: list[str] = []
        self.next_id = 1
        self.fail_patch_with: int | None = None
        self.fail_delete_with: int | None = None
        self.last_time_min: str | None = None
        self.last_sync_token: str | None = None

    # -- the interface GoogleCalendarClient presents ---------------------------
    # This sits *below* the provider boundary, so tests using it also exercise the
    # JSON translation in GoogleProvider rather than skipping past it.

    def list_calendars(self) -> list[dict]:
        return self.calendars

    def list_events(self, calendar_id, sync_token=None, time_min=None):
        self.last_sync_token = sync_token
        self.last_time_min = time_min
        if sync_token and self.expire_next_sync_token:
            self.expire_next_sync_token = False
            raise SyncTokenExpired(410, "sync token expired")
        if not self.pages:
            return [], "token-empty"
        return self.pages.pop(0)

    def insert_event(self, calendar_id, body):
        gid = f"g{self.next_id}"
        self.next_id += 1
        self.inserted.append({"calendar_id": calendar_id, "body": body, "id": gid})
        return {"id": gid, "etag": '"e1"', "updated": "2026-07-30T12:00:00Z", **body}

    def patch_event(self, calendar_id, event_id, body):
        if self.fail_patch_with:
            status, self.fail_patch_with = self.fail_patch_with, None
            raise GoogleApiError(status, "patch failed")
        self.patched.append((event_id, body))
        return {"id": event_id, "etag": '"e2"', "updated": "2026-07-30T13:00:00Z", **body}

    def get_event(self, calendar_id, event_id):
        return {"id": event_id}

    def delete_event(self, calendar_id, event_id):
        if self.fail_delete_with:
            status, self.fail_delete_with = self.fail_delete_with, None
            raise GoogleApiError(status, "delete failed")
        self.deleted.append(event_id)


def gevent(gid: str, summary: str, start: str, end: str, **extra) -> dict:
    return {
        "id": gid,
        "summary": summary,
        "status": "confirmed",
        "etag": '"etag"',
        "updated": "2026-07-30T10:00:00Z",
        "start": {"dateTime": start},
        "end": {"dateTime": end},
        **extra,
    }


def gallday(gid: str, summary: str, start: str, end: str) -> dict:
    return {
        "id": gid,
        "summary": summary,
        "status": "confirmed",
        "etag": '"etag"',
        "updated": "2026-07-30T10:00:00Z",
        "start": {"date": start},
        "end": {"date": end},
    }
