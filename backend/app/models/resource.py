import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Uuid

from app.database import Base


class Resource(Base):
    """Équipement partagé (bac de lavage, casque, etc.).

    `type` reste du texte libre indexé plutôt qu'un enum Postgres : c'est la
    liste la plus susceptible de grandir sans déploiement de code, et
    modifier un enum Postgres après coup est pénible (ALTER TYPE).
    """

    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    appointments: Mapped[list["Appointment"]] = relationship(
        secondary="appointment_resources", back_populates="resources"
    )
