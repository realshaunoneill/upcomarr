"""One run: fetch, cache posters, render, check, publish, report."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import __version__, leakcheck, render, schedule
from .config import Config, Source
from .http import Client, FetchError
from .metrics import Registry
from .model import Episode, Movie, episode_from_state, movie_from_state, record_to_state
from .posters import PosterCache
from .publish import Layout, link_or_copy, publish, write_json
from .sources import radarr, sonarr

log = logging.getLogger("upcomarr")
STATIC = Path(__file__).parent / "static"
LABELS = {"sonarr": ("tv", "TV"), "radarr": ("movies", "Movies")}


@dataclasses.dataclass
class SourceResult:
    records: list[Any]
    ok: bool
    stale: bool
    last_success: datetime | None
    error: str | None
    sensitive: set[str]


def asset_version() -> str:
    digest = hashlib.sha256(__version__.encode())
    for path in sorted(STATIC.iterdir()):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


def _load_saved(layout: Layout, name: str) -> tuple[list[Any], datetime] | None:
    try:
        raw = json.loads((layout.state / f"{name}.json").read_text("utf-8"))
        loader = episode_from_state if name == "sonarr" else movie_from_state
        return [loader(r) for r in raw["records"]], datetime.fromisoformat(raw["fetched_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def fetch_source(cfg: Config, src: Source, client: Client, layout: Layout, now: datetime) -> SourceResult:
    today = now.astimezone(cfg.tz).date()
    # One spare day each side: the arrs window in UTC, the page in local time.
    start = today - timedelta(days=cfg.days_behind + 1)
    end = today + timedelta(days=src.days_ahead + 1)
    module = sonarr if src.name == "sonarr" else radarr
    try:
        records, sensitive = module.fetch(client, start, end, cfg.include_unmonitored, src.tags)
    except FetchError as e:
        saved = _load_saved(layout, src.name)
        if saved is not None:
            log.warning("%s: refresh failed (%s); showing data from %s", src.name, e.code, saved[1].isoformat())
            return SourceResult(saved[0], False, True, saved[1], e.code, set())
        log.warning("%s: refresh failed (%s) and nothing is saved", src.name, e.code)
        return SourceResult([], False, False, None, e.code, set())
    write_json(
        layout.state / f"{src.name}.json",
        {"fetched_at": now.isoformat(), "records": [record_to_state(r) for r in records]},
    )
    return SourceResult(records, True, False, now, None, sensitive)


def run_once(cfg: Config, layout: Layout, registry: Registry, now: datetime | None = None) -> bool:
    started = time.monotonic()
    now = now or datetime.now(UTC)
    layout.ensure()
    clients = {s.name: Client(s.url, s.api_key, cfg.request_timeout) for s in cfg.sources}
    results = {s.name: fetch_source(cfg, s, clients[s.name], layout, now) for s in cfg.sources}

    episodes: list[Episode] = results["sonarr"].records if "sonarr" in results else []
    movies: list[Movie] = results["radarr"].records if "radarr" in results else []
    refs = [r.poster for r in [*episodes, *movies] if r.poster is not None]
    posters = PosterCache(layout.posters, layout.state / "posters.json").sync(refs, clients)

    sonarr_cfg, radarr_cfg = cfg.source("sonarr"), cfg.source("radarr")
    sched = schedule.build(
        episodes,
        movies,
        now=now,
        tz=cfg.tz,
        days_behind=cfg.days_behind,
        tv_days_ahead=sonarr_cfg.days_ahead if sonarr_cfg else 0,
        movie_days_ahead=radarr_cfg.days_ahead if radarr_cfg else 0,
        posters=posters,
    )
    meta = render.Meta(
        title=cfg.site_title,
        generated_at=now,
        tz_name=cfg.tz_name,
        version=__version__,
        asset_version=asset_version(),
        sources={
            LABELS[name][0]: render.SourceStatus(LABELS[name][1], r.ok, r.stale, r.last_success, r.error)
            for name, r in results.items()
        },
    )

    def build(target: Path) -> None:
        write_site(target, sched, meta, layout.posters)

    sensitive = set().union(*(r.sensitive for r in results.values()))
    needles = leakcheck.needles_for([s.api_key for s in cfg.sources], [s.url for s in cfg.sources], sensitive)
    error = None
    try:
        publish(layout, build, lambda d: leakcheck.scan(d, needles))
    except leakcheck.LeakError as e:
        error = "leak"
        log.error("publish refused: %s", e)
    except OSError as e:
        error = "write"
        log.error("publish failed: %s", e.strerror or type(e).__name__)

    ok = error is None and all(r.ok for r in results.values())
    write_json(layout.status, render.status_json(ok, meta, error))
    _record_metrics(registry, results, sched, ok, time.monotonic() - started)
    tv = sum(1 for d in sched.days for e in d.entries if e.kind == "tv")
    mv = sum(1 for d in sched.days for e in d.entries if e.kind == "movie")
    log.info(
        "run %s: %d tv and %d movie entries, %d just arrived; %s",
        "ok" if ok else "degraded",
        tv,
        mv,
        len(sched.recent),
        ", ".join(f"{n} {'ok' if r.ok else r.error}" for n, r in results.items()),
    )
    return ok


def write_site(target: Path, sched: schedule.Schedule, meta: render.Meta, poster_dir: Path) -> None:
    (target / "index.html").write_text(render.render_index(sched, meta), "utf-8")
    (target / "404.html").write_text(render.render_404(meta), "utf-8")
    data = render.upcoming_json(sched, meta)
    (target / "upcoming.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    for path in STATIC.iterdir():
        if path.is_file():
            (target / path.name).write_bytes(path.read_bytes())
    used = {e.poster for d in sched.days for e in d.entries if e.poster}
    used |= {e.poster for e in sched.recent if e.poster}
    if used:
        (target / "p").mkdir()
        for name in sorted(used):
            src = poster_dir / name
            if src.is_file():
                link_or_copy(src, target / "p" / name)


def _record_metrics(
    registry: Registry, results: dict[str, SourceResult], sched: schedule.Schedule, ok: bool, seconds: float
) -> None:
    for name, r in results.items():
        registry.set(
            "upcomarr_source_up", "1 if the last fetch from this arr succeeded.", 1 if r.ok else 0, source=name
        )
        if r.last_success:
            registry.set(
                "upcomarr_source_last_success_timestamp_seconds",
                "When this arr was last fetched successfully.",
                r.last_success.timestamp(),
                source=name,
            )
    for kind in ("tv", "movie"):
        registry.set(
            "upcomarr_entries",
            "Entries on the page, by kind.",
            sum(1 for d in sched.days for e in d.entries if e.kind == kind),
            kind=kind,
        )
    registry.set("upcomarr_recent_entries", "Entries in the Just arrived strip.", len(sched.recent))
    registry.set("upcomarr_last_run_success", "1 if the last run fetched every source and published.", 1 if ok else 0)
    registry.set("upcomarr_last_run_timestamp_seconds", "When the last run finished.", time.time())
    registry.set("upcomarr_run_duration_seconds", "How long the last run took.", seconds)
