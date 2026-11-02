from sqlalchemy import text

from tests.factories import make_client_user


def test_encrypted_fields_roundtrip_through_orm(db_session):
    _, client_profile = make_client_user(db_session, telephone="514-555-0199", adresse="42 rue Secrète")
    db_session.flush()
    db_session.expire_all()

    reloaded = db_session.get(type(client_profile), client_profile.id)
    assert reloaded.telephone == "514-555-0199"
    assert reloaded.adresse == "42 rue Secrète"


def test_encrypted_fields_are_ciphertext_at_rest(db_session):
    _, client_profile = make_client_user(db_session, telephone="514-555-0199", adresse="42 rue Secrète")
    db_session.flush()

    raw_telephone = db_session.execute(
        text("SELECT telephone FROM clients WHERE id = :id"), {"id": client_profile.id}
    ).scalar()
    raw_adresse = db_session.execute(
        text("SELECT adresse FROM clients WHERE id = :id"), {"id": client_profile.id}
    ).scalar()

    assert raw_telephone != "514-555-0199"
    assert raw_adresse != "42 rue Secrète"
