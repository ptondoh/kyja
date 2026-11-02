import uuid
from typing import Literal

import structlog
from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.image_processing import InvalidImageError, compute_phash, validate_and_process_image
from app.core.storage import get_storage
from app.models.enums import MediaKind
from app.models.media import MediaItem
from app.schemas.catalogue import MediaItemCreate

OwnerField = Literal["service_id", "product_id", "appointment_id"]

logger = structlog.get_logger()


def _owner_filter(owner_field: OwnerField, owner_id: uuid.UUID):
    return getattr(MediaItem, owner_field) == owner_id


def get_owner_media(db: Session, owner_field: OwnerField, owner_id: uuid.UUID) -> list[MediaItem]:
    stmt = select(MediaItem).where(_owner_filter(owner_field, owner_id)).order_by(MediaItem.position)
    return list(db.execute(stmt).scalars().all())


def attach_media(db: Session, owner_field: OwnerField, owner_id: uuid.UUID, payload: MediaItemCreate) -> MediaItem:
    max_position = db.execute(
        select(func.max(MediaItem.position)).where(_owner_filter(owner_field, owner_id))
    ).scalar()
    next_position = 0 if max_position is None else max_position + 1

    item = MediaItem(
        **payload.model_dump(),
        position=next_position,
        **{owner_field: owner_id},
    )
    db.add(item)
    db.flush()
    return item


def get_owned_media_or_404(db: Session, owner_field: OwnerField, owner_id: uuid.UUID, media_id: uuid.UUID) -> MediaItem:
    stmt = select(MediaItem).where(MediaItem.id == media_id, _owner_filter(owner_field, owner_id))
    item = db.execute(stmt).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Média introuvable")
    return item


def detach_media(db: Session, owner_field: OwnerField, owner_id: uuid.UUID, media_id: uuid.UUID) -> None:
    """Supprime la ligne DB et le fichier de stockage associé (best-effort pour
    le fichier : un échec de suppression du fichier ne fait pas échouer la requête)."""
    item = get_owned_media_or_404(db, owner_field, owner_id, media_id)
    url = item.url
    db.delete(item)
    db.flush()

    storage = get_storage()
    key = storage.key_from_url(url)
    if key:
        try:
            storage.delete(key)
        except OSError:
            logger.warning("media_file_delete_failed", url=url)


async def handle_media_upload(
    db: Session,
    owner_field: OwnerField,
    owner_id: uuid.UUID,
    *,
    kind: MediaKind,
    file: UploadFile | None,
    url: str | None,
    thumbnail_url: str | None,
    duration_seconds: int | None,
) -> MediaItem:
    """Orchestration partagée entre /services/{id}/media et /products/{id}/media :
    image -> upload de fichier (validation, traitement, pHash, stockage) ;
    vidéo -> toujours par URL (pas de pipeline ffmpeg pour l'instant)."""
    if kind == MediaKind.IMAGE:
        if file is None:
            raise HTTPException(status_code=422, detail="file est requis pour une image")
        if url is not None or thumbnail_url is not None or duration_seconds is not None:
            raise HTTPException(
                status_code=422, detail="url/thumbnail_url/duration_seconds ne s'appliquent pas aux images"
            )

        raw = await file.read()
        try:
            processed = validate_and_process_image(raw)
        except InvalidImageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        phash = compute_phash(processed)
        folder = owner_field.removesuffix("_id") + "s"
        key = f"{folder}/{owner_id}/{uuid.uuid4()}.webp"
        stored_url = get_storage().save(processed, key, "image/webp")

        payload = MediaItemCreate(kind=MediaKind.IMAGE, url=stored_url)
        item = attach_media(db, owner_field, owner_id, payload)
        item.phash = phash
        return item

    if file is not None:
        raise HTTPException(status_code=422, detail="file ne s'applique pas aux vidéos pour l'instant")

    try:
        payload = MediaItemCreate(
            kind=MediaKind.VIDEO, url=url, thumbnail_url=thumbnail_url, duration_seconds=duration_seconds
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return attach_media(db, owner_field, owner_id, payload)


def reorder_media(
    db: Session, owner_field: OwnerField, owner_id: uuid.UUID, media_ids: list[uuid.UUID]
) -> list[MediaItem]:
    if len(media_ids) != len(set(media_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="media_ids contient des doublons",
        )

    existing = get_owner_media(db, owner_field, owner_id)
    existing_by_id = {item.id: item for item in existing}

    if set(media_ids) != set(existing_by_id.keys()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="L'ensemble des media_ids ne correspond pas exactement aux médias existants pour cet élément",
        )

    for index, media_id in enumerate(media_ids):
        existing_by_id[media_id].position = index

    db.flush()
    return sorted(existing_by_id.values(), key=lambda item: item.position)
