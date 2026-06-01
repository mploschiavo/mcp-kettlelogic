"""Serializer layer: render domain objects to the JSON/text the MCP surface
returns. JSON field-name literals live here and nowhere else.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from mcp_kettlelogic.domain.models import (
    ArticleContent,
    ArticleSummary,
    Industry,
    IndustryOverview,
    SearchResults,
)

_INDENT = 2


class ContentSerializer:
    """Converts domain objects into MCP response payloads."""

    def articles_manifest(self, summaries: Iterable[ArticleSummary]) -> str:
        items = [self._summary(summary) for summary in summaries]
        return self._json({"count": len(items), "items": items})

    def industries_list(self, industries: Iterable[Industry]) -> str:
        items = [self._industry(industry) for industry in industries]
        return self._json({"count": len(items), "items": items})

    def search_results(self, results: SearchResults) -> str:
        hits = [
            {
                "slug": hit.slug,
                "title": hit.title,
                "url": hit.url,
                "resource_uri": hit.resource_uri,
            }
            for hit in results.hits
        ]
        return self._json({"query": results.query, "count": results.count, "results": hits})

    def industry_overview(self, overview: IndustryOverview) -> str:
        return self._json(
            {
                "industry": overview.slug,
                "title": overview.title,
                "url": overview.url,
                "overview": overview.overview,
            }
        )

    def article_text(self, content: ArticleContent) -> str:
        summary = content.summary
        return f"# {summary.title}\n\n{summary.url}\n\n{content.text}"

    def _summary(self, summary: ArticleSummary) -> dict[str, str]:
        return {
            "slug": summary.slug,
            "title": summary.title,
            "description": summary.description,
            "url": summary.url,
        }

    def _industry(self, industry: Industry) -> dict[str, str]:
        return {"slug": industry.slug, "title": industry.title, "url": industry.url}

    def _json(self, payload: object) -> str:
        return json.dumps(payload, indent=_INDENT)
