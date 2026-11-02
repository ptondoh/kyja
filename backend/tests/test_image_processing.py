import io

import imagehash
import pytest
from PIL import Image

from app.core.image_processing import (
    MAX_DIMENSION,
    InvalidImageError,
    compute_phash,
    find_similar_media,
    validate_and_process_image,
)
from app.models.enums import MediaKind
from app.models.media import MediaItem
from tests.factories import make_service


def _make_checkerboard_jpeg_bytes(size: tuple[int, int] = (300, 300), square: int = 30) -> bytes:
    """pHash est basé sur la luminance/structure (DCT), pas la couleur pure —
    deux aplats de couleurs différentes peuvent avoir un hash quasi identique.
    Un damier donne une structure nettement différente d'un aplat uni."""
    img = Image.new("RGB", size, color=(255, 255, 255))
    pixels = img.load()
    for x in range(size[0]):
        for y in range(size[1]):
            if (x // square + y // square) % 2 == 0:
                pixels[x, y] = (0, 0, 0)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_jpeg_bytes(size: tuple[int, int], color: tuple[int, int, int], with_exif: bool = False) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    if with_exif:
        exif = Image.Exif()
        exif[271] = "TestCameraMake"  # tag 271 = Make
        img.save(buf, format="JPEG", exif=exif.tobytes())
    else:
        img.save(buf, format="JPEG")
    return buf.getvalue()


def test_validate_and_process_image_rejects_non_image_bytes():
    with pytest.raises(InvalidImageError):
        validate_and_process_image(b"this is not an image, just text")


def test_validate_and_process_image_strips_exif():
    raw = _make_jpeg_bytes((400, 400), (200, 30, 30), with_exif=True)
    processed = validate_and_process_image(raw)
    result_img = Image.open(io.BytesIO(processed))
    assert len(result_img.getexif()) == 0


def test_validate_and_process_image_resizes_oversized_images():
    raw = _make_jpeg_bytes((3000, 2000), (0, 100, 200))
    processed = validate_and_process_image(raw)
    result_img = Image.open(io.BytesIO(processed))
    assert max(result_img.size) <= MAX_DIMENSION


def test_validate_and_process_image_outputs_webp():
    raw = _make_jpeg_bytes((100, 100), (10, 20, 30))
    processed = validate_and_process_image(raw)
    result_img = Image.open(io.BytesIO(processed))
    assert result_img.format == "WEBP"


def test_compute_phash_identical_images_have_distance_zero():
    raw_a = validate_and_process_image(_make_jpeg_bytes((300, 300), (200, 30, 30)))
    raw_b = validate_and_process_image(_make_jpeg_bytes((300, 300), (200, 30, 30)))
    hash_a = imagehash.hex_to_hash(compute_phash(raw_a))
    hash_b = imagehash.hex_to_hash(compute_phash(raw_b))
    assert (hash_a - hash_b) == 0


def test_compute_phash_different_images_have_high_distance():
    raw_solid = validate_and_process_image(_make_jpeg_bytes((300, 300), (200, 20, 20)))
    raw_checker = validate_and_process_image(_make_checkerboard_jpeg_bytes())
    hash_solid = imagehash.hex_to_hash(compute_phash(raw_solid))
    hash_checker = imagehash.hex_to_hash(compute_phash(raw_checker))
    assert (hash_solid - hash_checker) > 10


def test_find_similar_media_returns_close_match_and_excludes_unrelated(db_session):
    service = make_service(db_session)

    processed_red = validate_and_process_image(_make_jpeg_bytes((300, 300), (200, 20, 20)))
    processed_red_variant = validate_and_process_image(_make_jpeg_bytes((290, 290), (200, 20, 20)))
    processed_checker = validate_and_process_image(_make_checkerboard_jpeg_bytes())

    red_item = MediaItem(
        service_id=service.id, kind=MediaKind.IMAGE, url="/media/red.webp", phash=compute_phash(processed_red)
    )
    checker_item = MediaItem(
        service_id=service.id,
        kind=MediaKind.IMAGE,
        url="/media/checker.webp",
        phash=compute_phash(processed_checker),
    )
    db_session.add_all([red_item, checker_item])
    db_session.flush()

    query_hash = compute_phash(processed_red_variant)
    results = find_similar_media(db_session, query_hash, limit=5, max_distance=10)

    result_ids = [item.id for item, _distance in results]
    assert red_item.id in result_ids
    assert checker_item.id not in result_ids
