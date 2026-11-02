from pathlib import Path

from app.config import settings
from app.models import MediaItem
from tests.factories import auth_headers_for, make_admin_user, make_jpeg_bytes, make_service


def test_upload_valid_image_succeeds_and_sets_phash(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)

    resp = client.post(
        f"/services/{service.id}/media",
        headers=auth_headers_for(admin),
        data={"kind": "image"},
        files={"file": ("photo.jpg", make_jpeg_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["kind"] == "image"
    assert body["url"].startswith("/media/services/")

    media = db_session.get(MediaItem, body["id"])
    assert media.phash is not None

    disk_path = Path(settings.LOCAL_STORAGE_DIR) / body["url"].removeprefix("/media/")
    assert disk_path.exists()


def test_upload_non_image_file_rejected(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)

    resp = client.post(
        f"/services/{service.id}/media",
        headers=auth_headers_for(admin),
        data={"kind": "image"},
        files={"file": ("fake.jpg", b"not an image at all", "image/jpeg")},
    )
    assert resp.status_code == 422


def test_upload_image_with_url_field_rejected(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)

    resp = client.post(
        f"/services/{service.id}/media",
        headers=auth_headers_for(admin),
        data={"kind": "image", "url": "https://example.com/x.jpg"},
        files={"file": ("photo.jpg", make_jpeg_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 422


def test_attach_video_by_url_still_works(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)

    resp = client.post(
        f"/services/{service.id}/media",
        headers=auth_headers_for(admin),
        data={
            "kind": "video",
            "url": "https://example.com/v1.mp4",
            "thumbnail_url": "https://example.com/t.jpg",
            "duration_seconds": "20",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["kind"] == "video"


def test_attach_video_with_file_rejected(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)

    resp = client.post(
        f"/services/{service.id}/media",
        headers=auth_headers_for(admin),
        data={
            "kind": "video",
            "url": "https://example.com/v1.mp4",
            "thumbnail_url": "https://example.com/t.jpg",
            "duration_seconds": "20",
        },
        files={"file": ("x.mp4", b"fake video bytes", "video/mp4")},
    )
    assert resp.status_code == 422


def test_attach_video_missing_required_fields_rejected(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)

    resp = client.post(
        f"/services/{service.id}/media",
        headers=auth_headers_for(admin),
        data={"kind": "video", "url": "https://example.com/v1.mp4"},
    )
    assert resp.status_code == 422
