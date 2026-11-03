"""Configuration from environment variables.

Every secret can also come from a file (`SONARR_API_KEY_FILE`), for Docker secrets.
Setting both forms of one variable is an error rather than a silent preference.
"""

from __future__ import annotations

import dataclasses
import re
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .model import Links


class ConfigError(Exception):
    """A setting is missing or invalid. The message never contains a secret's value."""


@dataclasses.dataclass(frozen=True)
class Source:
    name: str  # "sonarr" or "radarr"
    url: str  # base URL, no trailing slash
    api_key: str = dataclasses.field(repr=False)
    days_ahead: int
    tags: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Config:
    sources: tuple[Source, ...]
    days_behind: int
    interval_seconds: int
    tz_name: str
    tz: ZoneInfo
    site_title: str
    include_unmonitored: bool
    out_dir: Path
    metrics_port: int
    request_timeout: float
    links: Links = dataclasses.field(default_factory=Links)

    def source(self, name: str) -> Source | None:
        return next((s for s in self.sources if s.name == name), None)


def _value(env: Mapping[str, str], name: str) -> str | None:
    """Read NAME or NAME_FILE. Empty counts as unset."""
    direct = env.get(name, "").strip()
    path = env.get(f"{name}_FILE", "").strip()
    if direct and path:
        raise ConfigError(f"set {name} or {name}_FILE, not both")
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip() or None
        except OSError as e:
            raise ConfigError(f"cannot read {name}_FILE ({e.strerror})") from None
    return direct or None


def _int(env: Mapping[str, str], name: str, default: int, lo: int, hi: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number") from None
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be between {lo} and {hi}")
    return value


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be true or false")


def _url(name: str, raw: str) -> str:
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ConfigError(f"{name} must be an http:// or https:// URL")
    if parts.username or parts.password:
        raise ConfigError(f"{name} must not contain credentials; use the API key setting")
    if parts.query or parts.fragment:
        raise ConfigError(f"{name} must not have a query string or fragment")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


PLACEHOLDERS = ("{tmdb}", "{tvdb}", "{imdb}")


def _template(env: Mapping[str, str], name: str) -> str | None:
    """A details-link template such as https://request.example.com/movie/{tmdb}."""
    raw = env.get(name, "").strip()
    if not raw:
        return None
    found = re.findall(r"\{[^{}]*\}", raw)
    if not found or any(f not in PLACEHOLDERS for f in found):
        raise ConfigError(f"{name} needs one or more of {', '.join(PLACEHOLDERS)} and no other {{...}}")
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname or "{" in parts.netloc:
        raise ConfigError(f"{name} must be an http:// or https:// URL with the placeholders after the host")
    if parts.username or parts.password:
        raise ConfigError(f"{name} must not contain credentials")
    return raw


def _links(env: Mapping[str, str]) -> Links:
    """SEERR_URL is the shortcut (Seerr, Overseerr and Jellyseerr share /movie/<tmdb> and /tv/<tmdb>);
    DETAILS_URL_MOVIE and DETAILS_URL_TV point anywhere else, and win if both are set."""
    movie = tv = None
    seerr = env.get("SEERR_URL", "").strip()
    if seerr:
        base = _url("SEERR_URL", seerr)
        movie, tv = f"{base}/movie/{{tmdb}}", f"{base}/tv/{{tmdb}}"
    movie = _template(env, "DETAILS_URL_MOVIE") or movie
    tv = _template(env, "DETAILS_URL_TV") or tv
    label = env.get("DETAILS_LABEL", "").strip()[:30] or "Details"
    return Links(
        movie=movie,
        tv=tv,
        label=label,
        trailers=_bool(env, "SHOW_TRAILERS", True),
        calendar=_bool(env, "CALENDAR_BUTTONS", True),
    )


def _tags(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    raw = env.get(name, "")
    return tuple(t.strip().lower() for t in raw.split(",") if t.strip())


def load(env: Mapping[str, str]) -> Config:
    sources = []
    for name, days_default in (("sonarr", 60), ("radarr", 90)):
        upper = name.upper()
        url = _value(env, f"{upper}_URL")
        key = _value(env, f"{upper}_API_KEY")
        if not url and not key:
            continue
        if not url or not key:
            raise ConfigError(f"{upper}_URL and {upper}_API_KEY must be set together")
        sources.append(
            Source(
                name=name,
                url=_url(f"{upper}_URL", url),
                api_key=key,
                days_ahead=_int(env, f"{upper}_DAYS_AHEAD", days_default, 1, 366),
                tags=_tags(env, f"{upper}_TAGS"),
            )
        )
    if not sources:
        raise ConfigError("configure at least one of SONARR_URL/SONARR_API_KEY or RADARR_URL/RADARR_API_KEY")

    tz_name = env.get("TZ", "").strip() or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"TZ {tz_name!r} is not a known time zone") from None

    title = env.get("SITE_TITLE", "").strip() or "Coming soon"
    return Config(
        sources=tuple(sources),
        days_behind=_int(env, "DAYS_BEHIND", 3, 0, 30),
        interval_seconds=_int(env, "INTERVAL_SECONDS", 1800, 60, 86400),
        tz_name=tz_name,
        tz=tz,
        site_title=title[:80],
        include_unmonitored=_bool(env, "INCLUDE_UNMONITORED", False),
        out_dir=Path(env.get("OUT_DIR", "").strip() or "/out"),
        metrics_port=_int(env, "METRICS_PORT", 0, 0, 65535),
        request_timeout=float(_int(env, "REQUEST_TIMEOUT_SECONDS", 20, 1, 300)),
        links=_links(env),
    )
