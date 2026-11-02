from tests.factories import auth_headers_for, make_admin_user, make_client_user, make_media_item, make_product

NEW_PRODUCT_PAYLOAD = {"nom": "Shampoing Pro", "prix": "25.00"}


def test_create_product_requires_admin(client, db_session):
    user, _ = make_client_user(db_session)
    resp_client = client.post("/products", json=NEW_PRODUCT_PAYLOAD, headers=auth_headers_for(user))
    assert resp_client.status_code == 403

    resp_anon = client.post("/products", json=NEW_PRODUCT_PAYLOAD)
    assert resp_anon.status_code == 401


def test_create_product_as_admin_succeeds(client, db_session):
    admin = make_admin_user(db_session)
    resp = client.post("/products", json=NEW_PRODUCT_PAYLOAD, headers=auth_headers_for(admin))
    assert resp.status_code == 201
    assert resp.json()["nom"] == "Shampoing Pro"


def test_list_products_only_returns_active(client, db_session):
    make_product(db_session, nom="Actif", is_active=True)
    make_product(db_session, nom="Inactif", is_active=False)

    resp = client.get("/products")
    assert resp.status_code == 200
    noms = [p["nom"] for p in resp.json()]
    assert "Actif" in noms
    assert "Inactif" not in noms


def test_get_product_404_for_unknown_id(client):
    import uuid

    resp = client.get(f"/products/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_update_product_partial(client, db_session):
    admin = make_admin_user(db_session)
    product = make_product(db_session, nom="Avant", prix="10.00")

    resp = client.put(f"/products/{product.id}", json={"prix": "15.00"}, headers=auth_headers_for(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["nom"] == "Avant"
    assert body["prix"] == "15.00"


def test_deactivate_product_hides_from_public_list_but_not_direct_get(client, db_session):
    admin = make_admin_user(db_session)
    product = make_product(db_session, is_active=True)

    resp = client.patch(f"/products/{product.id}/deactivate", headers=auth_headers_for(admin))
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    list_resp = client.get("/products")
    assert all(p["id"] != str(product.id) for p in list_resp.json())

    direct_resp = client.get(f"/products/{product.id}")
    assert direct_resp.status_code == 200


def test_detach_media_cross_owner_returns_404(client, db_session):
    admin = make_admin_user(db_session)
    product_a = make_product(db_session, nom="A")
    product_b = make_product(db_session, nom="B")
    media = make_media_item(db_session, product_id=product_a.id)

    resp = client.delete(f"/products/{product_b.id}/media/{media.id}", headers=auth_headers_for(admin))
    assert resp.status_code == 404


def test_reorder_media_rejects_incomplete_id_set(client, db_session):
    admin = make_admin_user(db_session)
    product = make_product(db_session)
    media_a = make_media_item(db_session, product_id=product.id, position=0)
    make_media_item(db_session, product_id=product.id, position=1)

    resp = client.put(
        f"/products/{product.id}/media/reorder",
        json={"media_ids": [str(media_a.id)]},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 422


def test_reorder_media_happy_path(client, db_session):
    admin = make_admin_user(db_session)
    product = make_product(db_session)
    media_a = make_media_item(db_session, product_id=product.id, position=0)
    media_b = make_media_item(db_session, product_id=product.id, position=1)

    resp = client.put(
        f"/products/{product.id}/media/reorder",
        json={"media_ids": [str(media_b.id), str(media_a.id)]},
        headers=auth_headers_for(admin),
    )
    assert resp.status_code == 200
    ordered_ids = [m["id"] for m in resp.json()]
    assert ordered_ids == [str(media_b.id), str(media_a.id)]
