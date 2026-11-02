from app.models.enums import ExperienceLevel
from tests.factories import auth_headers_for, make_admin_user, make_client_user, make_hairdresser_user

VALID_PAYLOAD = {
    "email": "nouvelle.coiffeuse@example.com",
    "password": "CorrectHorse123!",
    "nom": "Roy",
    "prenom": "Sarah",
    "bio": "Spécialiste balayage",
    "experience_level": "senior",
    "is_independent": False,
}


def test_create_hairdresser_succeeds_as_admin(client, db_session):
    admin = make_admin_user(db_session)

    resp = client.post("/hairdressers", json=VALID_PAYLOAD, headers=auth_headers_for(admin))
    assert resp.status_code == 201
    body = resp.json()
    assert body["nom"] == "Roy"
    assert body["is_active"] is True


def test_create_hairdresser_duplicate_email_returns_409(client, db_session):
    admin = make_admin_user(db_session)
    make_hairdresser_user(db_session, email="deja.prise@example.com")

    payload = {**VALID_PAYLOAD, "email": "deja.prise@example.com"}
    resp = client.post("/hairdressers", json=payload, headers=auth_headers_for(admin))
    assert resp.status_code == 409


def test_create_hairdresser_requires_admin(client, db_session):
    user, _ = make_client_user(db_session)

    resp = client.post("/hairdressers", json=VALID_PAYLOAD, headers=auth_headers_for(user))
    assert resp.status_code == 403


def test_list_hairdressers_excludes_deactivated(client, db_session):
    _, active = make_hairdresser_user(db_session, email="active@example.com")
    inactive_user, inactive = make_hairdresser_user(db_session, email="inactive@example.com")
    inactive_user.is_active = False
    db_session.commit()

    resp = client.get("/hairdressers")
    assert resp.status_code == 200
    ids = [h["id"] for h in resp.json()]
    assert str(active.id) in ids
    assert str(inactive.id) not in ids


def test_update_hairdresser_partial(client, db_session):
    admin = make_admin_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)

    resp = client.patch(
        f"/hairdressers/{hairdresser.id}",
        json={"experience_level": "expert"},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["experience_level"] == "expert"
    assert resp.json()["nom"] == hairdresser.nom


def test_deactivate_hairdresser_blocks_login(client, db_session):
    admin = make_admin_user(db_session)
    hairdresser_user, hairdresser = make_hairdresser_user(
        db_session, email="aretirer@example.com", password="CorrectHorse123!"
    )

    resp = client.patch(f"/hairdressers/{hairdresser.id}/deactivate", headers=auth_headers_for(admin))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    login_resp = client.post(
        "/auth/login", json={"email": "aretirer@example.com", "password": "CorrectHorse123!"}
    )
    assert login_resp.status_code == 401


def test_get_unknown_hairdresser_returns_404(client, db_session):
    import uuid

    resp = client.get(f"/hairdressers/{uuid.uuid4()}")
    assert resp.status_code == 404
