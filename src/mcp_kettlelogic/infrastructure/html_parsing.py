"""HTML parsing built on the standard library — no scraping framework, no regex
over markup. Two ``HTMLParser`` subclasses do extraction; a facade exposes them.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from mcp_kettlelogic import constants
from mcp_kettlelogic.domain.models import HtmlLink, ParsedDocument

_Attrs = list[tuple[str, str | None]]


class TextNormalizer:
    """Title/slug text tidying."""

    def __init__(self) -> None:
        self._suffix = re.compile(constants.TITLE_SUFFIX_SEPARATORS)

    def clean_title(self, raw: str) -> str:
        """Collapse whitespace and drop a trailing ' — Brand' / ' | Brand' suffix."""
        title = " ".join(raw.split())
        if not title:
            return ""
        return self._suffix.split(title)[0].strip()

    def slug_to_title(self, slug: str) -> str:
        return slug.replace("-", " ").title()


class _LinkExtractor(HTMLParser):
    """Collects ``(href, anchor text)`` pairs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[HtmlLink] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: _Attrs) -> None:
        if tag != constants.ANCHOR_TAG:
            return
        href = dict(attrs).get(constants.HREF_ATTR)
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == constants.ANCHOR_TAG and self._href is not None:
            text = " ".join("".join(self._text).split())
            self.links.append(HtmlLink(href=self._href, text=text))
            self._href = None
            self._text = []


class _ReadableTextExtractor(HTMLParser):
    """Extracts the page title, meta description, and readable body text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._title_parts: list[str] = []
        self.description = ""
        self._chunks: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: _Attrs) -> None:
        if tag in constants.SKIP_TEXT_TAGS or tag in constants.SKIP_REGION_TAGS:
            self._skip_depth += 1
            return
        if tag == constants.TITLE_TAG:
            self._in_title = True
        elif tag == constants.META_TAG:
            self._capture_description(dict(attrs))
        if tag in constants.BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in constants.SKIP_TEXT_TAGS or tag in constants.SKIP_REGION_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == constants.TITLE_TAG:
            self._in_title = False
        elif tag in constants.BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        # Capture <title> even though it lives inside the skipped <head>.
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._skip_depth:
            return
        self._chunks.append(data)

    def _capture_description(self, attrs: dict[str, str | None]) -> None:
        if attrs.get(constants.META_NAME_ATTR) != constants.META_DESCRIPTION_NAME:
            return
        content = attrs.get(constants.META_CONTENT_ATTR)
        if content:
            self.description = content.strip()

    @property
    def title(self) -> str:
        return "".join(self._title_parts)

    @property
    def text(self) -> str:
        raw = "".join(self._chunks)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        kept: list[str] = []
        for line in lines:
            if line or (kept and kept[-1]):
                kept.append(line)
        return "\n".join(kept).strip()


class HtmlParser:
    """Facade over the extractor classes."""

    def extract_links(self, html: str) -> list[HtmlLink]:
        extractor = _LinkExtractor()
        extractor.feed(html)
        return extractor.links

    def parse_document(self, html: str) -> ParsedDocument:
        extractor = _ReadableTextExtractor()
        extractor.feed(html)
        return ParsedDocument(
            title=extractor.title,
            description=extractor.description,
            text=extractor.text,
        )
