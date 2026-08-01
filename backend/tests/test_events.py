import pytest


def make_event(client, calendar_id, **overrides):
    payload = {
        "calendar_id": calendar_id,
        "title": "Soccer practice",
        "start_at": "2026-08-03T17:00:00Z",
        "end_at": "2026-08-03T18:30:00Z",
        **overrides,
    }
    return client.post("/api/events", json=payload)


def test_first_run_creates_local_family_calendar(client):
    cals = client.get("/api/calendars").json()
    assert len(cals) == 1
    assert cals[0]["name"] == "Family"
    assert cals[0]["is_local"] is True
    assert cals[0]["writable"] is True


def test_create_and_fetch_event(client, local_calendar):
    r = make_event(client, local_calendar["id"])
    assert r.status_code == 201
    ev = r.json()
    assert ev["title"] == "Soccer practice"
    assert ev["origin"] == "local"
    assert ev["sync_state"] == "synced", "local events are never queued for Google"
    assert ev["editable"] is True

    assert client.get(f"/api/events/{ev['id']}").json()["id"] == ev["id"]


def test_event_color_follows_claiming_user(client, local_calendar):
    uid = client.post("/api/users", json={"name": "Mike", "color": "#abcdef"}).json()["id"]
    client.patch(f"/api/calendars/{local_calendar['id']}", json={"claimed_by_user_id": uid})

    ev = make_event(client, local_calendar["id"]).json()
    assert ev["color"] == "#abcdef"
    assert ev["user_id"] == uid


def test_color_override_beats_user_color(client, local_calendar):
    uid = client.post("/api/users", json={"name": "Mike", "color": "#abcdef"}).json()["id"]
    client.patch(
        f"/api/calendars/{local_calendar['id']}",
        json={"claimed_by_user_id": uid, "color_override": "#123456"},
    )
    assert make_event(client, local_calendar["id"]).json()["color"] == "#123456"


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("2026-08-03T00:00:00Z", "2026-08-04T00:00:00Z", 1),  # same day
        ("2026-08-03T18:00:00Z", "2026-08-04T00:00:00Z", 1),  # partial overlap at the end
        ("2026-08-03T00:00:00Z", "2026-08-03T17:00:00Z", 0),  # range ends exactly at start
        ("2026-08-03T18:30:00Z", "2026-08-04T00:00:00Z", 0),  # range starts exactly at end
        ("2026-08-10T00:00:00Z", "2026-08-11T00:00:00Z", 0),  # different week
    ],
)
def test_date_range_overlap_semantics(client, local_calendar, start, end, expected):
    make_event(client, local_calendar["id"])
    r = client.get("/api/events", params={"start": start, "end": end})
    assert len(r.json()) == expected


def test_multiday_event_appears_in_every_overlapping_range(client, local_calendar):
    make_event(
        client,
        local_calendar["id"],
        title="Vacation",
        start_at="2026-08-01T00:00:00Z",
        end_at="2026-08-08T00:00:00Z",
    )
    for day in ("2026-08-02", "2026-08-05", "2026-08-07"):
        r = client.get(
            "/api/events", params={"start": f"{day}T00:00:00Z", "end": f"{day}T23:59:59Z"}
        )
        assert len(r.json()) == 1, f"expected the multi-day event to cover {day}"


def test_events_sorted_by_start(client, local_calendar):
    make_event(client, local_calendar["id"], title="Later", start_at="2026-08-03T20:00:00Z",
               end_at="2026-08-03T21:00:00Z")
    make_event(client, local_calendar["id"], title="Earlier", start_at="2026-08-03T08:00:00Z",
               end_at="2026-08-03T09:00:00Z")
    titles = [
        e["title"]
        for e in client.get(
            "/api/events", params={"start": "2026-08-03T00:00:00Z", "end": "2026-08-04T00:00:00Z"}
        ).json()
    ]
    assert titles == ["Earlier", "Later"]


def test_filter_by_calendar_and_user(client, local_calendar):
    uid = client.post("/api/users", json={"name": "Mike"}).json()["id"]
    other = client.post("/api/calendars", json={"name": "Chores"}).json()
    client.patch(f"/api/calendars/{other['id']}", json={"claimed_by_user_id": uid})

    make_event(client, local_calendar["id"], title="Family thing")
    make_event(client, other["id"], title="Take out trash")

    params = {"start": "2026-08-03T00:00:00Z", "end": "2026-08-04T00:00:00Z"}
    assert len(client.get("/api/events", params=params).json()) == 2

    by_cal = client.get("/api/events", params={**params, "calendar_ids": str(other["id"])}).json()
    assert [e["title"] for e in by_cal] == ["Take out trash"]

    by_user = client.get("/api/events", params={**params, "user_ids": str(uid)}).json()
    assert [e["title"] for e in by_user] == ["Take out trash"]


def test_non_numeric_id_filters_are_rejected_not_a_server_error(client, local_calendar):
    """A typo in a filter is the caller's mistake, so it must not read as ours.

    `int()` on a non-numeric part used to raise straight out of the handler,
    which FastAPI surfaces as a 500 — indistinguishable from the calendar
    actually being broken.
    """
    make_event(client, local_calendar["id"], title="Family thing")
    params = {"start": "2026-08-03T00:00:00Z", "end": "2026-08-04T00:00:00Z"}
    for field in ("calendar_ids", "user_ids"):
        r = client.get("/api/events", params={**params, field: "abc"})
        assert r.status_code == 400, f"{field}=abc gave {r.status_code}"
        assert field in r.json()["error"]["message"]

    # Trailing and repeated separators are sloppy, not wrong.
    ok = client.get("/api/events", params={**params, "calendar_ids": f",{local_calendar['id']},,"})
    assert ok.status_code == 200
    assert [e["title"] for e in ok.json()] == ["Family thing"]


def test_text_search(client, local_calendar):
    make_event(client, local_calendar["id"], title="Dentist appointment")
    make_event(client, local_calendar["id"], title="Soccer practice")
    params = {"start": "2026-08-03T00:00:00Z", "end": "2026-08-04T00:00:00Z", "q": "dent"}
    assert [e["title"] for e in client.get("/api/events", params=params).json()] == [
        "Dentist appointment"
    ]


def test_update_event(client, local_calendar):
    ev = make_event(client, local_calendar["id"]).json()
    r = client.patch(
        f"/api/events/{ev['id']}", json={"title": "Soccer game", "location": "Field 3"}
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Soccer game"
    assert r.json()["location"] == "Field 3"
    assert r.json()["start_at"] == ev["start_at"], "untouched fields must not change"


def test_delete_event(client, local_calendar):
    ev = make_event(client, local_calendar["id"]).json()
    assert client.delete(f"/api/events/{ev['id']}").status_code == 204
    assert client.get(f"/api/events/{ev['id']}").status_code == 404


def test_end_before_start_rejected(client, local_calendar):
    r = make_event(client, local_calendar["id"], end_at="2026-08-03T16:00:00Z")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_bad_range_rejected(client):
    r = client.get(
        "/api/events", params={"start": "2026-08-04T00:00:00Z", "end": "2026-08-03T00:00:00Z"}
    )
    assert r.status_code == 400


def test_event_on_missing_calendar(client):
    r = make_event(client, 9999)
    assert r.status_code == 404


def test_all_day_event_roundtrip(client, local_calendar):
    ev = make_event(
        client,
        local_calendar["id"],
        title="Birthday",
        all_day=True,
        start_at="2026-08-03T00:00:00Z",
        end_at="2026-08-04T00:00:00Z",
    ).json()
    assert ev["all_day"] is True
    fetched = client.get(
        "/api/events", params={"start": "2026-08-03T00:00:00Z", "end": "2026-08-04T00:00:00Z"}
    ).json()[0]
    assert fetched["all_day"] is True


def test_timestamps_returned_with_utc_offset(client, local_calendar):
    ev = make_event(client, local_calendar["id"]).json()
    assert ev["start_at"].endswith("Z") or "+00:00" in ev["start_at"]


def test_non_utc_input_is_normalized(client, local_calendar):
    ev = make_event(
        client,
        local_calendar["id"],
        start_at="2026-08-03T13:00:00-04:00",
        end_at="2026-08-03T14:00:00-04:00",
    ).json()
    # 13:00 EDT is 17:00 UTC
    assert ev["start_at"].startswith("2026-08-03T17:00:00")
