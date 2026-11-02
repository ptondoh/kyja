import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import require_role
from app.core.media import detach_media, handle_media_upload, reorder_media
from app.database import get_db
from app.models import Service, User
from app.models.enums import MediaKind, UserRole
from app.schemas.catalogue import (
    MediaItemOut,
    MediaReorderRequest,
    ServiceCreate,
    ServiceOut,
    ServiceUpdate,
)

router = APIRouter()
logger = structlog.get_logger()

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _get_service_or_404(db: Session, service_id: uuid.UUID) -> Service:
    service = db.get(Service, service_id, options=[selectinload(Service.media)])
    if service is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service introuvable")
    return service


@router.post("", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ServiceOut:
    service = Service(**payload.model_dump())
    db.add(service)
    db.commit()
    logger.info("service_created", service_id=str(service.id), admin_id=str(admin.id))
    return ServiceOut.model_validate(service)


@router.get("", response_model=list[ServiceOut])
def list_services(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> list[ServiceOut]:
    stmt = (
        select(Service)
        .where(Service.is_active.is_(True))
        .options(selectinload(Service.media))
        .order_by(Service.nom)
        .offset(skip)
        .limit(limit)
    )
    services = db.execute(stmt).scalars().all()
    return [ServiceOut.model_validate(s) for s in services]


@router.get("/{service_id}", response_model=ServiceOut)
def get_service(service_id: uuid.UUID, db: Session = Depends(get_db)) -> ServiceOut:
    service = _get_service_or_404(db, service_id)
    return ServiceOut.model_validate(service)


@router.put("/{service_id}", response_model=ServiceOut)
def update_service(
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ServiceOut:
    service = _get_service_or_404(db, service_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(service, key, value)
    db.commit()
    logger.info("service_updated", service_id=str(service_id), admin_id=str(admin.id))
    return ServiceOut.model_validate(service)


@router.patch("/{service_id}/deactivate", response_model=ServiceOut)
def deactivate_service(
    service_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ServiceOut:
    service = _get_service_or_404(db, service_id)
    service.is_active = False
    db.commit()
    logger.info("service_deactivated", service_id=str(service_id), admin_id=str(admin.id))
    return ServiceOut.model_validate(service)


@router.post("/{service_id}/media", response_model=MediaItemOut, status_code=status.HTTP_201_CREATED)
async def add_service_media(
    service_id: uuid.UUID,
    kind: MediaKind = Form(...),
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    thumbnail_url: str | None = Form(default=None),
    duration_seconds: int | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> MediaItemOut:
    _get_service_or_404(db, service_id)
    item = await handle_media_upload(
        db,
        "service_id",
        service_id,
        kind=kind,
        file=file,
        url=url,
        thumbnail_url=thumbnail_url,
        duration_seconds=duration_seconds,
    )
    db.commit()
    logger.info("service_media_attached", service_id=str(service_id), media_id=str(item.id), admin_id=str(admin.id))
    return MediaItemOut.model_validate(item)


@router.delete("/{service_id}/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_service_media(
    service_id: uuid.UUID,
    media_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> None:
    _get_service_or_404(db, service_id)
    detach_media(db, "service_id", service_id, media_id)
    db.commit()
    logger.info("service_media_detached", service_id=str(service_id), media_id=str(media_id), admin_id=str(admin.id))


@router.put("/{service_id}/media/reorder", response_model=list[MediaItemOut])
def reorder_service_media(
    service_id: uuid.UUID,
    payload: MediaReorderRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> list[MediaItemOut]:
    _get_service_or_404(db, service_id)
    items = reorder_media(db, "service_id", service_id, payload.media_ids)
    db.commit()
    logger.info("service_media_reordered", service_id=str(service_id), admin_id=str(admin.id))
    return [MediaItemOut.model_validate(i) for i in items]
