from datetime import datetime, timedelta, timezone

from app.models.enums import AppointmentStatus
from tests.factories import auth_headers_for, make_admin_user, make_appointment, make_client_user, make_hairdresser_user


def _make_pending_quote_appointment(db_session, *, start_time=None):
    user, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    start_time = start_time or (datetime.now(timezone.utc) + timedelta(days=2))
    appointment = make_appointment(
        db_session,
        client_id=client_profile.id,
        hairdresser_id=hairdresser.id,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=75),
        status=AppointmentStatus.PENDING_QUOTE,
        price=None,
        description="Coloration complète",
    )
    db_session.commit()
    return appointment, hairdresser


def test_confirm_quote_sets_price_and_status(client, db_session):
    appointment, _ = _make_pending_quote_appointment(db_session)
    admin = make_admin_user(db_session)

    resp = client.patch(
        f"/bookings/{appointment.id}/confirm-quote",
        json={"price": "85.00"},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["price"] == "85.00"


def test_confirm_quote_requires_admin(client, db_session):
    appointment, _ = _make_pending_quote_appointment(db_session)
    user, _ = make_client_user(db_session)

    resp = client.patch(
        f"/bookings/{appointment.id}/confirm-quote",
        json={"price": "85.00"},
        headers=auth_headers_for(user),
    )
    assert resp.status_code == 403


def test_confirm_quote_on_non_pending_booking_returns_409(client, db_session):
    user, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    appointment = make_appointment(
        db_session, client_id=client_profile.id, hairdresser_id=hairdresser.id, status=AppointmentStatus.CONFIRMED
    )
    admin = make_admin_user(db_session)

    resp = client.patch(
        f"/bookings/{appointment.id}/confirm-quote",
        json={"price": "85.00"},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 409


def test_confirm_quote_duration_override_conflict_applies_no_mutation(client, db_session):
    start_time = datetime.now(timezone.utc) + timedelta(days=5)
    appointment, hairdresser = _make_pending_quote_appointment(db_session, start_time=start_time)
    admin = make_admin_user(db_session)

    # Un autre RDV confirmé juste après le créneau original de 75 min + 15 min buffer.
    other_user, other_client = make_client_user(db_session)
    blocking_start = start_time + timedelta(minutes=120)
    make_appointment(
        db_session,
        client_id=other_client.id,
        hairdresser_id=hairdresser.id,
        start_time=blocking_start,
        end_time=blocking_start + timedelta(minutes=60),
        status=AppointmentStatus.CONFIRMED,
    )
    db_session.commit()

    # Une durée bien plus longue entrerait maintenant en collision avec ce RDV bloquant.
    resp = client.patch(
        f"/bookings/{appointment.id}/confirm-quote",
        json={"price": "200.00", "duration_minutes": 180},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 409

    unchanged = client.get(f"/bookings/{appointment.id}", headers=auth_headers_for(admin))
    assert unchanged.json()["status"] == "pending_quote"
    assert unchanged.json()["price"] is None
