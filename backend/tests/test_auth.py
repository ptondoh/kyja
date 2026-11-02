from sqlalchemy import select

from app.models import Client, ConsentRecord, User
from tests.factories import make_client_user, make_user

REGISTER_PAYLOAD = {
    "email": "nouvelle.cliente@example.com",
    "password": "SuperSecret123",
    "nom": "Bouchard",
    "prenom": "Nadia",
    "telephone": "514-555-0111",
    "adresse": "10 rue des Fleurs",
    "marketing_opt_in": True,
    "terms_accepted": True,
}


def test_register_creates_user_client_and_consent_records(client, db_session):
    resp = client.post("/auth/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == REGISTER_PAYLOAD["email"]

    user = db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"])).scalar_one()
    client_profile = db_session.execute(select(Client).where(Client.user_id == user.id)).scalar_one()
    consents = db_session.execute(select(ConsentRecord).where(ConsentRecord.client_id == client_profile.id)).scalars().all()
    assert len(consents) == 2


def test_register_duplicate_email_returns_409(client, db_session):
    make_user(db_session, email=REGISTER_PAYLOAD["email"])
    resp = client.post("/auth/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 409


def test_register_requires_terms_accepted(client):
    payload = {**REGISTER_PAYLOAD, "terms_accepted": False}
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 422


def test_login_success_sets_cookies_and_returns_access_token(client, db_session):
    make_client_user(db_session, email="login.ok@example.com", password="GoodPassword1")
    resp = client.post("/auth/login", json={"email": "login.ok@example.com", "password": "GoodPassword1"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert resp.cookies.get("refresh_token") is not None
    assert resp.cookies.get("csrf_refresh_token") is not None


def test_login_wrong_password_returns_401(client, db_session):
    make_client_user(db_session, email="login.bad@example.com", password="GoodPassword1")
    resp = client.post("/auth/login", json={"email": "login.bad@example.com", "password": "WrongPassword"})
    assert resp.status_code == 401


def test_login_rate_limited_after_five_failed_attempts(client, db_session):
    make_client_user(db_session, email="ratelimit@example.com", password="GoodPassword1")
    for _ in range(5):
        resp = client.post("/auth/login", json={"email": "ratelimit@example.com", "password": "wrong"})
        assert resp.status_code == 401
    resp = client.post("/auth/login", json={"email": "ratelimit@example.com", "password": "wrong"})
    assert resp.status_code == 429


def test_me_requires_bearer_token(client, db_session):
    user, _ = make_client_user(db_session)
    from tests.factories import auth_headers_for

    resp_ok = client.get("/auth/me", headers=auth_headers_for(user))
    assert resp_ok.status_code == 200

    resp_no_auth = client.get("/auth/me")
    assert resp_no_auth.status_code == 401


def test_refresh_requires_csrf_header(client, db_session):
    make_client_user(db_session, email="refresh.csrf@example.com", password="GoodPassword1")
    client.post("/auth/login", json={"email": "refresh.csrf@example.com", "password": "GoodPassword1"})

    resp_no_csrf = client.post("/auth/refresh")
    assert resp_no_csrf.status_code == 403

    resp_wrong_csrf = client.post("/auth/refresh", headers={"X-CSRF-Token": "not-the-right-value"})
    assert resp_wrong_csrf.status_code == 403


def test_refresh_rotates_token_and_rejects_replay(client, db_session):
    make_client_user(db_session, email="refresh.rotate@example.com", password="GoodPassword1")
    login_resp = client.post("/auth/login", json={"email": "refresh.rotate@example.com", "password": "GoodPassword1"})
    old_refresh = login_resp.cookies.get("refresh_token")
    old_csrf = login_resp.cookies.get("csrf_refresh_token")

    refresh_resp = client.post("/auth/refresh", headers={"X-CSRF-Token": old_csrf})
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["user"]["email"] == "refresh.rotate@example.com"
    # Le nouveau refresh cookie doit avoir changé (preuve de rotation) même si
    # l'access token JWT peut être identique en cas de collision à la seconde
    # près (iat/exp n'ont pas de nonce) — ce n'est pas un bug, juste pas un
    # signal fiable pour ce test.
    assert refresh_resp.cookies.get("refresh_token") != old_refresh

    replay_resp = client.post(
        "/auth/refresh",
        headers={"X-CSRF-Token": old_csrf},
        cookies={"refresh_token": old_refresh, "csrf_refresh_token": old_csrf},
    )
    assert replay_resp.status_code == 401


def test_logout_revokes_refresh_token(client, db_session):
    user, _ = make_client_user(db_session, email="logout.me@example.com", password="GoodPassword1")
    login_resp = client.post("/auth/login", json={"email": "logout.me@example.com", "password": "GoodPassword1"})
    from tests.factories import auth_headers_for

    old_refresh = login_resp.cookies.get("refresh_token")
    old_csrf = login_resp.cookies.get("csrf_refresh_token")

    logout_resp = client.post("/auth/logout", headers=auth_headers_for(user))
    assert logout_resp.status_code == 204

    # Le logout a effacé les cookies côté jar ; on renvoie explicitement les
    # anciennes valeurs pour tester que le token lui-même est bien révoqué en
    # base (401), pas juste que le cookie CSRF a disparu (403).
    refresh_after_logout = client.post(
        "/auth/refresh",
        headers={"X-CSRF-Token": old_csrf},
        cookies={"refresh_token": old_refresh, "csrf_refresh_token": old_csrf},
    )
    assert refresh_after_logout.status_code == 401
