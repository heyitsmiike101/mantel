import io

import pytest
from PIL import Image

from app.services import photos as photo_service


def make_image(fmt="JPEG", size=(800, 600), color=(120, 160, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


def upload(client, data: bytes, name="photo.jpg", content_type="image/jpeg"):
    return client.post("/api/photos", files={"file": (name, data, content_type)})


@pytest.fixture(autouse=True)
def clean_photo_dir():
    """Each test starts with an empty library; the dir is shared per test session."""
    for f in photo_service.photo_dir().glob("*"):
        f.unlink()
    yield
    for f in photo_service.photo_dir().glob("*"):
        f.unlink()


# ------------------------------- happy path ----------------------------------


def test_upload_and_list(client):
    r = upload(client, make_image())
    assert r.status_code == 201
    body = r.json()
    assert body["width"] == 800
    assert body["url"] == f"/api/photos/{body['id']}/file"

    listed = client.get("/api/photos").json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_png_and_webp_are_accepted(client):
    assert upload(client, make_image("PNG"), "a.png", "image/png").status_code == 201
    assert upload(client, make_image("WEBP"), "b.webp", "image/webp").status_code == 201


def test_uploaded_file_is_served_back(client):
    photo_id = upload(client, make_image()).json()["id"]
    r = client.get(f"/api/photos/{photo_id}/file")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    # It must come back as a decodable image, not the bytes we happened to send.
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.format == "JPEG"


def test_oversized_image_is_downscaled(client):
    body = upload(client, make_image(size=(4000, 3000))).json()
    assert max(body["width"], body["height"]) == photo_service.MAX_DIMENSION
    assert body["width"] == 2560 and body["height"] == 1920, "aspect ratio must hold"


def test_exif_is_stripped(client):
    """Phone photos carry GPS coordinates. Re-encoding must drop them."""
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100))
    exif = img.getexif()
    exif[0x9286] = "secret location note"
    img.save(buf, format="JPEG", exif=exif)

    photo_id = upload(client, buf.getvalue()).json()["id"]
    served = client.get(f"/api/photos/{photo_id}/file").content
    with Image.open(io.BytesIO(served)) as out:
        assert not dict(out.getexif()), "re-encoded image must carry no EXIF"


def test_delete_removes_row_and_file(client):
    photo_id = upload(client, make_image()).json()["id"]
    stored = list(photo_service.photo_dir().glob("*"))
    assert len(stored) == 1

    assert client.delete(f"/api/photos/{photo_id}").status_code == 204
    assert client.get("/api/photos").json() == []
    assert list(photo_service.photo_dir().glob("*")) == [], "file must go with the row"
    assert client.get(f"/api/photos/{photo_id}/file").status_code == 404


def test_photos_keep_upload_order(client):
    ids = [upload(client, make_image(color=(i * 30, 0, 0))).json()["id"] for i in range(3)]
    assert [p["id"] for p in client.get("/api/photos").json()] == ids


# ------------------------------- rejections ----------------------------------


def test_non_image_disguised_as_jpeg_is_rejected(client):
    """The declared content type and the extension are both attacker-controlled;
    only decoding the bytes decides."""
    r = upload(client, b"#!/bin/sh\nrm -rf /\n", "innocent.jpg", "image/jpeg")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"
    assert list(photo_service.photo_dir().glob("*")) == []


def test_html_polyglot_is_rejected(client):
    r = upload(client, b"<html><script>alert(1)</script></html>", "x.png", "image/png")
    assert r.status_code == 400


def test_empty_upload_is_rejected(client):
    assert upload(client, b"").status_code == 400


def test_oversized_upload_is_rejected(client, monkeypatch):
    monkeypatch.setattr(photo_service, "MAX_UPLOAD_BYTES", 1024)
    r = upload(client, make_image(size=(1200, 1200)))
    assert r.status_code == 400
    assert "larger than" in r.json()["error"]["message"]


def test_full_library_is_rejected(client, monkeypatch):
    upload(client, make_image())
    monkeypatch.setattr(photo_service, "MAX_LIBRARY_BYTES", 1)
    r = upload(client, make_image())
    assert r.status_code == 400
    assert "full" in r.json()["error"]["message"]


def test_missing_photo_404s(client):
    assert client.get("/api/photos/999/file").status_code == 404
    assert client.delete("/api/photos/999").status_code == 404


# --------------------------- path traversal ----------------------------------


@pytest.mark.parametrize(
    "filename",
    ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "/etc/passwd", "sub/dir.jpg", ""],
)
def test_path_for_refuses_to_escape_the_photo_directory(filename):
    with pytest.raises(photo_service.PhotoError):
        photo_service.path_for(filename)


def test_stored_filename_ignores_the_uploaded_name(client):
    """Even a hostile filename can't influence where the file lands, because the
    stored name is generated server-side."""
    body = upload(client, make_image(), "../../../evil.jpg").json()
    stored = list(photo_service.photo_dir().glob("*"))
    assert len(stored) == 1
    assert stored[0].name.endswith(".jpg")
    assert "evil" not in stored[0].name and ".." not in stored[0].name
    assert body["original_name"] == "../../../evil.jpg", "recorded, but never used as a path"


def test_traversal_row_cannot_read_outside(client, db):
    """A hand-edited database row must not become an arbitrary file read."""
    from app.models import Photo

    photo = Photo(
        filename="../../../../etc/passwd",
        content_type="image/jpeg",
        size_bytes=1,
        width=1,
        height=1,
    )
    db.add(photo)
    db.commit()
    assert client.get(f"/api/photos/{photo.id}/file").status_code == 404


# ------------------------------- settings ------------------------------------


def test_screensaver_settings_are_exposed_and_patchable(client):
    settings = client.get("/api/settings").json()
    assert settings["screensaver_enabled"] is True
    assert settings["screensaver_delay_minutes"] == 5
    assert settings["sleep_enabled"] is False

    updated = client.patch(
        "/api/settings",
        json={"screensaver_mode": "clock", "sleep_enabled": True, "sleep_start_hour": 22},
    ).json()
    assert updated["screensaver_mode"] == "clock"
    assert updated["sleep_enabled"] is True
    assert updated["sleep_start_hour"] == 22
