from concurrent.futures import ThreadPoolExecutor


def make_list(client, name="Groceries", icon="🛒"):
    return client.post("/api/lists", json={"name": name, "icon": icon}).json()


def add(client, list_id, text, **extra):
    return client.post(f"/api/lists/{list_id}/items", json={"text": text, **extra})


# ---------------------------------- lists ------------------------------------


def test_starts_empty(client):
    assert client.get("/api/lists").json() == []


def test_create_and_fetch(client):
    created = make_list(client)
    assert created["name"] == "Groceries"
    assert created["icon"] == "🛒"
    assert created["items"] == []

    listed = client.get("/api/lists").json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]


def test_lists_keep_creation_order(client):
    ids = [make_list(client, n)["id"] for n in ("Groceries", "Hardware", "Packing")]
    assert [row["id"] for row in client.get("/api/lists").json()] == ids


def test_rename_and_delete(client):
    row = make_list(client)
    renamed = client.patch(f"/api/lists/{row['id']}", json={"name": "Costco"}).json()
    assert renamed["name"] == "Costco"

    assert client.delete(f"/api/lists/{row['id']}").status_code == 204
    assert client.get("/api/lists").json() == []


def test_deleting_a_list_takes_its_items(client, db):
    from app.models import ListItem

    row = make_list(client)
    add(client, row["id"], "Milk")
    add(client, row["id"], "Eggs")

    client.delete(f"/api/lists/{row['id']}")
    assert db.query(ListItem).count() == 0, "items must not outlive their list"


def test_missing_list_404s(client):
    assert client.get("/api/lists/999").status_code == 404
    assert client.patch("/api/lists/999", json={"name": "x"}).status_code == 404
    assert client.delete("/api/lists/999").status_code == 404


# ---------------------------------- items ------------------------------------


def test_add_items_and_count_remaining(client):
    row = make_list(client)
    add(client, row["id"], "Milk")
    add(client, row["id"], "Eggs")

    fetched = client.get(f"/api/lists/{row['id']}").json()
    assert [i["text"] for i in fetched["items"]] == ["Milk", "Eggs"]
    assert fetched["item_count"] == 2


def test_checking_an_item_sinks_it_and_drops_the_count(client):
    row = make_list(client)
    milk = add(client, row["id"], "Milk").json()
    add(client, row["id"], "Eggs")
    add(client, row["id"], "Bread")

    client.patch(f"/api/lists/{row['id']}/items/{milk['id']}", json={"checked": True})

    fetched = client.get(f"/api/lists/{row['id']}").json()
    assert [i["text"] for i in fetched["items"]] == ["Eggs", "Bread", "Milk"]
    assert fetched["item_count"] == 2, "checked items don't count as remaining"


def test_unchecking_restores_position(client):
    row = make_list(client)
    milk = add(client, row["id"], "Milk").json()
    add(client, row["id"], "Eggs")

    client.patch(f"/api/lists/{row['id']}/items/{milk['id']}", json={"checked": True})
    client.patch(f"/api/lists/{row['id']}/items/{milk['id']}", json={"checked": False})

    fetched = client.get(f"/api/lists/{row['id']}").json()
    assert [i["text"] for i in fetched["items"]] == ["Milk", "Eggs"]


def test_assigning_an_item_carries_the_person_color(client):
    uid = client.post("/api/users", json={"name": "Mike", "color": "#abcdef"}).json()["id"]
    row = make_list(client)
    item = add(client, row["id"], "Take out trash", assigned_user_id=uid).json()
    assert item["assigned_user_id"] == uid
    assert item["color"] == "#abcdef"


def test_unassigned_items_have_no_color(client):
    row = make_list(client)
    assert add(client, row["id"], "Milk").json()["color"] is None


def test_rename_and_delete_an_item(client):
    row = make_list(client)
    item = add(client, row["id"], "Milk").json()

    renamed = client.patch(
        f"/api/lists/{row['id']}/items/{item['id']}", json={"text": "Oat milk"}
    ).json()
    assert renamed["text"] == "Oat milk"

    assert client.delete(f"/api/lists/{row['id']}/items/{item['id']}").status_code == 204
    assert client.get(f"/api/lists/{row['id']}").json()["items"] == []


def test_clear_checked(client):
    row = make_list(client)
    milk = add(client, row["id"], "Milk").json()
    add(client, row["id"], "Eggs")
    client.patch(f"/api/lists/{row['id']}/items/{milk['id']}", json={"checked": True})

    after = client.post(f"/api/lists/{row['id']}/clear-checked").json()
    assert [i["text"] for i in after["items"]] == ["Eggs"]


def test_items_are_scoped_to_their_list(client):
    """An item id from one list must not be reachable through another."""
    a, b = make_list(client, "A"), make_list(client, "B")
    item = add(client, a["id"], "Milk").json()

    assert client.patch(
        f"/api/lists/{b['id']}/items/{item['id']}", json={"checked": True}
    ).status_code == 404
    assert client.delete(f"/api/lists/{b['id']}/items/{item['id']}").status_code == 404


def test_rejects_empty_text(client):
    row = make_list(client)
    assert add(client, row["id"], "").status_code == 422


def test_rejects_unknown_assignee(client):
    row = make_list(client)
    assert add(client, row["id"], "Milk", assigned_user_id=999).status_code == 404


def test_adding_to_a_missing_list_404s(client):
    assert add(client, 999, "Milk").status_code == 404


# ------------------------------- concurrency ---------------------------------


def test_two_people_adding_at_once(client):
    """The realistic case: one person at the shop, another at the kitchen display."""
    row = make_list(client)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: add(client, row["id"], f"Item {i}"), range(24)))

    assert all(r.status_code == 201 for r in results)
    fetched = client.get(f"/api/lists/{row['id']}").json()
    assert fetched["item_count"] == 24
    assert len({i["text"] for i in fetched["items"]}) == 24, "no lost or duplicated writes"
