import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Uuid

from app.database import Base
from app.models.enums import AppointmentStatus

appointment_resources = Table(
    "appointment_resources",
    Base.metadata,
    Column("appointment_id", Uuid(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), primary_key=True),
    Column("resource_id", Uuid(as_uuid=True), ForeignKey("resources.id", ondelete="RESTRICT"), primary_key=True),
)


class Appointment(Base):
    """Rendez-vous — deux chemins de création :
    catalogue (service_id + price connus dès la création, snapshot de service.prix)
    ou sur devis (service_id/price NULL jusqu'à confirmation admin, description
    et/ou photos, status=PENDING_QUOTE, suggested_* purement informatifs issus
    du matching pHash, jamais contraignants).
    """

    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_hairdresser_window", "hairdresser_id", "start_time", "end_time"),
        CheckConstraint(
            "status NOT IN ('confirmed', 'completed') OR price IS NOT NULL",
            name="confirmed_has_price",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    hairdresser_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hairdressers.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="RESTRICT"), nullable=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, name="appointment_status", values_callable=lambda e: [m.value for m in e]),
        default=AppointmentStatus.CONFIRMED,
        nullable=False,
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    suggested_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_service_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("services.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    client: Mapped["Client"] = relationship(back_populates="appointments")
    hairdresser: Mapped["Hairdresser"] = relationship(back_populates="appointments")
    service: Mapped["Service"] = relationship(back_populates="appointments", foreign_keys=[service_id])
    resources: Mapped[list["Resource"]] = relationship(
        secondary=appointment_resources, back_populates="appointments"
    )
    media: Mapped[list["MediaItem"]] = relationship(
        back_populates="appointment", order_by="MediaItem.position", cascade="all, delete-orphan"
    )
