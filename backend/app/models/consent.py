import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Uuid

from app.database import Base
from app.models.enums import ConsentType


class ConsentRecord(Base):
    """Registre de consentement PIPEDA / Loi 25.

    INVARIANT : les lignes de cette table ne sont jamais supprimées ni
    modifiées après création (preuve légale de consentement). Non imposé
    par un trigger DB — seulement par discipline applicative — mais
    client_id est en ON DELETE RESTRICT, ce qui empêche la suppression
    physique d'une cliente ayant des consentements et force le flux
    d'anonymisation (clients.anonymized_at) plutôt qu'une suppression.
    """

    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    consent_type: Mapped[ConsentType] = mapped_column(
        Enum(ConsentType, name="consent_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    client: Mapped["Client"] = relationship(back_populates="consent_records")
