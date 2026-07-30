def test_widget_types_are_discoverable(client):
    types = client.get("/api/dashboard/widget-types").json()
    keys = {t["type"] for t in types}
    assert {"upcoming_events", "today_agenda", "clock", "mini_month", "note"} <= keys
    for t in types:
        assert t["name"] and t["description"], "an agent needs to know what each widget does"
        assert t["default_size"] in ("small", "medium", "large")


def test_dashboard_starts_empty(client):
    assert client.get("/api/dashboard/widgets").json() == []


def test_add_widgets_appends_in_order(client):
    a = client.post("/api/dashboard/widgets", json={"widget_type": "clock"}).json()
    b = client.post("/api/dashboard/widgets", json={"widget_type": "note"}).json()
    assert a["position"] < b["position"]
    assert [w["widget_type"] for w in client.get("/api/dashboard/widgets").json()] == [
        "clock",
        "note",
    ]


def test_widget_config_roundtrips(client):
    w = client.post(
        "/api/dashboard/widgets",
        json={"widget_type": "upcoming_events", "size": "large", "config": {"days": 3}},
    ).json()
    assert w["config"] == {"days": 3}
    assert w["size"] == "large"

    updated = client.patch(
        f"/api/dashboard/widgets/{w['id']}", json={"config": {"days": 14}, "size": "small"}
    ).json()
    assert updated["config"] == {"days": 14}
    assert updated["size"] == "small"


def test_reordering_widgets(client):
    a = client.post("/api/dashboard/widgets", json={"widget_type": "clock"}).json()
    b = client.post("/api/dashboard/widgets", json={"widget_type": "note"}).json()
    client.patch(f"/api/dashboard/widgets/{a['id']}", json={"position": b["position"] + 1})
    assert [w["widget_type"] for w in client.get("/api/dashboard/widgets").json()] == [
        "note",
        "clock",
    ]


def test_remove_widget(client):
    w = client.post("/api/dashboard/widgets", json={"widget_type": "clock"}).json()
    assert client.delete(f"/api/dashboard/widgets/{w['id']}").status_code == 204
    assert client.get("/api/dashboard/widgets").json() == []


def test_unknown_widget_type_rejected(client):
    r = client.post("/api/dashboard/widgets", json={"widget_type": "weather_machine"})
    assert r.status_code == 400
    assert "Valid types" in r.json()["error"]["message"]


def test_invalid_size_rejected(client):
    r = client.post("/api/dashboard/widgets", json={"widget_type": "clock", "size": "enormous"})
    assert r.status_code == 400


def test_missing_widget_404s(client):
    assert client.patch("/api/dashboard/widgets/999", json={"size": "small"}).status_code == 404
    assert client.delete("/api/dashboard/widgets/999").status_code == 404
