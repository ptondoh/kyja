import io
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from PIL import Image
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import Appointment, Client, Hairdresser, MediaItem, Product, Service, User
from app.models.enums import AppointmentStatus, ExperienceLevel, MediaKind, UserRole


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:8]}@example.com"


def make_user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "CorrectHorse123!",
    role: UserRole = UserRole.CLIENT,
    is_active: bool = True,
) -> User:
    user = User(
        email=email or _unique_email(),
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def make_client_user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "CorrectHorse123!",
    nom: str = "Tremblay",
    prenom: str = "Zoé",
    telephone: str = "514-555-0100",
    adresse: str = "123 rue Test, Montréal",
) -> tuple[User, Client]:
    user = make_user(db, email=email, password=password, role=UserRole.CLIENT)
    client_profile = Client(user_id=user.id, nom=nom, prenom=prenom, telephone=telephone, adresse=adresse)
    db.add(client_profile)
    db.flush()
    return user, client_profile


def make_admin_user(db: Session, *, email: str | None = None, password: str = "CorrectHorse123!") -> User:
    return make_user(db, email=email, password=password, role=UserRole.ADMIN)


def make_hairdresser_user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "CorrectHorse123!",
    nom: str = "Gagnon",
    prenom: str = "Alex",
    experience_level: ExperienceLevel = ExperienceLevel.SENIOR,
) -> tuple[User, Hairdresser]:
    user = make_user(db, email=email, password=password, role=UserRole.HAIRDRESSER)
    hairdresser = Hairdresser(user_id=user.id, nom=nom, prenom=prenom, experience_level=experience_level)
    db.add(hairdresser)
    db.flush()
    return user, hairdresser


def make_service(
    db: Session,
    *,
    nom: str = "Coupe",
    description: str | None = None,
    prix: Decimal = Decimal("45.00"),
    duree_minutes: int = 30,
    categorie: str | None = None,
    is_active: bool = True,
) -> Service:
    service = Service(
        nom=nom,
        description=description,
        prix=prix,
        duree_minutes=duree_minutes,
        categorie=categorie,
        is_active=is_active,
    )
    db.add(service)
    db.flush()
    return service


def make_product(
    db: Session,
    *,
    nom: str = "Shampoing",
    description: str | None = None,
    prix: Decimal = Decimal("20.00"),
    is_active: bool = True,
) -> Product:
    product = Product(nom=nom, description=description, prix=prix, is_active=is_active)
    db.add(product)
    db.flush()
    return product


def make_media_item(
    db: Session,
    *,
    service_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
    appointment_id: uuid.UUID | None = None,
    url: str = "https://example.com/img.jpg",
    phash: str | None = None,
    position: int | None = None,
) -> MediaItem:
    owner_id = service_id or product_id or appointment_id
    owner_col = MediaItem.service_id if service_id else (MediaItem.product_id if product_id else MediaItem.appointment_id)
    if position is None:
        existing = [m.position for m in db.query(MediaItem).filter(owner_col == owner_id)]
        position = (max(existing) + 1) if existing else 0
    item = MediaItem(
        service_id=service_id,
        product_id=product_id,
        appointment_id=appointment_id,
        kind=MediaKind.IMAGE,
        url=url,
        phash=phash,
        position=position,
    )
    db.add(item)
    db.flush()
    return item


def make_appointment(
    db: Session,
    *,
    client_id: uuid.UUID,
    hairdresser_id: uuid.UUID,
    service_id: uuid.UUID | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    buffer_minutes: int = 15,
    status: AppointmentStatus = AppointmentStatus.CONFIRMED,
    price: Decimal | None = None,
    description: str | None = None,
) -> Appointment:
    start_time = start_time or (datetime.now(timezone.utc) + timedelta(days=1))
    end_time = end_time or (start_time + timedelta(minutes=45))
    if price is None and status in (AppointmentStatus.CONFIRMED, AppointmentStatus.COMPLETED):
        price = Decimal("45.00")  # CHECK confirmed_has_price l'exige
    appointment = Appointment(
        client_id=client_id,
        hairdresser_id=hairdresser_id,
        service_id=service_id,
        start_time=start_time,
        end_time=end_time,
        buffer_minutes=buffer_minutes,
        status=status,
        price=price,
        description=description,
    )
    db.add(appointment)
    db.flush()
    return appointment


def make_jpeg_bytes(size: tuple[int, int] = (200, 200), color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="JPEG")
    return buf.getvalue()


def auth_headers_for(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}
