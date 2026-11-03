"""Records read from the arrs, and the public Entry that is all a viewer ever sees.

The split is the security boundary. `Episode` and `Movie` hold arr ids and poster
references, so they stay inside the generator (in memory and in its private state folder).
`Entry` is the allowlist: the page and `upcoming.json` are built from it and nothing else,
and `ENTRY_FIELDS` is checked by the tests against a copy kept there.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from typing import Any


@dataclasses.dataclass(frozen=True)
class PosterRef:
    source: str  # "sonarr" or "radarr"
    item_id: int  # series id or movie id; never published
    version: str  # the arr's lastWrite token, so a changed poster is fetched again

    @property
    def key(self) -> str:
        return f"{self.source}:{self.item_id}"


@dataclasses.dataclass(frozen=True)
class Episode:
    series_id: int
    series_title: str
    network: str | None
    series_overview: str | None
    season: int
    episode: int
    title: str | None
    air_utc: datetime | None
    air_date: date | None
    has_file: bool
    poster: PosterRef | None
    # Public ids, used only to build the configured details link. Validated in sources/.
    tmdb: int | None = None
    tvdb: int | None = None
    imdb: str | None = None
    finale: str | None = None  # Sonarr's finaleType: "series", "season" or "midseason"
    runtime: int | None = None  # minutes: the episode's, else the series'


@dataclasses.dataclass(frozen=True)
class Movie:
    movie_id: int
    title: str
    year: int | None
    studio: str | None
    overview: str | None
    cinema: date | None
    digital: date | None
    physical: date | None
    has_file: bool
    file_added: date | None
    poster: PosterRef | None
    tmdb: int | None = None
    imdb: str | None = None
    trailer: str | None = None  # a YouTube video id, validated in sources/


# Badges, in the words the page uses.
AIRS = "airs"
ON_PLEX = "on_plex"
PARTIAL = "partial"
EXPECTED = "expected"
RELEASED = "released"
IN_CINEMAS = "in_cinemas"

# Highlights: an extra tag on a TV entry, worked out in schedule.highlight().
HIGHLIGHTS = (
    "new_series", "season_premiere", "full_season", "new_series_full",
    "midseason_finale", "season_finale", "series_finale",
)  # fmt: skip


@dataclasses.dataclass(frozen=True)
class Links:
    """Where a card's buttons point. Templates take {tmdb}, {tvdb} and {imdb}; a link whose id is
    unknown is left out rather than half-filled."""

    movie: str | None = None
    tv: str | None = None
    label: str = "Details"
    trailers: bool = True
    calendar: bool = True  # an "Add to calendar" .ics per upcoming card


@dataclasses.dataclass(frozen=True)
class Entry:
    kind: str  # "tv" or "movie"
    title: str
    label: str  # "S02E01–E08", "Special", "Movie (2026)"
    episode_title: str | None
    count: int
    on_plex_count: int
    network: str | None  # network for TV, studio for movies
    overview: str | None
    date: str  # local date, YYYY-MM-DD
    time: str | None  # local time, HH:MM, TV only
    badge: str
    on_plex: bool
    expected_date: str | None
    expected_via: str | None  # "digital" or "physical"
    cinema_date: str | None
    poster: str | None  # file name under p/, or None for the placeholder
    highlight: str | None = None  # one of HIGHLIGHTS, TV only
    trailer: str | None = None  # https://www.youtube.com/watch?v=<id>, movies only
    link: str | None = None  # the configured details link, filled in
    starts_at: str | None = None  # TV: the first air time, UTC, ISO 8601 (for the calendar file)
    runtime: int | None = None  # TV: minutes
    calendar: str | None = None  # path of this card's .ics under the site, e.g. cal/<hash>.ics


ENTRY_FIELDS = tuple(f.name for f in dataclasses.fields(Entry))


def entry_to_public(entry: Entry) -> dict[str, Any]:
    return {name: getattr(entry, name) for name in ENTRY_FIELDS}


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def record_to_state(rec: Episode | Movie) -> dict[str, Any]:
    """Serialise a record for the private state folder (never published)."""
    out: dict[str, Any] = {}
    for f in dataclasses.fields(rec):
        value = getattr(rec, f.name)
        if isinstance(value, PosterRef):
            value = dataclasses.asdict(value)
        elif isinstance(value, date | datetime):
            value = _iso(value)
        out[f.name] = value
    return out


def _poster(raw: Any) -> PosterRef | None:
    if not isinstance(raw, dict):
        return None
    return PosterRef(str(raw["source"]), int(raw["item_id"]), str(raw["version"]))


def _dt(raw: Any) -> datetime | None:
    return datetime.fromisoformat(raw) if isinstance(raw, str) else None


def _d(raw: Any) -> date | None:
    return date.fromisoformat(raw) if isinstance(raw, str) else None


def episode_from_state(raw: dict[str, Any]) -> Episode:
    return Episode(
        series_id=int(raw["series_id"]),
        series_title=str(raw["series_title"]),
        network=raw.get("network"),
        series_overview=raw.get("series_overview"),
        season=int(raw["season"]),
        episode=int(raw["episode"]),
        title=raw.get("title"),
        air_utc=_dt(raw.get("air_utc")),
        air_date=_d(raw.get("air_date")),
        has_file=bool(raw["has_file"]),
        poster=_poster(raw.get("poster")),
        tmdb=raw.get("tmdb"),
        tvdb=raw.get("tvdb"),
        imdb=raw.get("imdb"),
        finale=raw.get("finale"),
        runtime=raw.get("runtime"),
    )


def movie_from_state(raw: dict[str, Any]) -> Movie:
    return Movie(
        movie_id=int(raw["movie_id"]),
        title=str(raw["title"]),
        year=raw.get("year"),
        studio=raw.get("studio"),
        overview=raw.get("overview"),
        cinema=_d(raw.get("cinema")),
        digital=_d(raw.get("digital")),
        physical=_d(raw.get("physical")),
        has_file=bool(raw["has_file"]),
        file_added=_d(raw.get("file_added")),
        poster=_poster(raw.get("poster")),
        tmdb=raw.get("tmdb"),
        imdb=raw.get("imdb"),
        trailer=raw.get("trailer"),
    )
