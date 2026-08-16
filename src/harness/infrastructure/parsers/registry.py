"""Parser lookup by MIME type / filename.

Unsupported formats return None so callers can record them as unsupported —
they must never silently disappear (docs/spec/00_MASTER_SPEC.md, section 8).
"""

from collections.abc import Sequence

from harness.domain.artifacts.parsing import DocumentParser
from harness.infrastructure.parsers.docx import DocxParser
from harness.infrastructure.parsers.html import HtmlParser
from harness.infrastructure.parsers.images import ImageParser
from harness.infrastructure.parsers.pdf import PdfParser
from harness.infrastructure.parsers.pptx import PptxParser


class ParserRegistry:
    def __init__(self, parsers: Sequence[DocumentParser]) -> None:
        self._parsers = list(parsers)

    def find(self, mime_type: str | None, filename: str) -> DocumentParser | None:
        for parser in self._parsers:
            if parser.supports(mime_type or "", filename):
                return parser
        return None


def default_registry() -> ParserRegistry:
    return ParserRegistry(
        [
            PdfParser(),
            DocxParser(),
            PptxParser(),
            HtmlParser(),
            ImageParser(),
        ]
    )
