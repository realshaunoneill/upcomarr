"""A demo site from made-up sample data, for screenshots and for trying the page without an arr.

Every title here is invented. Posters are simple generated SVGs.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import __version__, ical, leakcheck, render, schedule
from .app import asset_version, write_site
from .model import Episode, Links, Movie, PosterRef
from .publish import Layout, publish, write_json

TZ = ZoneInfo("Europe/Dublin")
PALETTE = ("#2b5876", "#4e4376", "#614385", "#516395", "#1d4350", "#a43931", "#3a6073", "#16222a")

SHOWS = (
    # title, network, overview, (day offset, local time, season, first, last, on plex)
    (
        "The Lighthouse Keepers",
        "Northlight",
        "Two estranged sisters inherit a lighthouse and the secrets of the village below it.",
        [(0, "21:00", 2, 5, 5, False)],
    ),
    (
        "Night Market",
        "Channel 9",
        "A street-food stall in a city that only wakes after dark.",
        [(1, "20:00", 1, 1, 8, False)],
    ),
    ("Grand Tour of the Alps", "Velo+", "Every stage of the mountain race, live.", [(2, "13:30", 2026, 7, 9, False)]),
    (
        "Paper Moons",
        "Hearth",
        "A sitcom about a family-run printing shop.",
        [(-1, "20:30", 4, 3, 3, True), (6, "20:30", 4, 4, 4, False)],
    ),
    (
        "Deep Field",
        "Orbit",
        "A documentary series following the crew of a deep-space telescope.",
        [(3, None, 1, 1, 6, False)],
    ),
    ("Harbour Lights", "Northlight", "A coastal police drama.", [(0, "22:00", 3, 1, 2, False)]),
)

# Sonarr's finaleType for a few episodes, so the demo shows the highlights.
FINALES = {("The Lighthouse Keepers", 2, 5): "season", ("Night Market", 1, 8): "season"}
# Made-up trailer ids: the links go to YouTube but nowhere real.
TRAILERS = {"The Last Ferry": "demoTrailer1", "Signal Fires": "demoTrailer2", "Copper Coast": "demoTrailer3"}
LINKS = Links(movie="https://request.example.com/movie/{tmdb}", tv="https://request.example.com/tv/{tmdb}")

MOVIES = (
    # title, year, studio, overview, cinema offset, digital offset, physical offset, on plex days ago
    (
        "The Last Ferry",
        2026,
        "Tidewater Pictures",
        "A night crossing goes wrong in the middle of the Irish Sea.",
        -40,
        2,
        30,
        None,
    ),
    (
        "Signal Fires",
        2026,
        "Ember",
        "A radio operator hears a voice from a station that closed in 1974.",
        5,
        None,
        None,
        None,
    ),
    ("Orchard", 2026, "Greenhouse", "Three generations, one apple harvest.", -60, -1, None, None),
    ("Copper Coast", 2026, "Tidewater Pictures", "A heist on the old mining coast.", 12, 45, None, None),
    ("Small Hours", 2025, "Ember", "A bakery, a blackout and a long night.", -90, -30, -2, 1),
)


def _poster_svg(title: str) -> bytes:
    colour = PALETTE[int(hashlib.sha256(title.encode()).hexdigest(), 16) % len(PALETTE)]
    initials = "".join(w[0] for w in title.split() if w[0].isalpha())[:2].upper()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{colour}"/>'
        '<stop offset="1" stop-color="#111"/></linearGradient></defs>'
        '<rect width="200" height="300" fill="url(#g)"/>'
        f'<text x="100" y="170" font-family="Georgia, serif" font-size="72" fill="#fff" fill-opacity=".85" '
        f'text-anchor="middle">{initials}</text></svg>'
    ).encode()


def sample(now: datetime) -> tuple[list[Episode], list[Movie], dict[str, str], dict[str, bytes]]:
    today = now.astimezone(TZ).date()
    episodes, movies, posters, files = [], [], {}, {}
    for i, (title, network, overview, slots) in enumerate(SHOWS):
        svg = _poster_svg(title)
        name = hashlib.sha256(svg).hexdigest()[:16] + ".svg"
        ref = PosterRef("sonarr", i, "demo")
        posters[ref.key], files[name] = name, svg
        for offset, at, season, first, last, on_plex in slots:
            day = today + timedelta(days=offset)
            air = datetime.combine(day, time.fromisoformat(at), TZ).astimezone(UTC) if at else None
            for number in range(first, last + 1):
                episodes.append(
                    Episode(
                        i,
                        title,
                        network,
                        overview,
                        season,
                        number,
                        f"Episode {number}" if first == last else None,
                        air,
                        day,
                        on_plex,
                        ref,
                        tmdb=900_000 + i,
                        finale=FINALES.get((title, season, number)),
                    )
                )
    for j, (title, year, studio, overview, cinema, digital, physical, added) in enumerate(MOVIES):
        svg = _poster_svg(title)
        name = hashlib.sha256(svg).hexdigest()[:16] + ".svg"
        ref = PosterRef("radarr", j, "demo")
        posters[ref.key], files[name] = name, svg

        def at(offset: int | None):
            return today + timedelta(days=offset) if offset is not None else None

        movies.append(
            Movie(
                j,
                title,
                year,
                studio,
                overview,
                at(cinema),
                at(digital),
                at(physical),
                added is not None,
                at(-added) if added is not None else None,
                ref,
                tmdb=800_000 + j,
                trailer=TRAILERS.get(title),
            )
        )
    return episodes, movies, posters, files


def render_demo(layout: Layout, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    layout.ensure()
    episodes, movies, posters, files = sample(now)
    for name, data in files.items():
        (layout.posters / name).write_bytes(data)
    sched = schedule.build(episodes, movies, now, TZ, 3, 60, 90, posters, LINKS)
    sched = ical.attach(sched, LINKS.calendar)
    meta = render.Meta(
        title="Coming soon",
        generated_at=now,
        tz_name="Europe/Dublin",
        version=__version__,
        asset_version=asset_version(),
        details_label=LINKS.label,
        sources={
            "tv": render.SourceStatus("TV", True, False, now, None),
            "movies": render.SourceStatus("Movies", True, False, now, None),
        },
    )
    needles = leakcheck.needles_for([], [], [])
    publish(layout, lambda d: write_site(d, sched, meta, layout.posters), lambda d: leakcheck.scan(d, needles))
    write_json(layout.status, render.status_json(True, meta, None))
