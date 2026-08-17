"""HTML parser preserving headings, links and image references (TASK-011).

Content is split into sections at each h1-h6. Every section part keeps its
heading text/level and the links found inside it; <img> tags become
image_ref parts so visual evidence is never silently dropped. Script,
style and other non-content markup is removed up front.
"""

from typing import Any

from bs4 import BeautifulSoup, Tag

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.artifacts.parsing import ParsedDocument, ParsedPart, PartType

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_TEXT_TAGS = ("p", "li", "pre", "blockquote", "td", "th")
_BOILERPLATE_TAGS = ("script", "style", "noscript", "template")


class HtmlParser:
    """Satisfies DocumentParser."""

    def supports(self, mime_type: str, filename: str) -> bool:
        return mime_type in ("text/html", "application/xhtml+xml") or filename.lower().endswith(
            (".html", ".htm")
        )

    async def parse(self, artifact: FetchedArtifact) -> ParsedDocument:
        soup = BeautifulSoup(artifact.content, "lxml")
        for tag_name in _BOILERPLATE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        title = soup.title.get_text(strip=True) if soup.title else None
        root = soup.body if soup.body is not None else soup

        parts: list[ParsedPart] = []
        ordinal = 0
        section_heading: str | None = None
        section_level = 0
        section_lines: list[str] = []
        section_links: list[dict[str, str]] = []

        def flush_section() -> None:
            nonlocal ordinal
            if not section_lines and not section_heading:
                return
            text_lines = ([section_heading] if section_heading else []) + section_lines
            metadata: dict[str, Any] = {
                "heading": section_heading,
                "level": section_level or None,
                "links": list(section_links),
            }
            parts.append(
                ParsedPart(
                    part_type=PartType.SECTION,
                    ordinal=ordinal,
                    text_content="\n".join(text_lines),
                    metadata=metadata,
                )
            )
            ordinal += 1

        for element in root.find_all([*_HEADING_TAGS, *_TEXT_TAGS, "img"]):
            if not isinstance(element, Tag):
                continue
            if element.name in _HEADING_TAGS:
                flush_section()
                section_heading = element.get_text(" ", strip=True)
                section_level = int(element.name[1])
                section_lines = []
                section_links = []
            elif element.name == "img":
                src = str(element.get("src") or "")
                parts.append(
                    ParsedPart(
                        part_type=PartType.IMAGE_REF,
                        ordinal=ordinal,
                        text_content=str(element.get("alt") or "") or src,
                        metadata={
                            "src": src,
                            "alt": str(element.get("alt") or "") or None,
                            "section": section_heading,
                        },
                    )
                )
                ordinal += 1
            else:
                text = element.get_text(" ", strip=True)
                if text:
                    section_lines.append(text)
                for anchor in element.find_all("a"):
                    if isinstance(anchor, Tag) and anchor.get("href"):
                        section_links.append(
                            {
                                "text": anchor.get_text(" ", strip=True),
                                "href": str(anchor.get("href")),
                            }
                        )
        flush_section()

        return ParsedDocument(parts=parts, title=title)
