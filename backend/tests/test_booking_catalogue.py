from datetime import datetime, timedelta, timezone

from app.models.enums import AppointmentStatus, ExperienceLevel
from tests.factories import (
    auth_headers_for,
    make_admin_user,
    make_appointment,
    make_client_user,
    make_hairdresser_user,
    make_service,
)

FUTURE = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def test_book_catalogue_happy_path_computes_price_and_duration(client, db_session):
    user, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session, experience_level=ExperienceLevel.JUNIOR)
    service = make_service(db_session, prix="50.00", duree_minutes=40)

    resp = client.post(
        "/bookings/catalogue",
        json={"hairdresser_id": str(hairdresser.id), "service_id": str(service.id), "start_time": FUTURE},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["price"] == "50.00"

    start = datetime.fromisoformat(body["start_time"])
    end = datetime.fromisoformat(body["end_time"])
    expected_minutes = round(40 * 1.3) + 15  # coefficient junior + buffer
    assert (end - start) == timedelta(minutes=expected_minutes)


def test_book_catalogue_unknown_service_returns_404(client, db_session):
    user, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    import uuid

    resp = client.post(
        "/bookings/catalogue",
        json={"hairdresser_id": str(hairdresser.id), "service_id": str(uuid.uuid4()), "start_time": FUTURE},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 404


def test_book_catalogue_inactive_service_returns_404(client, db_session):
    user, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    service = make_service(db_session, is_active=False)

    resp = client.post(
        "/bookings/catalogue",
        json={"hairdresser_id": str(hairdresser.id), "service_id": str(service.id), "start_time": FUTURE},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 404


def test_book_catalogue_requires_client_role(client, db_session):
    admin = make_admin_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    service = make_service(db_session)

    resp = client.post(
        "/bookings/catalogue",
        json={"hairdresser_id": str(hairdresser.id), "service_id": str(service.id), "start_time": FUTURE},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 403


def test_book_catalogue_rejects_overlapping_slot_for_same_hairdresser(client, db_session):
    user, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    service = make_service(db_session, duree_minutes=60)

    start = datetime.now(timezone.utc) + timedelta(days=3)
    make_appointment(
        db_session,
        client_id=client_profile.id,
        hairdresser_id=hairdresser.id,
        service_id=service.id,
        start_time=start,
        end_time=start + timedelta(minutes=90),
        status=AppointmentStatus.CONFIRMED,
    )
    db_session.commit()

    overlapping_start = (start + timedelta(minutes=30)).isoformat()
    resp = client.post(
        "/bookings/catalogue",
        json={"hairdresser_id": str(hairdresser.id), "service_id": str(service.id), "start_time": overlapping_start},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 409


def test_get_booking_404_for_other_client(client, db_session):
    owner, owner_profile = make_client_user(db_session)
    other, _ = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    service = make_service(db_session)
    appointment = make_appointment(
        db_session, client_id=owner_profile.id, hairdresser_id=hairdresser.id, service_id=service.id
    )

    resp_owner = client.get(f"/bookings/{appointment.id}", headers=auth_headers_for(owner))
    assert resp_owner.status_code == 200

    resp_other = client.get(f"/bookings/{appointment.id}", headers=auth_headers_for(other))
    assert resp_other.status_code == 404


def test_get_booking_visible_to_assigned_hairdresser_and_admin(client, db_session):
    owner, owner_profile = make_client_user(db_session)
    hairdresser_user, hairdresser = make_hairdresser_user(db_session)
    admin = make_admin_user(db_session)
    service = make_service(db_session)
    appointment = make_appointment(
        db_session, client_id=owner_profile.id, hairdresser_id=hairdresser.id, service_id=service.id
    )

    assert client.get(f"/bookings/{appointment.id}", headers=auth_headers_for(hairdresser_user)).status_code == 200
    assert client.get(f"/bookings/{appointment.id}", headers=auth_headers_for(admin)).status_code == 200


def test_cancel_then_rebook_same_slot_succeeds(client, db_session):
    user, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    service = make_service(db_session, duree_minutes=60)

    start = datetime.now(timezone.utc) + timedelta(days=4)
    appointment = make_appointment(
        db_session,
        client_id=client_profile.id,
        hairdresser_id=hairdresser.id,
        service_id=service.id,
        start_time=start,
        end_time=start + timedelta(minutes=90),
        status=AppointmentStatus.CONFIRMED,
    )
    db_session.commit()

    cancel_resp = client.patch(f"/bookings/{appointment.id}/cancel", headers=auth_headers_for(user))
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    rebook_resp = client.post(
        "/bookings/catalogue",
        json={"hairdresser_id": str(hairdresser.id), "service_id": str(service.id), "start_time": start.isoformat()},
        headers=auth_headers_for(user),
    )
    assert rebook_resp.status_code == 201


def test_cancel_already_cancelled_booking_returns_409(client, db_session):
    user, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    appointment = make_appointment(
        db_session,
        client_id=client_profile.id,
        hairdresser_id=hairdresser.id,
        status=AppointmentStatus.CANCELLED,
        price=None,
    )

    resp = client.patch(f"/bookings/{appointment.id}/cancel", headers=auth_headers_for(user))
    assert resp.status_code == 409
