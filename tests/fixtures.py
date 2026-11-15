"""Synthetic arr responses, shaped like real Sonarr v5 and Radarr v6 calendar replies.

No real library data lives here. Every field the code is not meant to read carries a
`CANARY-...` value, paths point under /data/.../CANARY-..., and the ids that the generator
uses internally are distinctive numbers, so a test can prove none of them reached the site.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)  # a Tuesday; Dublin is on GMT
API_KEY = "CANARYKEY0123456789abcdef01234567"
OTHER_KEY = "CANARYKEYfedcba9876543210fedcba98"
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(range(64)) + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(64)

# Internal ids: must never appear in published output. Episode ids come from episode_id().
SERIES_IDS = (734891, 734892, 734893, 734894)
MOVIE_IDS = (881201, 881202, 881203, 881204, 881205)
INTERNAL_IDS = SERIES_IDS + MOVIE_IDS


def episode_id(show: dict[str, Any], number: int) -> int:
    """Distinct per series and episode number, and unlike any other id here."""
    return 990000 + (show["id"] % 100) * 100 + number


def canary(path: str) -> str:
    return f"CANARY-{path}"


def images(kind: str, item_id: int, last_write: str = "638987000000000000") -> list[dict[str, Any]]:
    return [
        {
            "coverType": "poster",
            "url": f"/MediaCover/{item_id}/poster.jpg?lastWrite={last_write}",
            "remoteUrl": canary(f"{kind}.images.poster.remoteUrl"),
        },
        {
            "coverType": "fanart",
            "url": canary(f"{kind}.images.fanart.url"),
            "remoteUrl": canary(f"{kind}.images.fanart.remoteUrl"),
        },
    ]


def series(
    item_id: int,
    title: str,
    network: str | None = "Northlight",
    tags: tuple[int, ...] = (),
    overview: str | None = None,
    last_write: str = "638987000000000000",
    tmdb: int | None = 610001,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "tmdbId": tmdb,
        "network": network,
        "overview": overview if overview is not None else f"About {title}.",
        "tags": list(tags),
        "monitored": True,
        "images": images("series", item_id, last_write),
        "path": f"/data/tv/CANARY-series-path-{item_id}",
        "rootFolderPath": "/data/tv/CANARY-root",
        "qualityProfileId": 7,
        "languageProfileId": 1,
        "certification": canary("series.certification"),
        "titleSlug": canary("series.titleSlug"),
        "cleanTitle": canary("series.cleanTitle"),
        "sortTitle": canary("series.sortTitle"),
        "imdbId": canary("series.imdbId"),
        "tvdbId": 5550001,
        "tvMazeId": 5550002,
        "genres": [canary("series.genres")],
        "airTime": "21:00",
        "seriesType": "standard",
        "status": "continuing",
        "added": canary("series.added"),
        "seasons": [{"seasonNumber": 1, "monitored": True, "statistics": {"sizeOnDisk": 123456}}],
        "statistics": {"sizeOnDisk": 987654321},
        "ratings": {"votes": 1, "value": 7.5},
    }


def episode(
    show: dict[str, Any],
    season: int,
    number: int,
    air_utc: str | None,
    has_file: bool = False,
    title: str | None = None,
    monitored: bool = True,
    air_date: str | None = None,
    finale: str | None = None,
) -> dict[str, Any]:
    return {
        "id": episode_id(show, number),
        "seriesId": show["id"],
        "series": show,
        "tvdbId": 5551000 + number,
        "episodeFileId": 0,
        "seasonNumber": season,
        "episodeNumber": number,
        "title": title if title is not None else f"Episode {number}",
        "airDate": air_date or (air_utc[:10] if air_utc else None),
        "airDateUtc": air_utc,
        "overview": canary("episode.overview"),
        "runtime": 45,
        "hasFile": has_file,
        "monitored": monitored,
        "unverifiedSceneNumbering": False,
        "finaleType": finale if finale is not None else canary("episode.finaleType"),
    }


def movie(
    item_id: int,
    title: str,
    cinema: str | None = None,
    digital: str | None = None,
    physical: str | None = None,
    has_file: bool = False,
    added: str | None = None,
    tags: tuple[int, ...] = (),
    monitored: bool = True,
    overview: str | None = None,
    trailer: str | None = None,
) -> dict[str, Any]:
    def day(value: str | None) -> str | None:
        return f"{value}T00:00:00Z" if value else None

    return {
        "id": item_id,
        "title": title,
        "originalTitle": canary("movie.originalTitle"),
        "year": 2026,
        "studio": "Tidewater Pictures",
        "overview": overview if overview is not None else f"About {title}.",
        "inCinemas": day(cinema),
        "digitalRelease": day(digital),
        "physicalRelease": day(physical),
        "releaseDate": day(digital or physical or cinema),
        "hasFile": has_file,
        "isAvailable": has_file,
        "monitored": monitored,
        "tags": list(tags),
        "images": images("movie", item_id),
        "path": f"/data/movies/CANARY-movie-path-{item_id}",
        "folderName": f"/data/movies/CANARY-folder-{item_id}",
        "movieFileId": 1 if has_file else 0,
        "movieFile": (
            {
                "id": 1,
                "path": f"/data/movies/CANARY-file-{item_id}.mkv",
                "relativePath": f"CANARY-relative-{item_id}.mkv",
                "dateAdded": f"{added}T14:22:11Z" if added else None,
                "size": 4321987654,
                "quality": {"quality": {"name": canary("movie.quality")}},
            }
            if has_file
            else None
        ),
        "sizeOnDisk": 4321987654 if has_file else 0,
        "qualityProfileId": 9,
        "minimumAvailability": "released",
        "youTubeTrailerId": trailer if trailer is not None else canary("movie.youTubeTrailerId"),
        "imdbId": canary("movie.imdbId"),
        "tmdbId": 4440001,
        "certification": canary("movie.certification"),
        "genres": [canary("movie.genres")],
        "keywords": [canary("movie.keywords")],
        "ratings": {"tmdb": {"votes": 10, "value": 7.1}},
        "runtime": 112,
        "cleanTitle": canary("movie.cleanTitle"),
        "sortTitle": canary("movie.sortTitle"),
        "titleSlug": canary("movie.titleSlug"),
        "website": canary("movie.website"),
        "added": canary("movie.added"),
        "statistics": {"sizeOnDisk": 4321987654},
    }


def shows() -> tuple[dict[str, Any], ...]:
    return (
        series(SERIES_IDS[0], "The Lighthouse Keepers"),
        series(SERIES_IDS[1], "Night Market", network="Channel 9"),
        series(SERIES_IDS[2], "Paper Moons", network=None),
        series(SERIES_IDS[3], "Harbour Lights"),
    )


def sonarr_calendar() -> list[dict[str, Any]]:
    """Four shows around NOW (2026-11-03 12:00 UTC)."""
    keepers, market, moons, harbour = shows()
    out = [episode(keepers, 2, 5, "2026-11-03T21:00:00Z", finale="season")]
    out += [episode(market, 1, n, "2026-11-05T20:00:00Z") for n in range(1, 9)]
    out += [
        episode(moons, 4, 3, "2026-11-01T20:30:00Z", has_file=True),  # just arrived
        episode(moons, 4, 4, "2026-11-08T20:30:00Z", title="TBA"),
        episode(harbour, 3, 1, "2026-11-01T21:00:00Z"),  # aired, not here, not downloading: not shown
        episode(harbour, 3, 2, "2026-11-02T21:00:00Z"),  # aired, downloading now: on today
    ]
    return out


def queue_record(id_key: str, item_id: int | None, status: str, state: str, health: str = "ok") -> dict[str, Any]:
    """One record of an arr's /api/v3/queue, every field the code must not read full of canaries."""
    return {
        "id": 70000 + (item_id or 0) % 1000,
        id_key: item_id,
        "status": status,
        "trackedDownloadState": state,
        "trackedDownloadStatus": health,
        "title": canary("queue.title.Some.Release.1080p.WEB-GROUP"),
        "size": 2_000_000_000,
        "sizeleft": 500_000_000,
        "timeleft": "00:04:10",
        "estimatedCompletionTime": "2026-11-03T12:04:10Z",
        "downloadId": canary("queue.downloadId"),
        "downloadClient": canary("queue.downloadClient"),
        "indexer": canary("queue.indexer"),
        "protocol": "usenet",
        "outputPath": f"/data/usenet/CANARY-output-{item_id}",
        "errorMessage": canary("queue.errorMessage"),
        "statusMessages": [{"title": canary("queue.statusMessages.title"), "messages": [canary("queue.message")]}],
        "quality": {"quality": {"name": canary("queue.quality")}},
    }


def sonarr_queue() -> list[dict[str, Any]]:
    keepers, market, moons, harbour = shows()
    return [
        queue_record("episodeId", episode_id(harbour, 2), "downloading", "downloading"),
        queue_record("episodeId", episode_id(market, 1), "queued", "downloading"),  # out early
        queue_record("episodeId", episode_id(market, 2), "completed", "importPending"),
        queue_record("episodeId", episode_id(moons, 3), "downloading", "downloading"),  # an upgrade: already on Plex
        queue_record("episodeId", episode_id(keepers, 5), "failed", "failedPending", "error"),
        queue_record("episodeId", episode_id(harbour, 1), "paused", "downloading"),
        queue_record("episodeId", None, "downloading", "downloading"),  # a release Sonarr could not match
    ]


def radarr_queue() -> list[dict[str, Any]]:
    return [
        queue_record("movieId", MOVIE_IDS[2], "completed", "importing"),  # Orchard: released, on its way
        queue_record("movieId", MOVIE_IDS[3], "downloading", "downloading"),  # Small Hours: an upgrade
        queue_record("movieId", MOVIE_IDS[0], "completed", "importBlocked", "warning"),  # needs a person
    ]


def radarr_calendar() -> list[dict[str, Any]]:
    return [
        movie(
            MOVIE_IDS[0],
            "The Last Ferry",
            cinema="2026-09-24",
            digital="2026-11-05",
            physical="2026-12-03",
            trailer="aBcDeFgHiJk",
        ),
        movie(MOVIE_IDS[1], "Signal Fires", cinema="2026-11-08"),
        movie(MOVIE_IDS[2], "Orchard", cinema="2026-09-01", digital="2026-11-02"),
        movie(
            MOVIE_IDS[3], "Small Hours", digital="2026-10-01", physical="2026-11-20", has_file=True, added="2026-11-02"
        ),
        movie(
            MOVIE_IDS[4],
            "Old Favourite",
            digital="2026-06-01",
            physical="2026-11-25",
            has_file=True,
            added="2026-06-02",
        ),
    ]


def tags() -> list[dict[str, Any]]:
    return [{"id": 1, "label": "kids"}, {"id": 2, "label": "Shared"}]
