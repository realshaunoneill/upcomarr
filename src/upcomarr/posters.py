"""Poster cache.

Posters come from the arr's own API (`/api/v3/mediacover/<id>/poster-250.jpg`, which takes
the key, unlike the UI's `/MediaCover/` route), so viewers' browsers never fetch anything
from a third party and the page's CSP can stay `img-src 'self'`.

Files are named by a hash of their bytes. The name says nothing about the arr's ids, it
changes only when the image does, and so the web server can cache it forever. The map from
arr item to file lives in the generator's private state folder.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

from .http import Client, FetchError
from .model import PosterRef

SIZE = "poster-250.jpg"
_MAGIC = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG\r\n\x1a\n", ".png"), (b"RIFF", ".webp"))


def _extension(data: bytes) -> str | None:
    for magic, ext in _MAGIC:
        if data.startswith(magic):
            if ext == ".webp" and data[8:12] != b"WEBP":
                return None
            return ext
    return None


class PosterCache:
    def __init__(self, cache_dir: Path, state_file: Path):
        self.dir = cache_dir
        self.state_file = state_file
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            self.state: dict[str, dict[str, str]] = json.loads(state_file.read_text("utf-8"))
        except (OSError, ValueError):
            self.state = {}

    def sync(self, refs: Iterable[PosterRef], clients: Mapping[str, Client]) -> dict[str, str]:
        """Fetch new or changed posters. Returns PosterRef.key -> file name, for those we have.

        A failed fetch keeps the previous file if there is one, so a flaky arr never blanks
        the page's artwork."""
        wanted = {ref.key: ref for ref in refs}
        result: dict[str, str] = {}
        for key, ref in wanted.items():
            known = self.state.get(key)
            if known and known.get("version") == ref.version and (self.dir / known["file"]).is_file():
                result[key] = known["file"]
                continue
            client = clients.get(ref.source)
            name = self._fetch(client, ref) if client is not None else None
            if name is not None:
                self.state[key] = {"version": ref.version, "file": name}
                result[key] = name
            elif known and (self.dir / known["file"]).is_file():
                result[key] = known["file"]
        # Forget items that are no longer on any calendar, then their files.
        self.state = {k: v for k, v in self.state.items() if k in wanted}
        self._prune({v["file"] for v in self.state.values()})
        self._save()
        return result

    def _fetch(self, client: Client, ref: PosterRef) -> str | None:
        try:
            data, _ = client.get_bytes(f"/api/v3/mediacover/{ref.item_id}/{SIZE}")
        except FetchError:
            return None
        ext = _extension(data)
        if ext is None:
            return None
        name = hashlib.sha256(data).hexdigest()[:16] + ext
        path = self.dir / name
        if not path.is_file():
            tmp = self.dir / f".{name}.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, path)
        return name

    def _prune(self, keep: set[str]) -> None:
        for path in self.dir.iterdir():
            if path.is_file() and path.name not in keep:
                path.unlink(missing_ok=True)

    def _save(self) -> None:
        tmp = self.state_file.with_name(self.state_file.name + ".tmp")
        tmp.write_text(json.dumps(self.state, sort_keys=True), "utf-8")
        os.replace(tmp, self.state_file)
