"""Un vrai test de verrouillage multi-connexion n'est pas fiable avec le
harnais de ce projet : db_session lie une seule connexion/transaction par
test (join_transaction_mode="create_savepoint"), jamais commit avant le
teardown. Une 2e connexion réelle ne verrait rien (READ COMMITTED) ou
bloquerait indéfiniment sur le verrou. Ce qui EST testable : deux appels
séquentiels dans la MÊME session/transaction — grâce à "read-your-own-writes",
le 2e appel voit le flush() du 1er et doit détecter le conflit. Ça couvre le
prédicat de chevauchement et le filtre de statuts, pas l'exclusion mutuelle
inter-connexions.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.booking_engine import BookingConflictError, create_catalogue_appointment
from tests.factories import make_client_user, make_hairdresser_user, make_service


def test_second_overlapping_call_conflicts_within_same_session(db_session):
    _, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    service = make_service(db_session, duree_minutes=60)
    start = datetime.now(timezone.utc) + timedelta(days=1)

    create_catalogue_appointment(
        db_session, client_id=client_profile.id, hairdresser=hairdresser, service=service, start_time=start
    )

    with pytest.raises(BookingConflictError):
        create_catalogue_appointment(
            db_session,
            client_id=client_profile.id,
            hairdresser=hairdresser,
            service=service,
            start_time=start + timedelta(minutes=30),
        )


def test_non_overlapping_call_succeeds(db_session):
    _, client_profile = make_client_user(db_session)
    _, hairdresser = make_hairdresser_user(db_session)
    service = make_service(db_session, duree_minutes=30)
    start = datetime.now(timezone.utc) + timedelta(days=1)

    first = create_catalogue_appointment(
        db_session, client_id=client_profile.id, hairdresser=hairdresser, service=service, start_time=start
    )
    second = create_catalogue_appointment(
        db_session,
        client_id=client_profile.id,
        hairdresser=hairdresser,
        service=service,
        start_time=first.end_time + timedelta(minutes=1),
    )
    assert first.id != second.id
