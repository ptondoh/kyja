from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.image_processing import compute_phash, validate_and_process_image
from app.models import MediaItem
from tests.factories import auth_headers_for, make_client_user, make_hairdresser_user, make_jpeg_bytes, make_service

FUTURE = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def test_devis_description_only_succeeds(client, db_session):
    user, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    resp = client.post(
        "/bookings/devis",
        data={"hairdresser_id": str(hairdresser.id), "start_time": FUTURE, "description": "Je veux une frange"},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending_quote"
    assert body["price"] is None
    assert body["description"] == "Je veux une frange"


def test_devis_photos_only_without_description_succeeds(client, db_session):
    user, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    resp = client.post(
        "/bookings/devis",
        data={"hairdresser_id": str(hairdresser.id), "start_time": FUTURE},
        files={"photos": ("look.jpg", make_jpeg_bytes(), "image/jpeg")},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["description"] is None
    assert len(body["media"]) == 1


def test_devis_requires_description_or_photo(client, db_session):
    user, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    resp = client.post(
        "/bookings/devis",
        data={"hairdresser_id": str(hairdresser.id), "start_time": FUTURE},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 422


def test_devis_photo_gets_phash_and_appointment_owner(client, db_session):
    user, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    resp = client.post(
        "/bookings/devis",
        data={"hairdresser_id": str(hairdresser.id), "start_time": FUTURE},
        files={"photos": ("look.jpg", make_jpeg_bytes(), "image/jpeg")},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 201
    appointment_id = resp.json()["id"]

    media_items = db_session.execute(
        select(MediaItem).where(MediaItem.appointment_id == appointment_id)
    ).scalars().all()
    assert len(media_items) == 1
    assert media_items[0].phash is not None


def test_devis_suggests_matching_service_from_photo(client, db_session):
    user, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    raw = make_jpeg_bytes(color=(80, 160, 200))
    processed = validate_and_process_image(raw)
    phash = compute_phash(processed)
    matching_service = make_service(db_session, nom="Balayage", prix="120.00", duree_minutes=90)
    db_session.add(
        MediaItem(service_id=matching_service.id, kind="image", url="/media/catalogue.webp", phash=phash, position=0)
    )
    db_session.commit()

    resp = client.post(
        "/bookings/devis",
        data={"hairdresser_id": str(hairdresser.id), "start_time": FUTURE},
        files={"photos": ("look.jpg", raw, "image/jpeg")},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["suggested_service_id"] == str(matching_service.id)
    assert body["suggested_price"] == "120.00"
    assert body["suggested_duration_minutes"] == 90


def test_devis_no_match_leaves_suggestion_null(client, db_session):
    user, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    resp = client.post(
        "/bookings/devis",
        data={"hairdresser_id": str(hairdresser.id), "start_time": FUTURE},
        files={"photos": ("look.jpg", make_jpeg_bytes(color=(5, 5, 5)), "image/jpeg")},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["suggested_service_id"] is None
    assert body["suggested_price"] is None
