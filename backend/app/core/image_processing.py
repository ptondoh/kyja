import io

import imagehash
import pillow_heif
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.media import MediaItem

pillow_heif.register_heif_opener()

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_DIMENSION = 1600
WEBP_QUALITY = 85


class InvalidImageError(ValueError):
    pass


def validate_and_process_image(raw_bytes: bytes) -> bytes:
    """Valide que `raw_bytes` est une vraie image, puis la normalise :
    EXIF strippé (confidentialité — peut contenir des coordonnées GPS),
    orientation respectée, redimensionnée, réencodée en WebP."""
    if len(raw_bytes) > MAX_IMAGE_BYTES:
        raise InvalidImageError("Image trop volumineuse (10 Mo max)")

    try:
        Image.open(io.BytesIO(raw_bytes)).verify()
    except Exception as exc:
        raise InvalidImageError("Fichier image invalide ou corrompu") from exc

    # verify() invalide l'objet pour tout usage ultérieur — on rouvre.
    image = Image.open(io.BytesIO(raw_bytes))
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION))

    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=WEBP_QUALITY)
    return buffer.getvalue()


def compute_phash(processed_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(processed_bytes))
    return str(imagehash.phash(image))


def find_similar_media(
    db: Session, query_phash: str, limit: int = 5, max_distance: int = 10
) -> list[tuple[MediaItem, int]]:
    query_hash = imagehash.hex_to_hash(query_phash)
    candidates = db.execute(select(MediaItem).where(MediaItem.phash.is_not(None))).scalars().all()

    scored = []
    for item in candidates:
        distance = query_hash - imagehash.hex_to_hash(item.phash)
        if distance <= max_distance:
            scored.append((item, distance))

    scored.sort(key=lambda pair: pair[1])
    return scored[:limit]
