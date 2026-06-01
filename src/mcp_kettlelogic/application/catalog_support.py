"""Shared discovery helper: pull same-site section slugs out of an index page."""

from __future__ import annotations

import re

from mcp_kettlelogic.infrastructure.html_parsing import HtmlParser

_SCHEME_MARKER = "://"


class SectionSlugReader:
    """Extracts ``<slug>`` for same-site ``/{section}/<slug>/`` links.

    Only relative hrefs are considered same-site; absolute URLs (any scheme) are
    skipped so a link to another domain's matching path cannot leak in.
    """

    def __init__(self, html_parser: HtmlParser) -> None:
        self._parser = html_parser

    def slugs(self, html: str, section: str) -> list[str]:
        pattern = re.compile(rf"^/{re.escape(section)}/([^/?#]+)/?$")
        seen: set[str] = set()
        ordered: list[str] = []
        for link in self._parser.extract_links(html):
            if _SCHEME_MARKER in link.href:
                continue
            match = pattern.match(link.href)
            if match is None:
                continue
            slug = match.group(1)
            if slug not in seen:
                seen.add(slug)
                ordered.append(slug)
        return ordered
