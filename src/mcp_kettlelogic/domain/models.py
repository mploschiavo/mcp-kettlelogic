"""Domain value objects.

Content moving through the application is represented by these frozen dataclasses
rather than bare dicts, so the type system — not string keys — guards field
access. Serialization to JSON lives in the interfaces (serializer) layer.
"""

from __future__ import annotations

from dataclasses import dataclass

from mcp_kettlelogic.constants import ARTICLE_RESOURCE_URI_TEMPLATE


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Readable content extracted from a single HTML page."""

    title: str
    description: str
    text: str


@dataclass(frozen=True, slots=True)
class HtmlLink:
    """An anchor discovered on an index page."""

    href: str
    text: str


@dataclass(frozen=True, slots=True)
class ArticleSummary:
    """Catalog entry for an insight article (no body)."""

    slug: str
    title: str
    description: str
    url: str

    @property
    def resource_uri(self) -> str:
        return ARTICLE_RESOURCE_URI_TEMPLATE.format(slug=self.slug)

    def matches(self, needle: str) -> bool:
        """True when the lowercased query appears in slug/title/description."""
        haystack = f"{self.slug} {self.title} {self.description}".lower()
        return needle in haystack


@dataclass(frozen=True, slots=True)
class ArticleContent:
    """An insight article including its readable body text."""

    summary: ArticleSummary
    text: str


@dataclass(frozen=True, slots=True)
class Industry:
    """An industry page entry."""

    slug: str
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class IndustryOverview:
    """A plain-text overview extracted from an industry page."""

    slug: str
    title: str
    url: str
    overview: str


@dataclass(frozen=True, slots=True)
class SearchResults:
    """Outcome of an article search."""

    query: str
    hits: tuple[ArticleSummary, ...]

    @property
    def count(self) -> int:
        return len(self.hits)
