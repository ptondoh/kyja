from tests.factories import auth_headers_for, make_admin_user, make_client_user, make_media_item, make_service

NEW_SERVICE_PAYLOAD = {"nom": "Coupe Femme", "prix": "45.00", "duree_minutes": 45, "categorie": "Coiffure"}


def test_create_service_requires_admin(client, db_session):
    user, _ = make_client_user(db_session)
    resp_client = client.post("/services", json=NEW_SERVICE_PAYLOAD, headers=auth_headers_for(user))
    assert resp_client.status_code == 403

    resp_anon = client.post("/services", json=NEW_SERVICE_PAYLOAD)
    assert resp_anon.status_code == 401


def test_create_service_as_admin_succeeds(client, db_session):
    admin = make_admin_user(db_session)
    resp = client.post("/services", json=NEW_SERVICE_PAYLOAD, headers=auth_headers_for(admin))
    assert resp.status_code == 201
    assert resp.json()["nom"] == "Coupe Femme"


def test_list_services_only_returns_active(client, db_session):
    make_service(db_session, nom="Actif", is_active=True)
    make_service(db_session, nom="Inactif", is_active=False)

    resp = client.get("/services")
    assert resp.status_code == 200
    noms = [s["nom"] for s in resp.json()]
    assert "Actif" in noms
    assert "Inactif" not in noms


def test_list_services_pagination_caps_limit(client, db_session):
    for i in range(5):
        make_service(db_session, nom=f"Service {i}")

    resp = client.get("/services", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp_over_cap = client.get("/services", params={"limit": 1000})
    assert resp_over_cap.status_code == 422


def test_get_service_404_for_unknown_id(client):
    import uuid

    resp = client.get(f"/services/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_update_service_partial(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session, nom="Avant", prix="10.00")

    resp = client.put(f"/services/{service.id}", json={"prix": "15.00"}, headers=auth_headers_for(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["nom"] == "Avant"
    assert body["prix"] == "15.00"


def test_deactivate_service_hides_from_public_list_but_not_direct_get(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session, is_active=True)

    resp = client.patch(f"/services/{service.id}/deactivate", headers=auth_headers_for(admin))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    list_resp = client.get("/services")
    assert all(s["id"] != str(service.id) for s in list_resp.json())

    direct_resp = client.get(f"/services/{service.id}")
    assert direct_resp.status_code == 200


def test_detach_media_cross_owner_returns_404(client, db_session):
    admin = make_admin_user(db_session)
    service_a = make_service(db_session, nom="A")
    service_b = make_service(db_session, nom="B")
    media = make_media_item(db_session, service_id=service_a.id)

    resp = client.delete(f"/services/{service_b.id}/media/{media.id}", headers=auth_headers_for(admin))
    assert resp.status_code == 404


def test_detach_media_succeeds_for_correct_owner(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)
    media = make_media_item(db_session, service_id=service.id)

    resp = client.delete(f"/services/{service.id}/media/{media.id}", headers=auth_headers_for(admin))
    assert resp.status_code == 204


def test_reorder_media_rejects_incomplete_id_set(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)
    media_a = make_media_item(db_session, service_id=service.id, position=0)
    make_media_item(db_session, service_id=service.id, position=1)

    resp = client.put(
        f"/services/{service.id}/media/reorder",
        json={"media_ids": [str(media_a.id)]},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 422


def test_reorder_media_happy_path(client, db_session):
    admin = make_admin_user(db_session)
    service = make_service(db_session)
    media_a = make_media_item(db_session, service_id=service.id, position=0)
    media_b = make_media_item(db_session, service_id=service.id, position=1)

    resp = client.put(
        f"/services/{service.id}/media/reorder",
        json={"media_ids": [str(media_b.id), str(media_a.id)]},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 200
    ordered_ids = [m["id"] for m in resp.json()]
    assert ordered_ids == [str(media_b.id), str(media_a.id)]
