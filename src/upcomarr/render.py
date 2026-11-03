"""Render the static site: index.html, 404.html and upcoming.json.

Everything an arr supplies is untrusted text, so every value goes through `h()`, and the
markup has no inline script, inline style or event handler: the page works under
`default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'`.

The page is complete without JavaScript. app.js only adds the filters, and rewrites dates
and times relative to the viewer's clock.
"""

from __future__ import annotations

import dataclasses
import html
from datetime import date, datetime
from typing import Any

from .model import (
    AIRS,
    EXPECTED,
    IN_CINEMAS,
    ON_PLEX,
    PARTIAL,
    RELEASED,
    Entry,
    entry_to_public,
)
from .schedule import Schedule, long_date, short_date
from .text import clean

SCHEMA = 1


def h(value: Any) -> str:
    """Escape for HTML text and attribute values, and drop control and bidi-override
    characters that could reorder what a viewer sees."""
    return html.escape(clean(str(value)), quote=True)


@dataclasses.dataclass(frozen=True)
class SourceStatus:
    label: str  # "TV" or "Movies"
    ok: bool  # fetched on this run
    stale: bool  # showing saved data from an earlier run
    last_success: datetime | None
    error: str | None  # a short code, never exception text


@dataclasses.dataclass(frozen=True)
class Meta:
    title: str
    generated_at: datetime
    tz_name: str
    version: str
    asset_version: str
    sources: dict[str, SourceStatus]  # "tv" / "movies", configured sources only


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def _stamp(dt: datetime, meta: Meta) -> str:
    """Absolute time in the configured zone; app.js turns it into "12 min ago"."""
    from zoneinfo import ZoneInfo

    local = dt.astimezone(ZoneInfo(meta.tz_name))
    text = f"{short_date(local.date())} {local:%H:%M}"
    return f'<time datetime="{h(_iso(dt))}" data-relative>{h(text)}</time>'


def _badge(entry: Entry) -> tuple[str, str | None]:
    """(badge text, optional context line)."""
    if entry.badge == ON_PLEX:
        return "On Plex now", None
    if entry.badge == PARTIAL:
        return f"{entry.on_plex_count} of {entry.count} on Plex", None
    if entry.badge == AIRS:
        return ("New episodes" if entry.count > 1 else "New episode"), None
    if entry.badge == EXPECTED:
        cinema = entry.cinema_date
        note = f"In cinemas {short_date(date.fromisoformat(cinema))}" if cinema else None
        return "Expected on Plex", note
    if entry.badge == RELEASED:
        when = short_date(date.fromisoformat(entry.expected_date)) if entry.expected_date else None
        return "On its way to Plex", (f"Released {when}" if when else None)
    if entry.badge == IN_CINEMAS:
        if entry.expected_date:
            note = f"On Plex from about {short_date(date.fromisoformat(entry.expected_date))}"
        else:
            note = "Plex date not announced yet"
        return "In cinemas", note
    return entry.badge, None


def _card(entry: Entry, compact: bool = False) -> str:
    poster = f"p/{entry.poster}" if entry.poster else "placeholder.svg"
    meta_bits = [h(entry.label)]
    if entry.network:
        meta_bits.append(h(entry.network))
    if entry.time:
        meta_bits.append(f'<time datetime="{h(entry.date)}T{h(entry.time)}">{h(entry.time)}</time>')
    badge, note = _badge(entry)
    if compact:
        note = None
    parts = [
        f'<li class="card" data-kind="{h(entry.kind)}" data-on-plex="{"true" if entry.on_plex else "false"}">',
        f'<img class="poster" src="{h(poster)}" alt="" width="100" height="150" loading="lazy" decoding="async">',
        '<div class="card-body">',
        f'<h3 class="card-title">{h(entry.title)}</h3>',
        f'<p class="card-meta">{" · ".join(meta_bits)}</p>',
    ]
    if entry.episode_title:
        parts.append(f'<p class="card-episode">{h(entry.episode_title)}</p>')
    parts.append(f'<p class="badge badge-{h(entry.badge)}">{h(badge)}</p>')
    if note:
        parts.append(f'<p class="card-note">{h(note)}</p>')
    if entry.overview and not compact:
        parts.append(f'<details class="card-overview"><summary>About</summary><p>{h(entry.overview)}</p></details>')
    parts.append("</div></li>")
    return "".join(parts)


def _banners(meta: Meta) -> str:
    out = []
    for status in meta.sources.values():
        if status.ok:
            continue
        if status.stale and status.last_success:
            out.append(
                f'<p class="banner" role="status">The {h(status.label.lower())} schedule could not be '
                f"refreshed. It was last updated {_stamp(status.last_success, meta)}.</p>"
            )
        else:
            out.append(
                f'<p class="banner" role="status">The {h(status.label.lower())} schedule is unavailable right now.</p>'
            )
    return "".join(out)


def _head(meta: Meta, title: str) -> str:
    v = h(meta.asset_version)
    return (
        "<!doctype html>"
        f'<html lang="en" data-tz="{h(meta.tz_name)}">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="dark">'
        '<meta name="referrer" content="no-referrer">'
        '<meta name="robots" content="noindex, nofollow">'
        f"<title>{h(title)}</title>"
        f'<link rel="stylesheet" href="style.css?v={v}">'
        '<link rel="icon" href="favicon.svg" type="image/svg+xml">'
        f'<script src="app.js?v={v}" defer></script>'
        "</head>"
    )


def render_index(schedule: Schedule, meta: Meta) -> str:
    body = [
        _head(meta, meta.title),
        f'<body data-today="{h(schedule.today.isoformat())}">',
        '<header class="site-header">',
        f"<h1>{h(meta.title)}</h1>",
        '<p class="tagline">What is on its way to Plex</p>',
        '<nav class="filters" aria-label="Filter" hidden>',
        '<div class="filter-group" role="group" aria-label="Show">',
        '<button type="button" data-filter="all" aria-pressed="true">All</button>',
        '<button type="button" data-filter="tv" aria-pressed="false">TV</button>',
        '<button type="button" data-filter="movie" aria-pressed="false">Movies</button>',
        "</div>",
        '<label class="filter-toggle"><input type="checkbox" data-hide-on-plex> Hide what is already on Plex</label>',
        "</nav>",
        "</header>",
        "<main>",
        _banners(meta),
    ]
    if schedule.recent:
        body.append('<section class="recent" aria-labelledby="recent-h">')
        body.append('<h2 id="recent-h">Just arrived</h2><ul class="cards cards-compact">')
        body.extend(_card(e, compact=True) for e in schedule.recent)
        body.append("</ul></section>")
    if schedule.days:
        for day in schedule.days:
            day_id = f"d-{day.date.isoformat()}"
            body.append(
                f'<section class="day" data-date="{h(day.date.isoformat())}" aria-labelledby="{h(day_id)}">'
                f'<h2 id="{h(day_id)}"><span class="day-name">{h(day.heading)}</span> '
                f'<time datetime="{h(day.date.isoformat())}">{h(day.date_text)}</time></h2>'
                '<ul class="cards">'
            )
            body.extend(_card(e) for e in day.entries)
            body.append("</ul></section>")
    else:
        body.append('<p class="empty">Nothing is scheduled yet. Check back soon.</p>')
    body.append(
        "</main>"
        f'<footer class="site-footer"><p>Updated {_stamp(meta.generated_at, meta)}. '
        f"Times are {h(meta.tz_name.replace('_', ' '))} time.</p>"
        f'<p class="credit">upcomarr {h(meta.version)}</p></footer>'
        "</body></html>"
    )
    return "".join(body)


def render_404(meta: Meta) -> str:
    return (
        _head(meta, f"Not found · {meta.title}") + '<body><main class="not-found"><h1>Not found</h1>'
        '<p><a href="./">Back to what is coming</a></p></main></body></html>'
    )


def upcoming_json(schedule: Schedule, meta: Meta) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "version": meta.version,
        "title": meta.title,
        "generated_at": _iso(meta.generated_at),
        "tz": meta.tz_name,
        "sources": {
            key: {"ok": s.ok, "stale": s.stale, "last_success": _iso(s.last_success)} for key, s in meta.sources.items()
        },
        "days": [
            {
                "date": day.date.isoformat(),
                "label": long_date(day.date),
                "entries": [entry_to_public(e) for e in day.entries],
            }
            for day in schedule.days
        ],
        "recent": [entry_to_public(e) for e in schedule.recent],
    }


def status_json(ok: bool, meta: Meta, error: str | None) -> dict[str, Any]:
    return {
        "ok": ok,
        "version": meta.version,
        "generated_at": _iso(meta.generated_at),
        "error": error,
        "sources": {
            key: {
                "ok": s.ok,
                "stale": s.stale,
                "last_success": _iso(s.last_success),
                "error": s.error,
            }
            for key, s in meta.sources.items()
        },
    }
