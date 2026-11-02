import base64
import os
import shutil
import tempfile

# Les overrides d'environnement DOIVENT précéder tout import `app.*` (y compris
# transitif) : app/core/encryption.py construit son Fernet à l'import, et
# app/database.py construit son engine à l'import.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@127.0.0.1:5432/kyjaB_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"  # DB logique 1 — jamais la 0 (dev, partagée)
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod-" + "x" * 32)
os.environ["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000"

_TEST_MEDIA_DIR = tempfile.mkdtemp(prefix="kyja_test_media_")
os.environ["LOCAL_STORAGE_DIR"] = _TEST_MEDIA_DIR

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.redis_client import get_redis  # noqa: E402
from app.database import Base, engine, get_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_media_dir():
    yield
    shutil.rmtree(_TEST_MEDIA_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def db_engine():
    assert "kyjaB_test" in str(engine.url), "refus d'exécuter les tests contre une base non-test"
    # drop_all + create_all (pas juste create_all) : create_all seul est
    # checkfirst-safe et ne touche jamais une table déjà existante, donc un
    # changement de schéma entre deux sessions de dev (ex: colonne ajoutée à
    # un modèle) laisserait kyjaB_test silencieusement désynchronisée — déjà
    # rencontré concrètement sur ce projet.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine


@pytest.fixture()
def db_session(db_engine):
    connection = db_engine.connect()
    outer_txn = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer_txn.rollback()
        connection.close()


@pytest.fixture()
def client(db_session):
    from app.main import app  # importé seulement ici, après les overrides d'env

    def _override_get_db():
        yield db_session  # pas de close() ici : db_session en garde la propriété

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_test_redis():
    r = get_redis()
    assert r.connection_pool.connection_kwargs.get("db") == 1, "refus de vider une DB Redis non-test"
    r.flushdb()
    yield
    r.flushdb()
