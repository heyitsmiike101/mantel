"""ICS feed tests.

A malformed feed is rejected outright by strict parsers -- Home Assistant's is
one -- so the format details here are load-bearing, not cosmetic.
"""

from app.services.crypto import feed_token


def token() -> str:
    return feed_token()


def make_event(client, calendar_id, **extra):
    payload = {
        "calendar_id": calendar_id,
        "title": "Soccer practice",
        "start_at": "2026-08-03T17:00:00Z",
        "end_at": "2026-08-03T18:30:00Z",
        **extra,
    }
    return client.post("/api/events", json=payload)


def fetch_feed(client, path="all", **params):
    query = {"token": token(), **params}
    return client.get(f"/api/feeds/{path}.ics", params=query)


# -------------------------------- structure ----------------------------------


def test_feed_is_well_formed(client, local_calendar):
    make_event(client, local_calendar["id"])
    r = fetch_feed(client)

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")

    body = r.text
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert body.endswith("END:VCALENDAR\r\n")
    assert "VERSION:2.0" in body
    assert body.count("BEGIN:VEVENT") == 1
    assert body.count("END:VEVENT") == 1

    # Every line must use CRLF; a bare LF makes strict parsers reject the file.
    assert "\n" not in body.replace("\r\n", "")


def test_event_fields_are_present(client, local_calendar):
    make_event(
        client,
        local_calendar["id"],
        description="Bring shin guards",
        location="Riverside Park",
    )
    body = fetch_feed(client).text

    assert "SUMMARY:Soccer practice" in body
    assert "DESCRIPTION:Bring shin guards" in body
    assert "LOCATION:Riverside Park" in body
    assert "DTSTART:20260803T170000Z" in body
    assert "DTEND:20260803T183000Z" in body
    assert "UID:famcal-" in body


def test_uid_is_stable_between_fetches(client, local_calendar):
    """An unstable UID makes a subscriber duplicate the event on every refresh."""
    make_event(client, local_calendar["id"])
    first = [ln for ln in fetch_feed(client).text.splitlines() if ln.startswith("UID:")]
    second = [ln for ln in fetch_feed(client).text.splitlines() if ln.startswith("UID:")]
    assert first == second


def test_all_day_events_use_date_values(client, local_calendar):
    make_event(
        client,
        local_calendar["id"],
        title="Beach trip",
        all_day=True,
        start_at="2026-08-01T00:00:00Z",
        end_at="2026-08-03T00:00:00Z",
    )
    body = fetch_feed(client).text
    assert "DTSTART;VALUE=DATE:20260801" in body
    assert "DTEND;VALUE=DATE:20260803" in body


def test_recurring_events_export_the_rule_not_every_instance(client, local_calendar):
    make_event(client, local_calendar["id"], recurrence_rule="FREQ=WEEKLY;COUNT=10")
    body = fetch_feed(client).text
    assert body.count("BEGIN:VEVENT") == 1, "the series is sent once"
    assert "RRULE:FREQ=WEEKLY;COUNT=10" in body


def test_special_characters_are_escaped(client, local_calendar):
    make_event(
        client,
        local_calendar["id"],
        title="Dinner; with the Smiths, at 7",
        description="Line one\nLine two",
    )
    body = fetch_feed(client).text
    assert "SUMMARY:Dinner\; with the Smiths\\, at 7" in body
    assert "\\n" in body


def test_long_lines_are_folded(client, local_calendar):
    """RFC 5545 caps content lines at 75 octets; an unfolded long description is
    exactly the kind of thing a strict parser refuses."""
    make_event(client, local_calendar["id"], description="x" * 400)
    body = fetch_feed(client).text

    for line in body.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, f"unfolded line: {line[:40]}..."
    # Folded continuations start with a single space.
    assert "\r\n x" in body


def test_feed_parses_with_a_real_icalendar_parser(client, local_calendar):
    """The claim that actually matters: a parser other than ours accepts this.

    Home Assistant, Apple Calendar and Outlook all use strict parsers that reject
    a feed outright rather than skipping a bad line, so 'it looks right' is not
    good enough.
    """
    from icalendar import Calendar

    make_event(
        client,
        local_calendar["id"],
        description="Bring shin guards, please; and a water bottle. " + "x" * 200,
        location="Riverside Park, Field 3",
        recurrence_rule="FREQ=WEEKLY;BYDAY=MO",
    )
    make_event(
        client,
        local_calendar["id"],
        title="Beach trip",
        all_day=True,
        start_at="2026-08-01T00:00:00Z",
        end_at="2026-08-03T00:00:00Z",
    )

    parsed = Calendar.from_ical(fetch_feed(client).text.encode("utf-8"))
    events = list(parsed.walk("VEVENT"))

    assert len(events) == 2
    assert str(parsed.get("X-WR-CALNAME")) == "Family Calendar"

    recurring = next(e for e in events if e.get("RRULE"))
    assert recurring["RRULE"].to_ical().decode() == "FREQ=WEEKLY;BYDAY=MO"
    assert "shin guards" in str(recurring.get("DESCRIPTION")), "folded text must reassemble"
    assert str(recurring.get("LOCATION")) == "Riverside Park, Field 3"

    all_day = next(e for e in events if str(e.get("SUMMARY")) == "Beach trip")
    assert all_day.decoded("DTSTART").isoformat() == "2026-08-01"


# ------------------------------- filtering -----------------------------------


def test_single_calendar_feed_only_has_that_calendar(client, local_calendar):
    other = client.post("/api/calendars", json={"name": "Chores"}).json()
    make_event(client, local_calendar["id"], title="Family thing")
    make_event(client, other["id"], title="Take out trash")

    everything = fetch_feed(client).text
    assert "Family thing" in everything and "Take out trash" in everything

    just_chores = fetch_feed(client, str(other["id"])).text
    assert "Take out trash" in just_chores
    assert "Family thing" not in just_chores


def test_calendar_name_is_advertised(client, local_calendar):
    body = fetch_feed(client, str(local_calendar["id"])).text
    assert "X-WR-CALNAME:Family" in body


def test_refresh_hint_is_included(client, local_calendar):
    body = fetch_feed(client).text
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT30M" in body
    assert "X-PUBLISHED-TTL:PT30M" in body


def test_missing_calendar_404s(client):
    assert fetch_feed(client, "999").status_code == 404


# --------------------------------- token -------------------------------------


def test_feed_requires_a_token(client, local_calendar):
    assert client.get("/api/feeds/all.ics").status_code == 422  # missing param


def test_wrong_token_is_refused(client, local_calendar):
    make_event(client, local_calendar["id"])
    r = client.get("/api/feeds/all.ics", params={"token": "not-the-token"})
    assert r.status_code == 403
    assert "Soccer practice" not in r.text


def test_token_endpoint_returns_a_usable_url(client):
    body = client.get("/api/feeds/token").json()
    assert body["token"] == token()
    assert body["all_calendars_url"].endswith(f"/api/feeds/all.ics?token={token()}")
    assert "password" in body["hint"].lower()


def test_token_is_stable_across_calls(client):
    assert client.get("/api/feeds/token").json()["token"] == (
        client.get("/api/feeds/token").json()["token"]
    )
