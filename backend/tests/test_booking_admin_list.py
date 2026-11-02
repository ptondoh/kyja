from datetime import datetime, timedelta, timezone

from app.models.enums import AppointmentStatus
from tests.factories import auth_headers_for, make_admin_user, make_appointment, make_client_user, make_hairdresser_user


def test_list_all_bookings_requires_admin(client, db_session):
    user, _ = make_client_user(db_session)

    resp = client.get("/bookings", headers=auth_headers_for(user))
    assert resp.status_code == 403


def test_list_all_bookings_returns_every_client(client, db_session):
    admin = make_admin_user(db_session)
    _, client_a = make_client_user(db_session, email="clienta@example.com")
    _, client_b = make_client_user(db_session, email="clientb@example.com")
    _, hairdresser = make_hairdresser_user(db_session)

    make_appointment(db_session, client_id=client_a.id, hairdresser_id=hairdresser.id)
    make_appointment(db_session, client_id=client_b.id, hairdresser_id=hairdresser.id)
    db_session.commit()

    resp = client.get("/bookings", headers=auth_headers_for(admin))
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert "client" in resp.json()[0]
    assert "nom" in resp.json()[0]["client"]


def test_list_all_bookings_filters_by_status(client, db_session):
    admin = make_admin_user(db_session)
    _, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    make_appointment(
        db_session, client_id=client_profile.id, hairdresser_id=hairdresser.id, status=AppointmentStatus.CONFIRMED
    )
    pending_start = datetime.now(timezone.utc) + timedelta(days=3)
    make_appointment(
        db_session,
        client_id=client_profile.id,
        hairdresser_id=hairdresser.id,
        start_time=pending_start,
        end_time=pending_start + timedelta(minutes=75),
        status=AppointmentStatus.PENDING_QUOTE,
        price=None,
    )
    db_session.commit()

    resp = client.get("/bookings?status=pending_quote", headers=auth_headers_for(admin))
    assert resp.status_code == 200
    bodies = resp.json()
    assert len(bodies) == 1
    assert bodies[0]["status"] == "pending_quote"


def test_list_all_bookings_filters_by_hairdresser(client, db_session):
    admin = make_admin_user(db_session)
    _, client_profile = make_client_user(db_session)
    _, hairdresser_a = make_hairdresser_user(db_session, email="coiffeusea@example.com")
    _, hairdresser_b = make_hairdresser_user(db_session, email="coiffeuseb@example.com")

    make_appointment(db_session, client_id=client_profile.id, hairdresser_id=hairdresser_a.id)
    make_appointment(db_session, client_id=client_profile.id, hairdresser_id=hairdresser_b.id)
    db_session.commit()

    resp = client.get(f"/bookings?hairdresser_id={hairdresser_a.id}", headers=auth_headers_for(admin))
    assert resp.status_code == 200
    bodies = resp.json()
    assert len(bodies) == 1
    assert bodies[0]["hairdresser"]["id"] == str(hairdresser_a.id)


def test_list_all_bookings_filters_by_date_range(client, db_session):
    admin = make_admin_user(db_session)
    _, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    near_start = datetime.now(timezone.utc) + timedelta(days=1)
    far_start = datetime.now(timezone.utc) + timedelta(days=10)
    make_appointment(
        db_session,
        client_id=client_profile.id,
        hairdresser_id=hairdresser.id,
        start_time=near_start,
        end_time=near_start + timedelta(minutes=60),
    )
    make_appointment(
        db_session,
        client_id=client_profile.id,
        hairdresser_id=hairdresser.id,
        start_time=far_start,
        end_time=far_start + timedelta(minutes=60),
    )
    db_session.commit()

    cutoff = (near_start + timedelta(days=1)).isoformat()
    resp = client.get("/bookings", params={"start_before": cutoff}, headers=auth_headers_for(admin))
    assert resp.status_code == 200
    bodies = resp.json()
    assert len(bodies) == 1
    assert datetime.fromisoformat(bodies[0]["start_time"]) == near_start
