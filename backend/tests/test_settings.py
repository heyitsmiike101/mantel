

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


def test_theme_defaults_to_midnight_and_accepts_each_shipped_theme(client):
    """Midnight is the look every existing install already has, so it must stay the default."""
    assert client.get("/api/settings").json()["theme"] == "midnight"

    for theme in ("daylight", "hearth", "midnight"):
        r = client.patch("/api/settings", json={"theme": theme})
        assert r.status_code == 200
        assert client.get("/api/settings").json()["theme"] == theme


def test_unknown_theme_is_rejected_and_leaves_the_current_theme_alone(client):
    client.patch("/api/settings", json={"theme": "hearth"})

    r = client.patch("/api/settings", json={"theme": "neon"})

    assert r.status_code == 400
    assert "neon" in r.json()["error"]["message"], "the error should echo what was rejected"
    assert "daylight" in r.json()["error"]["message"], "the error should list the valid choices"
    assert client.get("/api/settings").json()["theme"] == "hearth"
