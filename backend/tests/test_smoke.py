from sqlalchemy import text

from tests.factories import make_admin_user, make_client_user


def test_db_session_isolated(db_session):
    user, client_profile = make_client_user(db_session)
    assert user.id is not None
    assert client_profile.user_id == user.id


def test_previous_test_data_not_visible(db_session):
    # Si l'isolation par savepoint fonctionne, la table users est vide ici
    # malgré le test précédent qui y a inséré une ligne.
    count = db_session.execute(text("SELECT count(*) FROM users")).scalar()
    assert count == 0


def test_client_fixture_and_me_endpoint(client, db_session):
    from tests.factories import auth_headers_for

    admin = make_admin_user(db_session)
    resp = client.get("/auth/me", headers=auth_headers_for(admin))
    assert resp.status_code == 200
    assert resp.json()["email"] == admin.email
