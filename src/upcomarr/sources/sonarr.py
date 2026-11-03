"""Upcoming episodes from Sonarr's calendar (v3 API; Sonarr v4 and v5 both serve it)."""

from __future__ import annotations

from datetime import date
from typing import Any

from .. import tags
from ..http import Client, FetchError
from ..model import Episode
from . import as_day, as_int, as_int_set, as_str, as_utc, collect_sensitive, matches_tags
from . import poster_ref as _poster_ref

API = "v3"
NAME = "sonarr"


def fetch(
    client: Client,
    start: date,
    end: date,
    include_unmonitored: bool,
    tag_labels: tuple[str, ...],
) -> tuple[list[Episode], set[str]]:
    """Returns the projected episodes, and every file-system path seen, for the leak check."""
    wanted = tags.resolve(client, API, tag_labels)
    raw = client.get_json(
        f"/api/{API}/calendar",
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "includeSeries": "true",
            "unmonitored": "true" if include_unmonitored else "false",
        },
    )
    if not isinstance(raw, list):
        raise FetchError("bad_shape")
    episodes = []
    sensitive: set[str] = set()
    for item in raw:
        collect_sensitive(item, sensitive)
        episode = project(item, include_unmonitored, wanted)
        if episode is not None:
            episodes.append(episode)
    return episodes, sensitive


def project(item: Any, include_unmonitored: bool, wanted: frozenset[int] | None) -> Episode | None:
    if not isinstance(item, dict) or not isinstance(item.get("series"), dict):
        return None
    series = item["series"]
    if not include_unmonitored and item.get("monitored") is not True:
        return None
    if not matches_tags(as_int_set(series.get("tags")), wanted):
        return None
    series_id = as_int(item.get("seriesId"))
    if series_id is None:
        series_id = as_int(series.get("id"))
    title = as_str(series.get("title"), 300)
    season = as_int(item.get("seasonNumber"))
    number = as_int(item.get("episodeNumber"))
    air_utc = as_utc(item.get("airDateUtc"))
    air_date = as_day(item.get("airDate"))
    if series_id is None or title is None or season is None or number is None:
        return None
    if air_utc is None and air_date is None:
        return None
    return Episode(
        series_id=series_id,
        series_title=title,
        network=as_str(series.get("network"), 100),
        series_overview=as_str(series.get("overview")),
        season=season,
        episode=number,
        title=as_str(item.get("title"), 300),
        air_utc=air_utc,
        air_date=air_date,
        has_file=item.get("hasFile") is True,
        poster=_poster_ref(NAME, series_id, series.get("images")),
    )
