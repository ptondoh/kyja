import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import MediaKind


class MediaItemCreate(BaseModel):
    kind: MediaKind
    url: str = Field(min_length=1, max_length=500)
    thumbnail_url: str | None = Field(default=None, max_length=500)
    duration_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def check_video_fields(self) -> "MediaItemCreate":
        if self.kind == MediaKind.VIDEO:
            if not self.thumbnail_url or self.duration_seconds is None:
                raise ValueError("thumbnail_url et duration_seconds sont requis pour une vidéo")
        else:
            if self.thumbnail_url is not None or self.duration_seconds is not None:
                raise ValueError("thumbnail_url/duration_seconds ne s'appliquent qu'aux vidéos")
        return self


class MediaItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: MediaKind
    url: str
    thumbnail_url: str | None
    duration_seconds: int | None
    position: int
    created_at: datetime


class MediaReorderRequest(BaseModel):
    media_ids: list[uuid.UUID] = Field(min_length=1)


class ServiceCreate(BaseModel):
    nom: str = Field(min_length=1, max_length=150)
    description: str | None = None
    prix: Decimal = Field(gt=0, decimal_places=2)
    duree_minutes: int = Field(gt=0)
    categorie: str | None = Field(default=None, max_length=100)
    is_active: bool = True


class ServiceUpdate(BaseModel):
    nom: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    prix: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    duree_minutes: int | None = Field(default=None, gt=0)
    categorie: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    description: str | None
    prix: Decimal
    duree_minutes: int
    categorie: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    media: list[MediaItemOut] = []


class ProductCreate(BaseModel):
    nom: str = Field(min_length=1, max_length=150)
    description: str | None = None
    prix: Decimal = Field(gt=0, decimal_places=2)
    is_active: bool = True


class ProductUpdate(BaseModel):
    nom: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    prix: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    is_active: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    description: str | None
    prix: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime
    media: list[MediaItemOut] = []
