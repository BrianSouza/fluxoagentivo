"""Image metadata, checksum and perceptual hash (TASK-012).

The perceptual hash is a 64-bit difference hash (dHash) computed with
Pillow only: the image is grayscaled, resized to 9x8 and each bit encodes
whether a pixel is brighter than its right neighbor. Near-identical images
(recompression, mild resizing) produce hashes within a small Hamming
distance, which the dedup epic uses (docs/spec/06_DEDUP_TRIAGE.md).
"""

import hashlib
import io
from dataclasses import dataclass
from typing import Any, cast

from PIL import Image

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.artifacts.parsing import ParsedDocument, ParsedPart, PartType

_DHASH_WIDTH = 9
_DHASH_HEIGHT = 8

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff")


@dataclass(slots=True)
class ImageFingerprint:
    checksum_sha256: str
    perceptual_hash: str
    width: int
    height: int
    format: str | None
    mode: str

    def as_metadata(self) -> dict[str, Any]:
        return {
            "perceptual_hash": self.perceptual_hash,
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "mode": self.mode,
        }


def perceptual_hash(image: Image.Image) -> str:
    grayscale = image.convert("L").resize(
        (_DHASH_WIDTH, _DHASH_HEIGHT), Image.Resampling.LANCZOS
    )
    pixels = cast(list[int], list(grayscale.get_flattened_data()))
    bits = 0
    for row in range(_DHASH_HEIGHT):
        for col in range(_DHASH_WIDTH - 1):
            left = pixels[row * _DHASH_WIDTH + col]
            right = pixels[row * _DHASH_WIDTH + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def hamming_distance(hash_a: str, hash_b: str) -> int:
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def fingerprint_image(data: bytes) -> ImageFingerprint:
    with Image.open(io.BytesIO(data)) as image:
        return ImageFingerprint(
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            perceptual_hash=perceptual_hash(image),
            width=image.width,
            height=image.height,
            format=image.format,
            mode=image.mode,
        )


def image_part(
    data: bytes,
    ordinal: int,
    *,
    location: dict[str, Any] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> ParsedPart:
    """Build an image ParsedPart with fingerprint metadata attached."""
    fingerprint = fingerprint_image(data)
    metadata = fingerprint.as_metadata()
    if extra_metadata:
        metadata.update(extra_metadata)
    return ParsedPart(
        part_type=PartType.IMAGE,
        ordinal=ordinal,
        binary_content=data,
        checksum_sha256=fingerprint.checksum_sha256,
        location=location or {},
        metadata=metadata,
    )


class ImageParser:
    """Parses standalone image artifacts. Satisfies DocumentParser."""

    def supports(self, mime_type: str, filename: str) -> bool:
        return mime_type.startswith("image/") or filename.lower().endswith(IMAGE_EXTENSIONS)

    async def parse(self, artifact: FetchedArtifact) -> ParsedDocument:
        return ParsedDocument(
            parts=[image_part(artifact.content, ordinal=0)],
            title=artifact.filename,
        )
