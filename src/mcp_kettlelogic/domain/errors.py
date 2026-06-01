"""Domain-level exceptions.

The HTTP client translates transport errors into these, so the application and
interface layers never import or catch ``httpx`` directly.
"""

from __future__ import annotations


class ContentError(Exception):
    """Base class for content-retrieval failures."""


class FetchError(ContentError):
    """A page could not be retrieved."""


class NotFoundError(FetchError):
    """A page returned 404."""


class UnknownIndustryError(ContentError):
    """The requested industry slug does not exist on the site."""


class EmptyQueryError(ContentError):
    """A search was attempted with a blank query."""
