"""Image metadata, checksum and perceptual hash (TASK-012)."""

import hashlib

import pytest
from PIL import UnidentifiedImageError

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.infrastructure.parsers.images import (
    ImageParser,
    fingerprint_image,
    hamming_distance,
)
from tests.unit.parser_fixtures import make_png


def test_fingerprint_is_deterministic() -> None:
    data = make_png()
    first = fingerprint_image(data)
    second = fingerprint_image(data)
    assert first == second
    assert first.checksum_sha256 == hashlib.sha256(data).hexdigest()
    assert len(first.perceptual_hash) == 16


def test_fingerprint_captures_dimensions_and_format() -> None:
    fingerprint = fingerprint_image(make_png(size=(64, 48)))
    assert (fingerprint.width, fingerprint.height) == (64, 48)
    assert fingerprint.format == "PNG"


def test_different_images_have_distant_hashes() -> None:
    import io

    from PIL import Image

    def gradient(direction: int) -> bytes:
        image = Image.new("L", (64, 64))
        image.putdata([direction * (x % 64) * 4 % 256 for x in range(64 * 64)])
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    a = fingerprint_image(gradient(1))
    b = fingerprint_image(gradient(-1))
    assert hamming_distance(a.perceptual_hash, b.perceptual_hash) > 8


def test_reencoded_image_keeps_same_perceptual_hash() -> None:
    import io

    from PIL import Image

    original = make_png()
    with Image.open(io.BytesIO(original)) as image:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=70)
    reencoded = buffer.getvalue()

    a = fingerprint_image(original)
    b = fingerprint_image(reencoded)
    assert a.checksum_sha256 != b.checksum_sha256  # exact dedup misses it
    assert hamming_distance(a.perceptual_hash, b.perceptual_hash) <= 4  # perceptual finds it


async def test_image_parser_produces_single_fingerprinted_part() -> None:
    parser = ImageParser()
    assert parser.supports("image/png", "diagram.png")
    assert parser.supports("", "photo.JPG")
    assert not parser.supports("application/pdf", "doc.pdf")

    data = make_png()
    document = await parser.parse(
        FetchedArtifact(
            external_id="img-1",
            source_uri="file:///diagram.png",
            filename="diagram.png",
            content=data,
            mime_type="image/png",
        )
    )
    (part,) = document.parts
    assert part.part_type == "image"
    assert part.binary_content == data
    assert part.checksum_sha256 == hashlib.sha256(data).hexdigest()
    assert part.metadata["width"] == 64


def test_hamming_distance_of_identical_hashes_is_zero() -> None:
    assert hamming_distance("ff00ff00ff00ff00", "ff00ff00ff00ff00") == 0
    assert hamming_distance("0", "f") == 4


@pytest.mark.parametrize("bad", [b"", b"not an image"])
def test_fingerprint_rejects_invalid_image_bytes(bad: bytes) -> None:
    with pytest.raises(UnidentifiedImageError):
        fingerprint_image(bad)
