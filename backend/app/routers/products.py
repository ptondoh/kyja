import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import require_role
from app.core.media import detach_media, handle_media_upload, reorder_media
from app.database import get_db
from app.models import Product, User
from app.models.enums import MediaKind, UserRole
from app.schemas.catalogue import (
    MediaItemOut,
    MediaReorderRequest,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)

router = APIRouter()
logger = structlog.get_logger()

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def _get_product_or_404(db: Session, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id, options=[selectinload(Product.media)])
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produit introuvable")
    return product


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ProductOut:
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    logger.info("product_created", product_id=str(product.id), admin_id=str(admin.id))
    return ProductOut.model_validate(product)


@router.get("", response_model=list[ProductOut])
def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
) -> list[ProductOut]:
    stmt = (
        select(Product)
        .where(Product.is_active.is_(True))
        .options(selectinload(Product.media))
        .order_by(Product.nom)
        .offset(skip)
        .limit(limit)
    )
    products = db.execute(stmt).scalars().all()
    return [ProductOut.model_validate(p) for p in products]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)) -> ProductOut:
    product = _get_product_or_404(db, product_id)
    return ProductOut.model_validate(product)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ProductOut:
    product = _get_product_or_404(db, product_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, key, value)
    db.commit()
    logger.info("product_updated", product_id=str(product_id), admin_id=str(admin.id))
    return ProductOut.model_validate(product)


@router.patch("/{product_id}/deactivate", response_model=ProductOut)
def deactivate_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> ProductOut:
    product = _get_product_or_404(db, product_id)
    product.is_active = False
    db.commit()
    logger.info("product_deactivated", product_id=str(product_id), admin_id=str(admin.id))
    return ProductOut.model_validate(product)


@router.post("/{product_id}/media", response_model=MediaItemOut, status_code=status.HTTP_201_CREATED)
async def add_product_media(
    product_id: uuid.UUID,
    kind: MediaKind = Form(...),
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    thumbnail_url: str | None = Form(default=None),
    duration_seconds: int | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> MediaItemOut:
    _get_product_or_404(db, product_id)
    item = await handle_media_upload(
        db,
        "product_id",
        product_id,
        kind=kind,
        file=file,
        url=url,
        thumbnail_url=thumbnail_url,
        duration_seconds=duration_seconds,
    )
    db.commit()
    logger.info("product_media_attached", product_id=str(product_id), media_id=str(item.id), admin_id=str(admin.id))
    return MediaItemOut.model_validate(item)


@router.delete("/{product_id}/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_product_media(
    product_id: uuid.UUID,
    media_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> None:
    _get_product_or_404(db, product_id)
    detach_media(db, "product_id", product_id, media_id)
    db.commit()
    logger.info("product_media_detached", product_id=str(product_id), media_id=str(media_id), admin_id=str(admin.id))


@router.put("/{product_id}/media/reorder", response_model=list[MediaItemOut])
def reorder_product_media(
    product_id: uuid.UUID,
    payload: MediaReorderRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN)),
) -> list[MediaItemOut]:
    _get_product_or_404(db, product_id)
    items = reorder_media(db, "product_id", product_id, payload.media_ids)
    db.commit()
    logger.info("product_media_reordered", product_id=str(product_id), admin_id=str(admin.id))
    return [MediaItemOut.model_validate(i) for i in items]
