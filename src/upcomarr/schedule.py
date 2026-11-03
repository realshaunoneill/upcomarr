"""Turn episode and movie records into the page's schedule: entries grouped by local day.

Rules worth knowing:

- Episodes of one series that air on the same local day collapse into one entry
  ("S02E01–E08"), so a season dropped at once, or a weekend of race sessions, is one card.
- Times are converted with astimezone() only. Europe/Dublin has a *negative* DST offset in
  winter, so anything that reasons about dst() directly gets Irish times wrong.
- Movie dates are calendar days and are never shifted to a time zone.
- A movie goes on the day it is expected on Plex: its digital release, else its physical
  one. A movie with only a cinema date in the window goes on that date, as "In cinemas".
- Things already on Plex are not "coming". They appear only in the "Just arrived" strip,
  and only if they arrived in the last DAYS_BEHIND days.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .model import (
    AIRS,
    EXPECTED,
    IN_CINEMAS,
    ON_PLEX,
    PARTIAL,
    RELEASED,
    Entry,
    Episode,
    Movie,
)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
OVERVIEW_LIMIT = 600
_PLACEHOLDER_TITLES = frozenset({"tba", "tbd", "tba.", "to be announced"})


@dataclasses.dataclass(frozen=True)
class Day:
    date: date
    heading: str  # "Today", "Tomorrow", or the weekday
    date_text: str  # "5 November", shown after the heading
    entries: tuple[Entry, ...]


@dataclasses.dataclass(frozen=True)
class Schedule:
    today: date
    days: tuple[Day, ...]
    recent: tuple[Entry, ...]


def long_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def day_month(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]}"


def short_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1][:3]}"


def day_heading(d: date, today: date) -> str:
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return WEEKDAYS[d.weekday()]


def trim(text: str | None, limit: int = OVERVIEW_LIMIT) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:")
    return cut + "…"


def _ranges(numbers: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for n in numbers:
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def episode_label(episodes: Iterable[Episode]) -> str:
    by_season: dict[int, set[int]] = defaultdict(set)
    for ep in episodes:
        by_season[ep.season].add(ep.episode)
    parts = []
    for season in sorted(by_season):
        numbers = sorted(by_season[season])
        if season == 0:
            parts.append("Special" if len(numbers) == 1 else f"{len(numbers)} specials")
            continue
        spans = ", ".join(f"E{a:02d}" if a == b else f"E{a:02d}–E{b:02d}" for a, b in _ranges(numbers))
        parts.append(f"S{season:02d}{spans}")
    return ", ".join(parts)


def _local(ep: Episode, tz: ZoneInfo) -> tuple[date, str | None]:
    if ep.air_utc is not None:
        local = ep.air_utc.astimezone(tz)
        return local.date(), local.strftime("%H:%M")
    assert ep.air_date is not None  # sources drop episodes with neither
    return ep.air_date, None


def _episode_title(ep: Episode) -> str | None:
    if ep.title and ep.title.strip().lower() not in _PLACEHOLDER_TITLES:
        return ep.title
    return None


def _tv_entries(
    episodes: Iterable[Episode],
    tz: ZoneInfo,
    today: date,
    days_behind: int,
    days_ahead: int,
    posters: Mapping[str, str],
) -> tuple[list[Entry], list[Entry]]:
    groups: dict[tuple[int, date], list[tuple[str | None, Episode]]] = defaultdict(list)
    for ep in episodes:
        day, at = _local(ep, tz)
        groups[(ep.series_id, day)].append((at, ep))

    upcoming: list[Entry] = []
    recent: list[Entry] = []
    first_day = today - timedelta(days=days_behind)
    last_day = today + timedelta(days=days_ahead)
    for (_, day), items in groups.items():
        if day < first_day or day > last_day:
            continue
        items.sort(key=lambda pair: (pair[1].season, pair[1].episode))
        eps = [ep for _, ep in items]
        count = len(eps)
        on_plex = sum(ep.has_file for ep in eps)
        if day < today and on_plex == 0:
            continue  # aired, but not here yet: not news either way
        if on_plex == count:
            badge = ON_PLEX
        elif on_plex:
            badge = PARTIAL
        else:
            badge = AIRS
        times = [at for at, _ in items if at]
        lead = eps[0]
        entry = Entry(
            kind="tv",
            title=lead.series_title,
            label=episode_label(eps),
            episode_title=_episode_title(lead) if count == 1 else None,
            count=count,
            on_plex_count=on_plex,
            network=lead.network,
            overview=trim(lead.series_overview),
            date=day.isoformat(),
            time=min(times) if times else None,
            badge=badge,
            on_plex=on_plex == count,
            expected_date=None,
            expected_via=None,
            cinema_date=None,
            poster=posters.get(lead.poster.key) if lead.poster else None,
        )
        (recent if day < today else upcoming).append(entry)
    return upcoming, recent


def place_movie(
    movie: Movie, today: date, days_behind: int, days_ahead: int
) -> tuple[date, str, date | None, str | None] | None:
    """Where a movie that is not yet on Plex goes: (day, badge, expected date, via)."""
    first_day = today - timedelta(days=days_behind)
    last_day = today + timedelta(days=days_ahead)
    for when, via in ((movie.digital, "digital"), (movie.physical, "physical")):
        if when is None:
            continue
        if today <= when <= last_day:
            return when, EXPECTED, when, via
        if first_day <= when < today:
            return today, RELEASED, when, via
    if movie.cinema is not None and today <= movie.cinema <= last_day:
        later = [(d, v) for d, v in ((movie.digital, "digital"), (movie.physical, "physical")) if d and d > today]
        expected, via = min(later) if later else (None, None)
        return movie.cinema, IN_CINEMAS, expected, via
    return None


def _movie_entries(
    movies: Iterable[Movie],
    today: date,
    days_behind: int,
    days_ahead: int,
    posters: Mapping[str, str],
) -> tuple[list[Entry], list[Entry]]:
    upcoming: list[Entry] = []
    recent: list[Entry] = []
    first_day = today - timedelta(days=days_behind)
    for movie in movies:
        poster = posters.get(movie.poster.key) if movie.poster else None
        common = {
            "kind": "movie",
            "title": movie.title,
            "label": f"Movie ({movie.year})" if movie.year else "Movie",
            "episode_title": None,
            "count": 1,
            "network": movie.studio,
            "overview": trim(movie.overview),
            "time": None,
            "cinema_date": movie.cinema.isoformat() if movie.cinema else None,
            "poster": poster,
        }
        if movie.has_file:
            added = movie.file_added
            if added is not None and first_day <= added <= today:
                recent.append(
                    Entry(
                        **common,
                        on_plex_count=1,
                        date=added.isoformat(),
                        badge=ON_PLEX,
                        on_plex=True,
                        expected_date=None,
                        expected_via=None,
                    )
                )
            continue
        placed = place_movie(movie, today, days_behind, days_ahead)
        if placed is None:
            continue
        day, badge, expected, via = placed
        upcoming.append(
            Entry(
                **common,
                on_plex_count=0,
                date=day.isoformat(),
                badge=badge,
                on_plex=False,
                expected_date=expected.isoformat() if expected else None,
                expected_via=via,
            )
        )
    return upcoming, recent


def _sort_key(entry: Entry) -> tuple:
    return (0 if entry.kind == "tv" else 1, entry.time or "99:99", entry.title.lower())


def build(
    episodes: Iterable[Episode],
    movies: Iterable[Movie],
    now: datetime,
    tz: ZoneInfo,
    days_behind: int,
    tv_days_ahead: int,
    movie_days_ahead: int,
    posters: Mapping[str, str],
) -> Schedule:
    today = now.astimezone(tz).date()
    tv_up, tv_recent = _tv_entries(episodes, tz, today, days_behind, tv_days_ahead, posters)
    mv_up, mv_recent = _movie_entries(movies, today, days_behind, movie_days_ahead, posters)

    by_day: dict[date, list[Entry]] = defaultdict(list)
    for entry in tv_up + mv_up:
        by_day[date.fromisoformat(entry.date)].append(entry)
    days = tuple(
        Day(d, day_heading(d, today), day_month(d), tuple(sorted(by_day[d], key=_sort_key))) for d in sorted(by_day)
    )
    recent = tuple(
        sorted(
            tv_recent + mv_recent,
            key=lambda e: (-date.fromisoformat(e.date).toordinal(), e.title.lower()),
        )
    )
    return Schedule(today=today, days=days, recent=recent)
