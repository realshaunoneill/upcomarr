"""Upcoming movies from Radarr's calendar (v3 API).

Radarr returns a movie when any of its cinema, digital or physical dates falls in the
window, so the list includes movies that are already in the library. Placing them is
schedule.py's job; this module only reads the fields.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .. import tags
from ..http import Client, FetchError
from ..model import Movie
from . import as_day, as_int, as_int_set, as_str, collect_sensitive, matches_tags
from . import poster_ref as _poster_ref

API = "v3"
NAME = "radarr"


def fetch(
    client: Client,
    start: date,
    end: date,
    include_unmonitored: bool,
    tag_labels: tuple[str, ...],
) -> tuple[list[Movie], set[str]]:
    """Returns the projected movies, and every file-system path seen, for the leak check."""
    wanted = tags.resolve(client, API, tag_labels)
    raw = client.get_json(
        f"/api/{API}/calendar",
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "unmonitored": "true" if include_unmonitored else "false",
        },
    )
    if not isinstance(raw, list):
        raise FetchError("bad_shape")
    movies = []
    sensitive: set[str] = set()
    for item in raw:
        collect_sensitive(item, sensitive)
        movie = project(item, include_unmonitored, wanted)
        if movie is not None:
            movies.append(movie)
    return movies, sensitive


def project(item: Any, include_unmonitored: bool, wanted: frozenset[int] | None) -> Movie | None:
    if not isinstance(item, dict):
        return None
    if not include_unmonitored and item.get("monitored") is not True:
        return None
    if not matches_tags(as_int_set(item.get("tags")), wanted):
        return None
    movie_id = as_int(item.get("id"))
    title = as_str(item.get("title"), 300)
    if movie_id is None or title is None:
        return None
    has_file = item.get("hasFile") is True
    movie_file = item.get("movieFile")
    file_added = as_day(movie_file.get("dateAdded")) if has_file and isinstance(movie_file, dict) else None
    return Movie(
        movie_id=movie_id,
        title=title,
        year=as_int(item.get("year")),
        studio=as_str(item.get("studio"), 100),
        overview=as_str(item.get("overview")),
        cinema=as_day(item.get("inCinemas")),
        digital=as_day(item.get("digitalRelease")),
        physical=as_day(item.get("physicalRelease")),
        has_file=has_file,
        file_added=file_added,
        poster=_poster_ref(NAME, movie_id, item.get("images")),
    )
