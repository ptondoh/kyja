import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.deps import require_role
from app.core.security import hash_password
from app.database import get_db
from app.models import Hairdresser, User
from app.models.enums import UserRole
from app.schemas.hairdresser import HairdresserCreate, HairdresserOut, HairdresserUpdate

router = APIRouter()
logger = structlog.get_logger()

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _get_hairdresser_or_404(db: Session, hairdresser_id: uuid.UUID) -> Hairdresser:
    hairdresser = db.get(Hairdresser, hairdresser_id, options=[selectinload(Hairdresser.user)])
    if hairdresser is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coiffeuse introuvable")
    return hairdresser


@router.post("", response_model=HairdresserOut, status_code=status.HTTP_201_CREATED)
def create_hairdresser(
    payload: HairdresserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> HairdresserOut:
    user = User(
        email=payload.email, password_hash=hash_password(payload.password), role=UserRole.HAIRDRESSER, is_active=True
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un compte existe déjà avec cet email")

    hairdresser = Hairdresser(
        user_id=user.id,
        nom=payload.nom,
        prenom=payload.prenom,
        bio=payload.bio,
        experience_level=payload.experience_level,
        is_independent=payload.is_independent,
    )
    hairdresser.user = user
    db.add(hairdresser)
    db.commit()
    logger.info("hairdresser_created", hairdresser_id=str(hairdresser.id), admin_id=str(admin.id))
    return HairdresserOut.model_validate(hairdresser)


@router.get("", response_model=list[HairdresserOut])
def list_hairdressers(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> list[HairdresserOut]:
    stmt = (
        select(Hairdresser)
        .join(User, Hairdresser.user_id == User.id)
        .where(User.is_active.is_(True))
        .options(selectinload(Hairdresser.user))
        .order_by(Hairdresser.nom)
        .offset(skip)
        .limit(limit)
    )
    hairdressers = db.execute(stmt).scalars().all()
    return [HairdresserOut.model_validate(h) for h in hairdressers]


@router.get("/{hairdresser_id}", response_model=HairdresserOut)
def get_hairdresser(hairdresser_id: uuid.UUID, db: Session = Depends(get_db)) -> HairdresserOut:
    hairdresser = _get_hairdresser_or_404(db, hairdresser_id)
    return HairdresserOut.model_validate(hairdresser)


@router.patch("/{hairdresser_id}", response_model=HairdresserOut)
def update_hairdresser(
    hairdresser_id: uuid.UUID,
    payload: HairdresserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> HairdresserOut:
    hairdresser = _get_hairdresser_or_404(db, hairdresser_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(hairdresser, key, value)
    db.commit()
    logger.info("hairdresser_updated", hairdresser_id=str(hairdresser_id), admin_id=str(admin.id))
    return HairdresserOut.model_validate(hairdresser)


@router.patch("/{hairdresser_id}/deactivate", response_model=HairdresserOut)
def deactivate_hairdresser(
    hairdresser_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> HairdresserOut:
    hairdresser = _get_hairdresser_or_404(db, hairdresser_id)
    hairdresser.user.is_active = False
    db.commit()
    logger.info("hairdresser_deactivated", hairdresser_id=str(hairdresser_id), admin_id=str(admin.id))
    return HairdresserOut.model_validate(hairdresser)
