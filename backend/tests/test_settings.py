

def test_bookmark_settings_round_trip(client):
    """The top-bar shortcut is two plain settings keys; blank means no bar."""
    body = client.get("/api/settings").json()
    assert body["bookmark_label"] == ""
    assert body["bookmark_url"] == ""

    r = client.patch(
        "/api/settings",
        json={"bookmark_label": "wall", "bookmark_url": "http://dash.lan/?view=wall"},
    )
    assert r.status_code == 200

    body = client.get("/api/settings").json()
    assert body["bookmark_label"] == "wall"
    assert body["bookmark_url"] == "http://dash.lan/?view=wall"
