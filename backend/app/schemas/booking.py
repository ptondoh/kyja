import uuid
from datetime import datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AppointmentStatus
from app.schemas.catalogue import MediaItemOut


class BookingCreateCatalogue(BaseModel):
    hairdresser_id: uuid.UUID
    service_id: uuid.UUID
    start_time: datetime

    @field_validator("start_time")
    @classmethod
    def start_time_must_be_future(cls, v: datetime) -> datetime:
        reference = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if reference <= datetime.now(timezone.utc):
            raise ValueError("start_time doit être dans le futur")
        return v


class ConfirmQuoteRequest(BaseModel):
    price: Decimal = Field(gt=0, decimal_places=2)
    duration_minutes: int | None = Field(default=None, gt=0)


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    hairdresser_id: uuid.UUID
    service_id: uuid.UUID | None
    start_time: datetime
    end_time: datetime
    buffer_minutes: int
    status: AppointmentStatus
    price: Decimal | None
    description: str | None
    suggested_service_id: uuid.UUID | None
    suggested_price: Decimal | None
    suggested_duration_minutes: int | None
    media: list[MediaItemOut] = []
    created_at: datetime
    updated_at: datetime


class ClientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    prenom: str


class HairdresserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    prenom: str


class ServiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str


class BookingAdminOut(BookingOut):
    client: ClientSummary
    hairdresser: HairdresserSummary
    service: ServiceSummary | None
