"""CalDAV transport and XML.

These test the layer that talks to iCloud, not the sync logic. Everything here is
a shape a real server produces and this app has to survive.
"""

from datetime import datetime

import httpx
import pytest
from fake_caldav import CALENDAR, ENTRY_HOST, HOME, PARTITION_HOST, TASKS, FakeCalDav, vevent

from app.services.caldav_client import CalDavClient
from app.services.providers.base import ProviderAuthError, ProviderError, SyncTokenExpired


@pytest.fixture
def server():
    return FakeCalDav()


@pytest.fixture
def dav(server):
    return CalDavClient("someone@example.com", "pw", http=server.client())


@pytest.fixture
def home(dav):
    return dav.discover_calendar_home()


# ------------------------------- discovery -----------------------------------


def test_discovery_follows_the_partition_redirect(dav, server):
    """iCloud answers the published address with a redirect to the host that
    actually holds the account. Not following it means never finding a calendar."""
    found = dav.discover_calendar_home()

    assert found == f"{PARTITION_HOST}{HOME}"
    assert ("PROPFIND", "/") in server.requests


def test_lists_only_collections_that_can_hold_an_event(dav, home):
    """A calendar home also contains the home itself and a reminders-only list.
    Offering those would offer somewhere an event cannot be created."""
    calendars = dav.list_calendars(home)

    assert [c.path for c in calendars] == [CALENDAR]
    assert calendars[0].name == "Home"


def test_write_privileges_become_the_writer_role(dav, home):
    assert dav.list_calendars(home)[0].access_role == "writer"


def test_a_calendar_without_write_privileges_is_read_only(dav, home, server, monkeypatch):
    original = server._propfind

    def stripped(request, path):
        resp = original(request, path)
        text = resp.text.replace("<D:privilege><D:write-content/></D:privilege>", "")
        text = text.replace("<D:privilege><D:bind/></D:privilege>", "")
        return type(resp)(207, text=text, headers={"Content-Type": "application/xml"})

    monkeypatch.setattr(server, "_propfind", stripped)
    assert dav.list_calendars(home)[0].access_role == "reader"


def test_a_terse_server_is_not_assumed_to_lack_vevent(dav, home, server, monkeypatch):
    """RFC 4791 makes VEVENT the default. Excluding a calendar that simply did not
    advertise its components would hide real calendars."""
    original = server._propfind

    def stripped(request, path):
        resp = original(request, path)
        text = resp.text.replace(
            "<C:supported-calendar-component-set><C:comp name='VEVENT'/>"
            "</C:supported-calendar-component-set>",
            "",
        )
        return type(resp)(207, text=text, headers={"Content-Type": "application/xml"})

    monkeypatch.setattr(server, "_propfind", stripped)
    assert [c.path for c in dav.list_calendars(home)] == [CALENDAR]


# ------------------------------ reading --------------------------------------


def test_baseline_token_does_not_download_the_calendar(dav, home, server):
    """The whole point: get a cursor without pulling years of history."""
    server.add_event("a.ics", vevent("a", "One", "20260803T170000Z", "20260803T180000Z"))

    token = dav.baseline_sync_token(f"{PARTITION_HOST}{CALENDAR}")

    assert token == "sync-1"
    assert server.last_sync_token in (None, "")
    assert not any(m == "GET" for m, _ in server.requests)


def test_time_range_is_sent_in_ical_form(dav, server):
    """A time-range filter rejects ISO 8601 with separators; it wants 20260101T000000Z."""
    dav.list_hrefs_in_window(f"{PARTITION_HOST}{CALENDAR}", datetime(2026, 5, 1, 9, 30, 0))

    assert server.last_time_range == "20260501T093000Z"


def test_window_query_returns_hrefs_and_etags(dav, server):
    server.add_event("a.ics", vevent("a", "One", "20260803T170000Z", "20260803T180000Z"), '"e9"')

    found = dav.list_hrefs_in_window(f"{PARTITION_HOST}{CALENDAR}", datetime(2026, 1, 1))

    assert [r.href for r in found] == [CALENDAR + "a.ics"]
    assert found[0].etag == '"e9"'


def test_the_collection_itself_is_not_mistaken_for_an_event(dav, server):
    """A multistatus includes the collection it was asked about. Treating that as
    an event would create a titleless row on every sync."""
    server.changed = [(CALENDAR, False)]

    changed, _ = dav.sync_collection(f"{PARTITION_HOST}{CALENDAR}", "sync-0")

    assert changed == []


def test_sync_collection_reports_deletions(dav, server):
    server.add_event("a.ics", vevent("a", "One", "20260803T170000Z", "20260803T180000Z"))
    server.changed = [(CALENDAR + "a.ics", False), (CALENDAR + "gone.ics", True)]

    changed, token = dav.sync_collection(f"{PARTITION_HOST}{CALENDAR}", "sync-0")

    assert token == "sync-1"
    assert [(r.href, r.deleted) for r in changed] == [
        (CALENDAR + "a.ics", False),
        (CALENDAR + "gone.ics", True),
    ]


def test_an_expired_sync_token_is_not_reported_as_an_auth_failure(dav, server):
    """iCloud says 403 for both. Reading it as auth would tell the family to
    re-link a perfectly good account instead of quietly resyncing."""
    server.expire_next_sync_token = True

    with pytest.raises(SyncTokenExpired):
        dav.sync_collection(f"{PARTITION_HOST}{CALENDAR}", "stale")


def test_multiget_returns_bodies(dav, server):
    server.add_event("a.ics", vevent("a", "Dentist", "20260803T170000Z", "20260803T180000Z"))

    fetched = dav.fetch(f"{PARTITION_HOST}{CALENDAR}", [CALENDAR + "a.ics"])

    assert len(fetched) == 1
    assert "SUMMARY:Dentist" in fetched[0].data
    assert fetched[0].href == CALENDAR + "a.ics"


def test_multiget_batches_large_requests(dav, server):
    for i in range(120):
        server.add_event(f"e{i}.ics", vevent(f"e{i}", "X", "20260803T170000Z", "20260803T180000Z"))

    fetched = dav.fetch(f"{PARTITION_HOST}{CALENDAR}", list(server.resources))

    assert len(fetched) == 120
    reports = [r for r in server.requests if r[0] == "REPORT"]
    assert len(reports) == 3, "120 resources at 50 per batch is three round trips"


def test_a_resource_that_vanished_between_calls_is_skipped(dav, server):
    """The window query and the multiget are separate requests; something can be
    deleted in between. That is not an error."""
    fetched = dav.fetch(f"{PARTITION_HOST}{CALENDAR}", [CALENDAR + "missing.ics"])
    assert fetched == []


def test_weak_etags_are_normalised(dav, server):
    server.add_event("a.ics", vevent("a", "One", "20260803T170000Z", "20260803T180000Z"), 'W/"e3"')

    found = dav.list_hrefs_in_window(f"{PARTITION_HOST}{CALENDAR}", datetime(2026, 1, 1))

    assert found[0].etag == '"e3"', "a W/ prefix would make every If-Match fail"


# ------------------------------- writing -------------------------------------


def test_create_sends_if_none_match(dav, server):
    etag = dav.put(f"{PARTITION_HOST}{CALENDAR}new.ics", "BEGIN:VCALENDAR\r\n", create=True)

    assert etag == '"v1"'
    assert server.puts[0][0] == CALENDAR + "new.ics"


def test_update_guards_with_if_match(dav, server):
    server.add_event("a.ics", vevent("a", "One", "20260803T170000Z", "20260803T180000Z"))
    dav.put(f"{PARTITION_HOST}{CALENDAR}a.ics", "BEGIN:VCALENDAR\r\n", etag='"e1"')
    assert server.puts

    server.fail_put_with = 412
    with pytest.raises(ProviderError) as exc:
        dav.put(f"{PARTITION_HOST}{CALENDAR}a.ics", "BEGIN:VCALENDAR\r\n", etag='"stale"')
    assert exc.value.status == 412


def test_a_put_without_an_etag_header_returns_none(dav, server):
    """The spec lets a server omit it and iCloud sometimes does. The caller has to
    notice and re-read, or every later update sends a stale If-Match."""
    server.omit_etag_on_put = True

    assert dav.put(f"{PARTITION_HOST}{CALENDAR}new.ics", "BEGIN:VCALENDAR\r\n", create=True) is None


def test_get_reads_the_etag_back(dav, server):
    server.add_event("a.ics", vevent("a", "One", "20260803T170000Z", "20260803T180000Z"), '"e7"')

    resource = dav.get(f"{PARTITION_HOST}{CALENDAR}a.ics")

    assert resource.etag == '"e7"'
    assert "SUMMARY:One" in resource.data


def test_delete_removes_the_resource(dav, server):
    server.add_event("a.ics", vevent("a", "One", "20260803T170000Z", "20260803T180000Z"))

    dav.delete(f"{PARTITION_HOST}{CALENDAR}a.ics", etag='"e1"')

    assert server.deletes == [CALENDAR + "a.ics"]
    assert CALENDAR + "a.ics" not in server.resources


def test_deleting_something_already_gone_raises_404(dav, server):
    """The client reports it; the push loop is what decides that is fine."""
    with pytest.raises(ProviderError) as exc:
        dav.delete(f"{PARTITION_HOST}{CALENDAR}missing.ics")
    assert exc.value.status == 404


# -------------------------------- failures -----------------------------------


def test_a_rejected_password_asks_for_a_re_link(dav, server):
    server.unauthorized = True

    with pytest.raises(ProviderAuthError) as exc:
        dav.discover_calendar_home()
    assert "appleid.apple.com" in str(exc.value)


def test_an_unreachable_server_is_not_an_auth_failure(server):
    """A flaky network must not flip a working account to needs_reauth."""

    def boom(request):
        raise httpx.ConnectError("no route to host")

    client = CalDavClient(
        "someone@example.com",
        "pw",
        http=httpx.Client(transport=httpx.MockTransport(boom), follow_redirects=True),
    )
    with pytest.raises(ProviderError) as exc:
        client.discover_calendar_home()
    assert not isinstance(exc.value, ProviderAuthError)


def test_unreadable_xml_is_reported_clearly(dav, server, monkeypatch):


    monkeypatch.setattr(
        server, "_propfind", lambda request, path: httpx.Response(207, text="<not xml")
    )
    with pytest.raises(ProviderError, match="Unreadable XML"):
        dav.discover_calendar_home()


def test_entry_host_constant_matches_the_client_default():
    """Guards against the fake and the client drifting to different addresses."""
    from app.services.caldav_client import ICLOUD_CALDAV

    assert ICLOUD_CALDAV == ENTRY_HOST
    assert TASKS != CALENDAR
