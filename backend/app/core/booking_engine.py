import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.image_processing import find_similar_media
from app.models import Appointment, Hairdresser, Service
from app.models.enums import AppointmentStatus

# Pas de configuration par service/salon pour l'instant (différé, cf. PRD V1)
# — constante simple plutôt qu'un réglage Settings que personne ne peut encore
# ajuster sans redéploiement de toute façon.
DEFAULT_BUFFER_MINUTES = 15
DEFAULT_DEVIS_DURATION_MINUTES = 60
SUGGESTION_MAX_DISTANCE = 10

BLOCKING_STATUSES = (AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING_QUOTE)


class BookingConflictError(Exception):
    pass


def compute_catalogue_window(service: Service, hairdresser: Hairdresser, start_time: datetime) -> tuple[datetime, int]:
    duration_minutes = round(service.duree_minutes * hairdresser.duration_coefficient)
    end_time = start_time + timedelta(minutes=duration_minutes) + timedelta(minutes=DEFAULT_BUFFER_MINUTES)
    return end_time, DEFAULT_BUFFER_MINUTES


def compute_devis_window(start_time: datetime) -> tuple[datetime, int]:
    end_time = start_time + timedelta(minutes=DEFAULT_DEVIS_DURATION_MINUTES) + timedelta(minutes=DEFAULT_BUFFER_MINUTES)
    return end_time, DEFAULT_BUFFER_MINUTES


def check_and_lock_conflicts(
    db: Session,
    hairdresser_id: uuid.UUID,
    start_time: datetime,
    end_time: datetime,
    *,
    exclude_appointment_id: uuid.UUID | None = None,
) -> None:
    """Transaction courte, verrouillage en ligne (ARCHITECTURE.md) : verrouille
    les rendez-vous existants potentiellement en conflit AVANT l'insertion du
    nouveau, pour qu'une requête concurrente sur le même créneau ne puisse pas
    passer entre les deux. Ne commit jamais — le verrou tient jusqu'au commit
    du router appelant."""
    db.execute(text("SET LOCAL statement_timeout = '5s'"))

    stmt = (
        select(Appointment.id)
        .where(
            Appointment.hairdresser_id == hairdresser_id,
            Appointment.status.in_(BLOCKING_STATUSES),
            Appointment.start_time < end_time,
            Appointment.end_time > start_time,
        )
        .with_for_update()
    )
    if exclude_appointment_id is not None:
        stmt = stmt.where(Appointment.id != exclude_appointment_id)

    if db.execute(stmt).first() is not None:
        raise BookingConflictError("Ce créneau n'est plus disponible pour cette coiffeuse")


def create_catalogue_appointment(
    db: Session,
    *,
    client_id: uuid.UUID,
    hairdresser: Hairdresser,
    service: Service,
    start_time: datetime,
) -> Appointment:
    end_time, buffer_minutes = compute_catalogue_window(service, hairdresser, start_time)
    check_and_lock_conflicts(db, hairdresser.id, start_time, end_time)

    appointment = Appointment(
        client_id=client_id,
        hairdresser_id=hairdresser.id,
        service_id=service.id,
        start_time=start_time,
        end_time=end_time,
        buffer_minutes=buffer_minutes,
        status=AppointmentStatus.CONFIRMED,
        price=service.prix,
    )
    db.add(appointment)
    db.flush()
    return appointment


def create_devis_appointment(
    db: Session,
    *,
    client_id: uuid.UUID,
    hairdresser_id: uuid.UUID,
    start_time: datetime,
    description: str | None,
) -> Appointment:
    end_time, buffer_minutes = compute_devis_window(start_time)
    check_and_lock_conflicts(db, hairdresser_id, start_time, end_time)

    appointment = Appointment(
        client_id=client_id,
        hairdresser_id=hairdresser_id,
        service_id=None,
        start_time=start_time,
        end_time=end_time,
        buffer_minutes=buffer_minutes,
        status=AppointmentStatus.PENDING_QUOTE,
        price=None,
        description=description,
    )
    db.add(appointment)
    db.flush()
    return appointment


def compute_and_store_suggestion(db: Session, appointment: Appointment) -> None:
    """Pour chaque photo attachée à la demande, cherche des services du
    catalogue visuellement proches (pHash) et retient le meilleur match
    global (pas une moyenne entre plusieurs services différents — une moyenne
    ne correspond à aucune prestation réelle et n'est pas traçable). Purement
    informatif pour le staff, jamais contraignant."""
    best_item = None
    best_distance = None

    for media_item in appointment.media:
        if not media_item.phash:
            continue
        for candidate, distance in find_similar_media(
            db, media_item.phash, limit=5, max_distance=SUGGESTION_MAX_DISTANCE
        ):
            if candidate.service_id is None:
                continue
            if best_distance is None or distance < best_distance:
                best_item, best_distance = candidate, distance

    if best_item is None:
        return

    service = db.get(Service, best_item.service_id)
    if service is None:
        return

    appointment.suggested_service_id = service.id
    appointment.suggested_price = service.prix
    appointment.suggested_duration_minutes = service.duree_minutes
