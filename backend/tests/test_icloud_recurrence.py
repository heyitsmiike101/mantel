"""Recurring events from iCloud.

The hardest part of the feature, and the one with the most ways to look broken on
a wall display. CalDAV hands over a whole series as one resource: the master with
its rule, plus a separate component for every occurrence somebody has moved or
renamed. Get any of it wrong and an event shows twice, or a cancelled one never
goes away.

These go through the real list endpoint rather than inspecting rows, because
"what does the family actually see" is the thing that matters.
"""

from datetime import datetime

import pytest
from fake_caldav import CALENDAR, PARTITION_HOST, FakeCalDav

from app.models import Calendar, Event, LinkedAccount, User
from app.services import sync_engine
from app.services.caldav_client import CalDavClient
from app.services.crypto import encrypt
from app.services.providers.icloud import ICloudProvider

WINDOW = {"start": "2026-08-01T00:00:00Z", "end": "2026-09-01T00:00:00Z"}


@pytest.fixture
def server():
    return FakeCalDav()


@pytest.fixture
def provider(server, monkeypatch):
    def build(db, account):
        dav = CalDavClient("someone@icloud.com", "pw", http=server.client())
        return ICloudProvider(dav, f"{PARTITION_HOST}/1234567890/calendars/", "UTC")

    monkeypatch.setattr(sync_engine, "provider_factory", build)


@pytest.fixture
def icloud(client, db, provider):
    user = User(name="Mike", color="#3b82f6")
    db.add(user)
    db.flush()
    account = LinkedAccount(
        user_id=user.id,
        provider="icloud",
        email="mike@icloud.com",
        password_enc=encrypt("pw"),
        calendar_home_url=f"{PARTITION_HOST}/1234567890/calendars/",
    )
    db.add(account)
    db.flush()
    cal = Calendar(
        linked_account_id=account.id,
        google_calendar_id=CALENDAR,
        name="Home",
        claimed_by_user_id=user.id,
        sync_enabled=True,
        access_role="writer",
    )
    db.add(cal)
    db.commit()
    return cal


def series(rrule="FREQ=WEEKLY;COUNT=4", extra="", components=""):
    """A weekly Monday series starting 3 Aug 2026, plus whatever else is asked for."""
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:swim\r\nSUMMARY:Swimming\r\n"
        "DTSTART:20260803T170000Z\r\nDTEND:20260803T180000Z\r\n"
        "DTSTAMP:20260730T100000Z\r\nLAST-MODIFIED:20260730T100000Z\r\n"
        f"RRULE:{rrule}\r\n{extra}END:VEVENT\r\n"
        f"{components}END:VCALENDAR\r\n"
    )


def override(recurrence_id, summary, start, end):
    return (
        f"BEGIN:VEVENT\r\nUID:swim\r\nRECURRENCE-ID:{recurrence_id}\r\n"
        f"SUMMARY:{summary}\r\nDTSTART:{start}\r\nDTEND:{end}\r\n"
        "DTSTAMP:20260730T100000Z\r\nLAST-MODIFIED:20260730T110000Z\r\n"
        "END:VEVENT\r\n"
    )


def listed(client):
    return client.get("/api/events", params=WINDOW).json()


# ------------------------------ the plain case -------------------------------


def test_a_master_is_stored_once_and_expanded_locally(client, db, provider, icloud, server):
    """CalDAV does not expand, so the master stays visible and this app expands it.
    The opposite of the Google path, and the reason is_master is per-provider."""
    server.add_event("swim.ics", series())
    sync_engine.pull_calendar(db, icloud)

    stored = db.query(Event).one()
    assert stored.recurrence_rule == "FREQ=WEEKLY;COUNT=4"
    assert stored.is_master is False, "nothing else will draw this series"

    assert [e["start_at"][:10] for e in listed(client)] == [
        "2026-08-03",
        "2026-08-10",
        "2026-08-17",
        "2026-08-24",
    ]


def test_a_finite_series_records_when_it_ends(client, db, provider, icloud, server):
    """Stored so a series that finished years ago is skipped in SQL rather than
    loaded and re-expanded on every calendar request."""
    server.add_event("swim.ics", series())
    sync_engine.pull_calendar(db, icloud)

    assert db.query(Event).one().recurrence_end == datetime(2026, 8, 24, 18, 0)


def test_an_endless_series_records_no_end(client, db, provider, icloud, server):
    server.add_event("swim.ics", series(rrule="FREQ=WEEKLY"))
    sync_engine.pull_calendar(db, icloud)

    assert db.query(Event).one().recurrence_end is None


# --------------------------------- EXDATE ------------------------------------


def test_a_cancelled_occurrence_stops_being_shown(client, db, provider, icloud, server):
    """Somebody deleted one week on their phone. Without EXDATE handling it keeps
    appearing on the wall for good."""
    server.add_event("swim.ics", series(extra="EXDATE:20260810T170000Z\r\n"))
    sync_engine.pull_calendar(db, icloud)

    assert [e["start_at"][:10] for e in listed(client)] == [
        "2026-08-03",
        "2026-08-17",
        "2026-08-24",
    ]


def test_several_cancelled_occurrences(client, db, provider, icloud, server):
    server.add_event(
        "swim.ics", series(extra="EXDATE:20260810T170000Z,20260824T170000Z\r\n")
    )
    sync_engine.pull_calendar(db, icloud)

    assert [e["start_at"][:10] for e in listed(client)] == ["2026-08-03", "2026-08-17"]


def test_reinstating_an_occurrence_brings_it_back(client, db, provider, icloud, server):
    href = server.add_event("swim.ics", series(extra="EXDATE:20260810T170000Z\r\n"))
    sync_engine.pull_calendar(db, icloud)
    assert len(listed(client)) == 3

    server.resources[href] = ('"e2"', series())
    server.changed = [(href, False)]
    sync_engine.pull_calendar(db, icloud)

    assert len(listed(client)) == 4


# ------------------------------- overrides -----------------------------------


def test_a_moved_occurrence_appears_once_at_its_new_time(client, db, provider, icloud, server):
    """The bug this design exists to prevent. iCloud sends no EXDATE for a moved
    occurrence -- the RECURRENCE-ID is the exclusion -- so without synthesizing one
    the week shows twice: at the old time from the rule, and at the new time."""
    server.add_event(
        "swim.ics",
        series(components=override("20260810T170000Z", "Swimming (late)",
                                   "20260810T190000Z", "20260810T200000Z")),
    )
    sync_engine.pull_calendar(db, icloud)

    events = listed(client)
    on_the_tenth = [e for e in events if e["start_at"].startswith("2026-08-10")]
    assert len(on_the_tenth) == 1, "the rule must not also draw the original slot"
    assert on_the_tenth[0]["title"] == "Swimming (late)"
    assert on_the_tenth[0]["start_at"].startswith("2026-08-10T19:00")
    assert len(events) == 4, "still four weeks in total"


def test_an_override_is_its_own_row_tied_to_the_series(client, db, provider, icloud, server):
    server.add_event(
        "swim.ics",
        series(components=override("20260810T170000Z", "Swimming (late)",
                                   "20260810T190000Z", "20260810T200000Z")),
    )
    sync_engine.pull_calendar(db, icloud)

    rows = {e.remote_id: e for e in db.query(Event)}
    assert set(rows) == {"swim.ics", "swim.ics#20260810T170000Z"}
    assert rows["swim.ics#20260810T170000Z"].recurring_event_id == "swim.ics"
    assert rows["swim.ics#20260810T170000Z"].recurrence_rule is None


def test_moving_an_occurrence_back_removes_its_row(client, db, provider, icloud, server):
    """A resource arrives whole, so an override that is gone is simply absent --
    there is no deletion to report. It has to be noticed by its absence."""
    href = server.add_event(
        "swim.ics",
        series(components=override("20260810T170000Z", "Swimming (late)",
                                   "20260810T190000Z", "20260810T200000Z")),
    )
    sync_engine.pull_calendar(db, icloud)
    assert db.query(Event).count() == 2

    server.resources[href] = ('"e2"', series())
    server.changed = [(href, False)]
    sync_engine.pull_calendar(db, icloud)

    assert [e.remote_id for e in db.query(Event)] == ["swim.ics"]
    assert [e["start_at"][:10] for e in listed(client)] == [
        "2026-08-03",
        "2026-08-10",
        "2026-08-17",
        "2026-08-24",
    ]


def test_pruning_leaves_a_queued_local_edit_alone(client, db, provider, icloud, server):
    """The guard that stops a background pull destroying an unpushed change."""
    href = server.add_event("swim.ics", series())
    sync_engine.pull_calendar(db, icloud)

    mine = Event(
        calendar_id=icloud.id,
        google_event_id="swim.ics#20260817T170000Z",
        title="Edited here, not sent yet",
        start_at=datetime(2026, 8, 17, 18),
        end_at=datetime(2026, 8, 17, 19),
        origin="icloud",
        sync_state="pending_update",
    )
    db.add(mine)
    db.commit()

    server.changed = [(href, False)]
    sync_engine.pull_calendar(db, icloud)

    assert db.get(Event, mine.id) is not None, "the server has not seen this yet"
    assert db.get(Event, mine.id).sync_state == "pending_update"


def test_deleting_the_resource_removes_the_series_and_its_overrides(
    client, db, provider, icloud, server
):
    """Matching only the exact id would strand the moved occurrences as events
    belonging to a series that no longer exists."""
    href = server.add_event(
        "swim.ics",
        series(components=override("20260810T170000Z", "Swimming (late)",
                                   "20260810T190000Z", "20260810T200000Z")),
    )
    sync_engine.pull_calendar(db, icloud)
    assert db.query(Event).count() == 2

    del server.resources[href]
    server.changed = [(href, True)]
    sync_engine.pull_calendar(db, icloud)

    assert db.query(Event).count() == 0
    assert listed(client) == []


def test_an_orphan_override_is_still_shown(client, db, provider, icloud, server):
    """The master can fall outside the window we asked for. The occurrence is real
    either way, and dropping it would silently hide a real appointment."""
    server.add_event(
        "swim.ics",
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n"
        + override("20260810T170000Z", "Swimming (late)",
                   "20260810T190000Z", "20260810T200000Z")
        + "END:VCALENDAR\r\n",
    )
    sync_engine.pull_calendar(db, icloud)

    assert [e["title"] for e in listed(client)] == ["Swimming (late)"]


# ------------------------- all-day and odd shapes ----------------------------


def test_an_all_day_series_is_not_shifted(client, db, provider, icloud, server):
    server.add_event(
        "hol.ics",
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:hol\r\nSUMMARY:Bin day\r\n"
        "DTSTART;VALUE=DATE:20260803\r\nDTEND;VALUE=DATE:20260804\r\n"
        "DTSTAMP:20260730T100000Z\r\nRRULE:FREQ=WEEKLY;COUNT=3\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n",
    )
    sync_engine.pull_calendar(db, icloud)

    starts = [e["start_at"][:10] for e in listed(client)]
    assert starts == ["2026-08-03", "2026-08-10", "2026-08-17"]
    assert all(e["all_day"] for e in listed(client))


def test_an_unparseable_rule_does_not_lose_the_event(client, db, provider, icloud, server):
    """A rule this app cannot expand is still better shown once than not at all."""
    server.add_event("odd.ics", series(rrule="FREQ=SECONDLY;COUNT=2"))
    sync_engine.pull_calendar(db, icloud)

    assert db.query(Event).count() == 1
