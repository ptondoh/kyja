import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import ExperienceLevel


class HairdresserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    nom: str = Field(min_length=1, max_length=100)
    prenom: str = Field(min_length=1, max_length=100)
    bio: str | None = None
    experience_level: ExperienceLevel
    is_independent: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class HairdresserUpdate(BaseModel):
    nom: str | None = Field(default=None, min_length=1, max_length=100)
    prenom: str | None = Field(default=None, min_length=1, max_length=100)
    bio: str | None = None
    experience_level: ExperienceLevel | None = None
    is_independent: bool | None = None


class HairdresserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nom: str
    prenom: str
    bio: str | None
    experience_level: ExperienceLevel
    is_independent: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
