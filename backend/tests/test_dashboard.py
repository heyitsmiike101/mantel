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


def test_seven_day_checklist_config_persists_without_calendar_dates(client):
    types = client.get("/api/dashboard/widget-types").json()
    checklist_type = next(t for t in types if t["type"] == "seven_day_checklist")
    assert checklist_type["default_size"] == "large"
    assert "checklist" in checklist_type["config_schema"]

    widget = client.post(
        "/api/dashboard/widgets", json={"widget_type": "seven_day_checklist"}
    ).json()
    monday = [{"id": "meal-1", "text": "Pasta", "checked": False}]
    config = {"checklist": {"Monday": monday, "Sunday": []}}
    updated = client.patch(
        f"/api/dashboard/widgets/{widget['id']}", json={"config": config}
    )
    assert updated.status_code == 200
    assert client.get("/api/dashboard/widgets").json()[0]["config"] == config


def test_checklist_edits_from_two_clients_preserve_each_others_items(client):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from app.main import app

    widget = client.post(
        "/api/dashboard/widgets", json={"widget_type": "seven_day_checklist"}
    ).json()
    path = f"/api/dashboard/widgets/{widget['id']}/checklist"
    with TestClient(app) as other:
        assert other.get("/api/dashboard/widgets").json()[0]["config"] == {}

        def add_items(http_client, prefix):
            for index in range(10):
                response = http_client.post(
                    path,
                    json={
                        "operation": "add",
                        "day": "Monday",
                        "id": f"{prefix}-{index}",
                        "text": f"{prefix} meal {index}",
                    },
                )
                assert response.status_code == 200, response.text

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(add_items, client, "first")
            second = pool.submit(add_items, other, "second")
            first.result()
            second.result()

        items = client.get("/api/dashboard/widgets").json()[0]["config"]["checklist"]["Monday"]
        assert {item["id"] for item in items} == {
            f"{prefix}-{index}" for prefix in ("first", "second") for index in range(10)
        }
        history = client.get("/api/dashboard/widgets").json()[0]["config"]["meal_history"]
        assert set(history) == {
            f"{prefix} meal {index}" for prefix in ("first", "second") for index in range(10)
        }
        assert other.post(
            path,
            json={"operation": "set_checked", "day": "Monday", "id": "second-0", "checked": True},
        ).status_code == 200
        assert client.post(
            path, json={"operation": "remove", "day": "Monday", "id": "first-0"}
        ).status_code == 200
        items = client.get("/api/dashboard/widgets").json()[0]["config"]["checklist"]["Monday"]
        assert next(item for item in items if item["id"] == "second-0")["checked"] is True
        assert all(item["id"] != "first-0" for item in items)


def test_checklist_rejects_invalid_edits_without_saving(client):
    widget = client.post(
        "/api/dashboard/widgets", json={"widget_type": "seven_day_checklist"}
    ).json()
    path = f"/api/dashboard/widgets/{widget['id']}/checklist"
    assert client.post(
        path, json={"operation": "add", "day": "Monday", "id": "one"}
    ).status_code == 400
    assert client.post(
        path,
        json={"operation": "set_checked", "day": "Monday", "id": "one", "checked": True},
    ).status_code == 404
    assert client.post(
        path, json={"operation": "add", "day": "Tuesday", "id": "one", "text": "Soup"}
    ).status_code == 200
    assert client.post(
        path, json={"operation": "add", "day": "Tuesday", "id": "one", "text": "Salad"}
    ).status_code == 409
    assert client.get("/api/dashboard/widgets").json()[0]["config"]["checklist"]["Tuesday"] == [
        {"id": "one", "text": "Soup", "checked": False}
    ]


def test_checklist_remembers_unique_meals_after_completion_and_reuse(client):
    widget = client.post(
        "/api/dashboard/widgets", json={"widget_type": "seven_day_checklist"}
    ).json()
    path = f"/api/dashboard/widgets/{widget['id']}/checklist"
    for item_id, day, meal in [
        ("one", "Monday", "Pasta"),
        ("two", "Tuesday", " pasta "),
        ("three", "Sunday", "Soup"),
    ]:
        assert client.post(path, json={
            "operation": "add", "day": day, "id": item_id, "text": meal,
        }).status_code == 200
    assert client.post(path, json={
        "operation": "remove", "day": "Monday", "id": "one",
    }).status_code == 200
    assert client.post(path, json={
        "operation": "remove", "day": "Sunday", "id": "three",
    }).status_code == 200
    assert client.post(path, json={
        "operation": "add", "day": "Friday", "id": "four", "text": "Pasta",
    }).status_code == 200
    config = client.get("/api/dashboard/widgets").json()[0]["config"]
    assert config["meal_history"] == ["Pasta", "Soup"]
    assert config["checklist"]["Friday"] == [
        {"id": "four", "text": "Pasta", "checked": False}
    ]


def test_checklist_imported_items_are_saved_in_history_before_removal(client):
    widget = client.post("/api/dashboard/widgets", json={
        "widget_type": "seven_day_checklist",
        "config": {"checklist": {"Monday": [{
            "id": "old", "text": "Curry", "checked": False,
        }]}},
    }).json()
    path = f"/api/dashboard/widgets/{widget['id']}/checklist"
    response = client.post(path, json={
        "operation": "remove", "day": "Monday", "id": "old",
    })
    assert response.status_code == 200
    assert response.json()["config"]["meal_history"] == ["Curry"]


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
