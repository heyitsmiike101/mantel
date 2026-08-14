"""What the sync engine needs from a calendar service.

Google Calendar and CalDAV agree on more than they disagree on: a list of
calendars, a stream of changed events, an opaque cursor meaning "what changed
since", and create/update/delete. Everything below is that common shape, so the
engine can hold the interesting logic -- conflict resolution, the pending-push
queue, full-resync recovery -- exactly once.

Two differences genuinely leak, and are named here rather than being rediscovered
inside the engine:

* `expands_recurrence` -- Google is asked for `singleEvents`, so it returns the
  individual occurrences of a series. CalDAV returns the master with its RRULE and
  expects the client to expand it. That decides whether a pushed series keeps
  being displayed locally (`Event.is_master`).
* `RemoteEvent.id` -- an opaque per-calendar handle. Google's event id, or a
  CalDAV resource filename. The engine only ever compares and stores it.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

# Separates a resource id from the single occurrence it identifies, for providers
# where one remote resource carries a whole series: the master plus every
# occurrence somebody has since moved or renamed. CalDAV works this way; Google
# does not, and simply never puts this character in an id. The engine needs to
# know the convention so it can find every row belonging to a resource -- see
# `sync_engine._forget_resource`.
OCCURRENCE_SEP = "#"


class ProviderError(Exception):
    """The remote service refused a request."""

    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class SyncTokenExpired(ProviderError):
    """The stored incremental cursor is too old to use.

    Google answers 410; CalDAV answers 403 with a DAV:valid-sync-token
    precondition. Same meaning and the same recovery -- drop what that provider
    gave us and pull the window again -- so the engine handles one exception.
    """


class ProviderAuthError(Exception):
    """The stored credentials no longer work; the account has to be re-linked."""


@dataclass(slots=True)
class RemoteCalendar:
    """One calendar as the provider describes it.

    `name` is deliberately allowed to be empty. Neither service guarantees a
    title, and the engine would rather keep the name already on record than
    overwrite it with a placeholder.
    """

    id: str
    name: str = ""
    access_role: str = "reader"  # "owner" | "writer" | "reader"


@dataclass(slots=True)
class RemoteEvent:
    """One event, in the vocabulary this app stores rather than either service's.

    Times are naive UTC to match the database (see `models.utcnow`), except for
    all-day events, whose `start`/`end` are naive dates with an *exclusive* end --
    which is how Google and iCalendar both express them, so no conversion happens
    on that path at all.
    """

    id: str
    etag: str | None = None
    # The provider is reporting this event as gone: Google's status=cancelled, or a
    # 404 member in a CalDAV sync report. No other field is meaningful.
    deleted: bool = False
    title: str = ""
    description: str | None = None
    location: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    all_day: bool = False
    timezone: str | None = None
    recurrence_rule: str | None = None  # RRULE body, no "RRULE:" prefix
    recurring_event_id: str | None = None
    exdates: list[datetime] = field(default_factory=list)
    updated: datetime | None = None


class CalendarProvider(Protocol):
    """The surface `sync_engine` is written against."""

    expands_recurrence: bool

    def list_calendars(self) -> list[RemoteCalendar]: ...

    def list_events(
        self,
        calendar_id: str,
        sync_token: str | None = None,
        time_min: str | None = None,
    ) -> tuple[list[RemoteEvent], str | None]:
        """Returns (events, next_sync_token).

        With a `sync_token` this is incremental and must include deletions, so a
        removal made elsewhere propagates. Without one it is a fresh read of the
        window starting at `time_min`.
        """
        ...

    def create_event(self, calendar_id: str, event: RemoteEvent) -> RemoteEvent: ...

    def update_event(self, calendar_id: str, event: RemoteEvent) -> RemoteEvent:
        """`event.id` identifies the remote copy; `event.etag` guards the write."""
        ...

    def delete_event(
        self, calendar_id: str, remote_id: str, etag: str | None = None
    ) -> None: ...
