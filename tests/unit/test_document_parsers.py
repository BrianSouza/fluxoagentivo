"""PDF, DOCX, PPTX and HTML parsers (TASK-008 to TASK-011)."""

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.artifacts.parsing import PartType
from harness.infrastructure.parsers.docx import DocxParser
from harness.infrastructure.parsers.html import HtmlParser
from harness.infrastructure.parsers.pdf import PdfParser
from harness.infrastructure.parsers.pptx import PptxParser
from harness.infrastructure.parsers.registry import default_registry
from tests.unit.parser_fixtures import SAMPLE_HTML, make_docx, make_pdf, make_pptx


def fetched(filename: str, content: bytes, mime_type: str | None = None) -> FetchedArtifact:
    return FetchedArtifact(
        external_id=filename,
        source_uri=f"file:///{filename}",
        filename=filename,
        content=content,
        mime_type=mime_type,
    )


class TestPdfParser:
    async def test_extracts_page_texts_with_page_locations(self) -> None:
        document = await PdfParser().parse(fetched("doc.pdf", make_pdf()))
        pages = [p for p in document.parts if p.part_type == PartType.PAGE]
        assert len(pages) == 2
        assert "Checkout flow overview" in (pages[0].text_content or "")
        assert pages[0].location == {"page": 1}
        assert "Backend services involved" in (pages[1].text_content or "")
        assert pages[1].location == {"page": 2}

    async def test_extracts_embedded_images_with_fingerprint(self) -> None:
        document = await PdfParser().parse(fetched("doc.pdf", make_pdf()))
        images = document.image_parts
        assert len(images) == 1
        assert images[0].location == {"page": 1}
        assert images[0].checksum_sha256 is not None
        assert images[0].metadata["perceptual_hash"]

    def test_supports(self) -> None:
        parser = PdfParser()
        assert parser.supports("application/pdf", "x")
        assert parser.supports("", "report.PDF")
        assert not parser.supports("text/html", "page.html")


class TestDocxParser:
    async def test_extracts_headings_with_levels_and_paragraphs(self) -> None:
        document = await DocxParser().parse(fetched("doc.docx", make_docx()))
        headings = [p for p in document.parts if p.part_type == PartType.HEADING]
        paragraphs = [p for p in document.parts if p.part_type == PartType.PARAGRAPH]
        assert [h.text_content for h in headings] == ["Checkout architecture", "Backend"]
        assert [h.metadata["level"] for h in headings] == [1, 2]
        assert any("WebView" in (p.text_content or "") for p in paragraphs)
        assert document.title == "Checkout architecture"

    async def test_extracts_embedded_image(self) -> None:
        document = await DocxParser().parse(fetched("doc.docx", make_docx()))
        images = document.image_parts
        assert len(images) == 1
        assert images[0].checksum_sha256 is not None


class TestPptxParser:
    async def test_slide_boundaries_are_preserved(self) -> None:
        document = await PptxParser().parse(fetched("deck.pptx", make_pptx()))
        slides = [p for p in document.parts if p.part_type == PartType.SLIDE]
        assert len(slides) == 2
        assert slides[0].location == {"slide": 1}
        assert "Checkout flow" in (slides[0].text_content or "")
        assert slides[1].location == {"slide": 2}
        assert "Payment Gateway" in (slides[1].text_content or "")
        assert document.title == "Checkout flow"

    async def test_extracts_slide_images_with_slide_location(self) -> None:
        document = await PptxParser().parse(fetched("deck.pptx", make_pptx()))
        images = document.image_parts
        assert len(images) == 1
        assert images[0].location == {"slide": 2}


class TestHtmlParser:
    async def test_sections_preserve_heading_hierarchy(self) -> None:
        document = await HtmlParser().parse(
            fetched("page.html", SAMPLE_HTML, mime_type="text/html")
        )
        sections = [p for p in document.parts if p.part_type == PartType.SECTION]
        assert [s.metadata["heading"] for s in sections] == ["Checkout flow", "Backend services"]
        assert [s.metadata["level"] for s in sections] == [1, 2]
        assert document.title == "Checkout flow"
        assert "Checkout API" in (sections[1].text_content or "")

    async def test_links_are_preserved_per_section(self) -> None:
        document = await HtmlParser().parse(fetched("page.html", SAMPLE_HTML))
        sections = [p for p in document.parts if p.part_type == PartType.SECTION]
        assert sections[0].metadata["links"] == [{"text": "WebView", "href": "/wiki/webview"}]
        assert sections[1].metadata["links"] == [
            {"text": "Checkout API", "href": "/wiki/checkout-api"}
        ]

    async def test_image_references_are_kept(self) -> None:
        document = await HtmlParser().parse(fetched("page.html", SAMPLE_HTML))
        refs = [p for p in document.parts if p.part_type == PartType.IMAGE_REF]
        assert len(refs) == 1
        assert refs[0].metadata["src"] == "/images/checkout.png"
        assert refs[0].metadata["alt"] == "Checkout diagram"
        assert refs[0].metadata["section"] == "Checkout flow"

    async def test_boilerplate_is_removed(self) -> None:
        document = await HtmlParser().parse(fetched("page.html", SAMPLE_HTML))
        all_text = "\n".join(p.text_content or "" for p in document.parts)
        assert "console.log" not in all_text
        assert "color: red" not in all_text


class TestRegistry:
    def test_finds_parser_by_mime_or_extension(self) -> None:
        registry = default_registry()
        assert type(registry.find("application/pdf", "x")).__name__ == "PdfParser"
        assert type(registry.find(None, "deck.pptx")).__name__ == "PptxParser"
        assert type(registry.find("text/html", "page")).__name__ == "HtmlParser"
        assert type(registry.find("image/webp", "x.webp")).__name__ == "ImageParser"

    def test_unsupported_formats_return_none_for_explicit_recording(self) -> None:
        registry = default_registry()
        assert registry.find("application/msword", "legacy.doc") is None
        assert registry.find(None, "archive.zip") is None
