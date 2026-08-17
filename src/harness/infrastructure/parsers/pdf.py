"""PDF parser using PyMuPDF (TASK-008).

Produces one text part per page plus one image part per embedded image,
each located by page number.
"""

import pymupdf

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.artifacts.parsing import ParsedDocument, ParsedPart, PartType
from harness.infrastructure.parsers.images import image_part


class PdfParser:
    """Satisfies DocumentParser."""

    def supports(self, mime_type: str, filename: str) -> bool:
        return mime_type == "application/pdf" or filename.lower().endswith(".pdf")

    async def parse(self, artifact: FetchedArtifact) -> ParsedDocument:
        parts: list[ParsedPart] = []
        ordinal = 0
        with pymupdf.open(stream=artifact.content, filetype="pdf") as document:
            for page_index in range(document.page_count):
                page = document[page_index]
                page_number = page_index + 1
                text = page.get_text("text").strip()
                if text:
                    parts.append(
                        ParsedPart(
                            part_type=PartType.PAGE,
                            ordinal=ordinal,
                            text_content=text,
                            location={"page": page_number},
                        )
                    )
                    ordinal += 1
                for image_info in page.get_images(full=True):
                    xref = image_info[0]
                    extracted = document.extract_image(xref)
                    parts.append(
                        image_part(
                            extracted["image"],
                            ordinal=ordinal,
                            location={"page": page_number},
                            extra_metadata={"source_format": extracted.get("ext")},
                        )
                    )
                    ordinal += 1
            title = (document.metadata or {}).get("title") or None
        return ParsedDocument(parts=parts, title=title)
