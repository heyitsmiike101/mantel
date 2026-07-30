def test_create_and_list_users(client):
    r = client.post("/api/users", json={"name": "Mike", "color": "#ff0000"})
    assert r.status_code == 201
    assert r.json()["color"] == "#ff0000"

    r2 = client.post("/api/users", json={"name": "Sam"})
    assert r2.status_code == 201
    assert r2.json()["color"] != "#ff0000", "auto-assigned colors must not collide"

    names = [u["name"] for u in client.get("/api/users").json()]
    assert names == ["Mike", "Sam"]


def test_users_sorted_by_sort_order(client):
    client.post("/api/users", json={"name": "Second", "sort_order": 5})
    client.post("/api/users", json={"name": "First", "sort_order": 1})
    assert [u["name"] for u in client.get("/api/users").json()] == ["First", "Second"]


def test_update_and_delete_user(client):
    uid = client.post("/api/users", json={"name": "Mike"}).json()["id"]

    r = client.patch(f"/api/users/{uid}", json={"color": "#00FF00", "avatar_emoji": "🦊"})
    assert r.json()["color"] == "#00ff00"
    assert r.json()["avatar_emoji"] == "🦊"

    assert client.delete(f"/api/users/{uid}").status_code == 204
    assert client.get(f"/api/users/{uid}").status_code == 404


def test_invalid_color_rejected(client):
    r = client.post("/api/users", json={"name": "Mike", "color": "red"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_error_envelope_shape(client):
    body = client.get("/api/users/999").json()
    assert body == {"error": {"code": "not_found", "message": "User not found"}}
