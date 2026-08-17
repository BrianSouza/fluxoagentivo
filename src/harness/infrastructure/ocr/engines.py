"""OCR engine adapters (TASK-025).

The default engine is a no-op so the pipeline runs anywhere without system
packages; Tesseract is opt-in and reports clearly when it is unavailable
rather than failing deep inside a job.
"""

from collections.abc import Callable

from harness.domain.enrichment.models import OcrResult


class OcrUnavailableError(RuntimeError):
    """Raised when a configured OCR engine is not installed."""


class NullOcrEngine:
    """Extracts nothing. The safe default when OCR is not configured.

    Returning an empty result (instead of raising) keeps the pipeline's
    'OCR if useful' step optional, as the spec's §3 flow expects.
    """

    name = "none"

    def extract_text(self, image: bytes) -> OcrResult:
        return OcrResult(text="", engine=self.name)


class CallableOcrEngine:
    """Wraps any callable as an OCR engine. Used by tests and custom hooks."""

    def __init__(self, extract: Callable[[bytes], str], *, name: str = "callable") -> None:
        self._extract = extract
        self.name = name

    def extract_text(self, image: bytes) -> OcrResult:
        return OcrResult(text=self._extract(image), engine=self.name)


class TesseractOcrEngine:
    """Tesseract adapter, imported lazily so it stays an optional dependency."""

    name = "tesseract"

    def __init__(self, *, language: str = "eng") -> None:
        self._language = language

    def extract_text(self, image: bytes) -> OcrResult:
        try:
            import io

            import pytesseract  # type: ignore[import-not-found]
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - depends on host packages
            raise OcrUnavailableError(
                "tesseract OCR requires the 'pytesseract' package and the "
                "tesseract binary to be installed"
            ) from exc

        with Image.open(io.BytesIO(image)) as handle:
            text = str(pytesseract.image_to_string(handle, lang=self._language))
        return OcrResult(text=text.strip(), engine=self.name)
