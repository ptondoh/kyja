import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.booking_engine import (
    DEFAULT_BUFFER_MINUTES,
    BookingConflictError,
    check_and_lock_conflicts,
    compute_and_store_suggestion,
    create_catalogue_appointment,
    create_devis_appointment,
)
from app.core.deps import get_current_client, get_current_user, require_role
from app.core.media import handle_media_upload
from app.database import get_db
from app.models import Appointment, Client, Hairdresser, Service, User
from app.models.enums import AppointmentStatus, MediaKind, UserRole
from app.schemas.booking import BookingAdminOut, BookingCreateCatalogue, BookingOut, ConfirmQuoteRequest

router = APIRouter()
logger = structlog.get_logger()

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

_LOAD_OPTIONS = (
    selectinload(Appointment.client),
    selectinload(Appointment.hairdresser),
    selectinload(Appointment.service),
    selectinload(Appointment.media),
)


def _get_booking_or_404(db: Session, booking_id: uuid.UUID) -> Appointment:
    booking = db.get(Appointment, booking_id, options=list(_LOAD_OPTIONS))
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rendez-vous introuvable")
    return booking


def _get_authorized_booking_or_404(db: Session, booking_id: uuid.UUID, current_user: User) -> Appointment:
    """Jamais de 403 ici : une cliente qui tente l'id d'un rendez-vous qui n'est
    pas le sien reçoit la même 404 qu'un id inexistant — pas de fuite
    d'existence, même pattern que get_owned_media_or_404."""
    booking = _get_booking_or_404(db, booking_id)
    is_owner_client = booking.client.user_id == current_user.id
    is_assigned_hairdresser = booking.hairdresser.user_id == current_user.id
    is_admin = current_user.role == UserRole.ADMIN
    if not (is_owner_client or is_assigned_hairdresser or is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rendez-vous introuvable")
    return booking


@router.post("/catalogue", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def book_catalogue(
    payload: BookingCreateCatalogue,
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> BookingOut:
    hairdresser = db.get(Hairdresser, payload.hairdresser_id)
    if hairdresser is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coiffeuse introuvable")

    service = db.get(Service, payload.service_id)
    if service is None or not service.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service introuvable")

    try:
        appointment = create_catalogue_appointment(
            db, client_id=client.id, hairdresser=hairdresser, service=service, start_time=payload.start_time
        )
    except BookingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    logger.info("booking_catalogue_created", booking_id=str(appointment.id), client_id=str(client.id))
    return BookingOut.model_validate(_get_booking_or_404(db, appointment.id))


@router.post("/devis", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
async def book_devis(
    hairdresser_id: uuid.UUID = Form(...),
    start_time: datetime = Form(...),
    description: str | None = Form(default=None),
    photos: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> BookingOut:
    if not description and not photos:
        raise HTTPException(status_code=422, detail="description ou au moins une photo requis")

    reference = start_time if start_time.tzinfo else start_time.replace(tzinfo=timezone.utc)
    if reference <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="start_time doit être dans le futur")

    hairdresser = db.get(Hairdresser, hairdresser_id)
    if hairdresser is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coiffeuse introuvable")

    try:
        appointment = create_devis_appointment(
            db, client_id=client.id, hairdresser_id=hairdresser_id, start_time=start_time, description=description
        )
    except BookingConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    for photo in photos:
        await handle_media_upload(
            db,
            "appointment_id",
            appointment.id,
            kind=MediaKind.IMAGE,
            file=photo,
            url=None,
            thumbnail_url=None,
            duration_seconds=None,
        )

    compute_and_store_suggestion(db, appointment)
    db.commit()
    logger.info("booking_devis_created", booking_id=str(appointment.id), client_id=str(client.id))
    return BookingOut.model_validate(_get_booking_or_404(db, appointment.id))


@router.get("", response_model=list[BookingAdminOut])
def list_all_bookings(
    status_filter: AppointmentStatus | None = Query(default=None, alias="status"),
    hairdresser_id: uuid.UUID | None = Query(default=None),
    start_after: datetime | None = Query(default=None),
    start_before: datetime | None = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> list[BookingAdminOut]:
    stmt = select(Appointment).options(*_LOAD_OPTIONS).order_by(Appointment.start_time)
    if status_filter is not None:
        stmt = stmt.where(Appointment.status == status_filter)
    if hairdresser_id is not None:
        stmt = stmt.where(Appointment.hairdresser_id == hairdresser_id)
    if start_after is not None:
        stmt = stmt.where(Appointment.start_time >= start_after)
    if start_before is not None:
        stmt = stmt.where(Appointment.start_time <= start_before)
    stmt = stmt.offset(skip).limit(limit)

    bookings = db.execute(stmt).scalars().all()
    return [BookingAdminOut.model_validate(b) for b in bookings]


@router.get("/mine", response_model=list[BookingOut])
def list_my_bookings(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
    client: Client = Depends(get_current_client),
) -> list[BookingOut]:
    stmt = (
        select(Appointment)
        .where(Appointment.client_id == client.id)
        .options(*_LOAD_OPTIONS)
        .order_by(Appointment.start_time)
        .offset(skip)
        .limit(limit)
    )
    bookings = db.execute(stmt).scalars().all()
    return [BookingOut.model_validate(b) for b in bookings]


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingOut:
    booking = _get_authorized_booking_or_404(db, booking_id, current_user)
    return BookingOut.model_validate(booking)


@router.patch("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BookingOut:
    booking = _get_authorized_booking_or_404(db, booking_id, current_user)
    if booking.status not in (AppointmentStatus.CONFIRMED, AppointmentStatus.PENDING_QUOTE):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce rendez-vous ne peut plus être annulé")

    booking.status = AppointmentStatus.CANCELLED
    db.commit()
    logger.info("booking_cancelled", booking_id=str(booking_id), user_id=str(current_user.id))
    return BookingOut.model_validate(booking)


@router.patch("/{booking_id}/confirm-quote", response_model=BookingOut)
def confirm_quote(
    booking_id: uuid.UUID,
    payload: ConfirmQuoteRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> BookingOut:
    booking = _get_booking_or_404(db, booking_id)
    if booking.status != AppointmentStatus.PENDING_QUOTE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ce rendez-vous n'est pas en attente de devis")

    if payload.duration_minutes is not None:
        new_end_time = booking.start_time + timedelta(minutes=payload.duration_minutes) + timedelta(
            minutes=DEFAULT_BUFFER_MINUTES
        )
        try:
            check_and_lock_conflicts(
                db, booking.hairdresser_id, booking.start_time, new_end_time, exclude_appointment_id=booking.id
            )
        except BookingConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        booking.end_time = new_end_time

    booking.price = payload.price
    booking.status = AppointmentStatus.CONFIRMED
    db.commit()
    logger.info("booking_quote_confirmed", booking_id=str(booking_id), admin_id=str(admin.id))
    return BookingOut.model_validate(booking)
