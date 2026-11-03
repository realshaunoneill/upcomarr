"""Helpers shared by the Sonarr and Radarr sources.

Every value is read by name and type-checked here, so a field the code does not ask for
can never reach a record, and an unexpected type drops the item rather than crashing the run.
"""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from ..model import PosterRef
from ..text import clean

# Keys whose values are file-system locations. They are collected from every raw response so
# the leak check can prove none of them reached the published site.
SENSITIVE_KEYS = frozenset({"path", "folderName", "relativePath", "rootFolderPath", "folder"})


def as_str(value: Any, limit: int = 2000) -> str | None:
    """Text from an arr, with control and bidi-override characters removed."""
    if not isinstance(value, str):
        return None
    value = clean(value).strip()
    return value[:limit] or None


def as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def as_int_set(value: Any) -> frozenset[int]:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(v for v in value if as_int(v) is not None)


_IMDB = re.compile(r"^tt\d{5,10}$")
_YOUTUBE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
FINALE_TYPES = frozenset({"series", "season", "midseason"})


def as_public_id(value: Any) -> int | None:
    """A TMDB or TVDB id: a positive integer. They go into links, so nothing else gets through."""
    number = as_int(value)
    return number if number is not None and number > 0 else None


def as_imdb(value: Any) -> str | None:
    return value if isinstance(value, str) and _IMDB.match(value) else None


def as_youtube(value: Any) -> str | None:
    return value if isinstance(value, str) and _YOUTUBE.match(value) else None


def as_finale(value: Any) -> str | None:
    return value if value in FINALE_TYPES else None


def as_utc(value: Any) -> datetime | None:
    """An instant such as Sonarr's airDateUtc."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def as_day(value: Any) -> date | None:
    """A calendar day. Radarr sends release dates as midnight UTC, but they are days, not
    instants: shifting them to a time zone would put every date a day early west of UTC."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def poster_ref(source: str, item_id: int, images: Any) -> PosterRef | None:
    if not isinstance(images, list):
        return None
    for image in images:
        if isinstance(image, dict) and image.get("coverType") == "poster":
            url = image.get("url") if isinstance(image.get("url"), str) else ""
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            version = (query.get("lastWrite") or [""])[0][:64]
            return PosterRef(source, item_id, version)
    return None


def collect_sensitive(value: Any, found: set[str] | None = None) -> set[str]:
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            if k in SENSITIVE_KEYS and isinstance(v, str) and len(v.strip()) >= 4:
                found.add(v.strip())
            else:
                collect_sensitive(v, found)
    elif isinstance(value, list):
        for v in value:
            collect_sensitive(v, found)
    return found


def matches_tags(item_tags: Iterable[int], wanted: frozenset[int] | None) -> bool:
    return wanted is None or bool(set(item_tags) & wanted)
