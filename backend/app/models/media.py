import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Uuid

from app.database import Base
from app.models.enums import MediaKind


class MediaItem(Base):
    """Galerie images/vidéos — table polymorphe partagée par services, products
    et appointments (photos de demande "sur devis").

    Un seul des trois FK (service_id / product_id / appointment_id) est
    renseigné par ligne (CHECK exactly_one_owner, via num_nonnulls()).
    thumbnail_url/duration_seconds ne sont renseignés que pour kind=video
    (CHECK video_has_thumbnail).
    """

    __tablename__ = "media_items"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(service_id, product_id, appointment_id) = 1",
            name="exactly_one_owner",
        ),
        CheckConstraint(
            "kind <> 'video' OR (thumbnail_url IS NOT NULL AND duration_seconds IS NOT NULL)",
            name="video_has_thumbnail",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE"), nullable=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[MediaKind] = mapped_column(
        Enum(MediaKind, name="media_kind", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    phash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    service: Mapped["Service"] = relationship(back_populates="media")
    product: Mapped["Product"] = relationship(back_populates="media")
    appointment: Mapped["Appointment"] = relationship(back_populates="media")
