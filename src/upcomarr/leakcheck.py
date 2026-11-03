"""The last gate before publishing: prove that nothing sensitive is in the build.

The allowlist in model.Entry is the real control. This is the backstop that catches a
mistake in it. Every file in the build, and every file name, is searched for:

- each API key, and each arr's base URL and host;
- every file-system path the arrs returned on this run (series and movie folders, files);
- markers that only appear in raw arr data: `/api/`, `/MediaCover`, `lastWrite`, `X-Api-Key`.

A hit fails the run, so nothing is published. The error names the file and which kind of
needle matched, never the needle itself.
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Iterable
from pathlib import Path

MARKERS = ("/api/", "/mediacover", "lastwrite", "x-api-key", "apikey")
MIN_NEEDLE = 6


class LeakError(Exception):
    pass


def needles_for(keys: Iterable[str], urls: Iterable[str], paths: Iterable[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key in keys:
        if key:
            out.append(("api key", key))
    for url in urls:
        out.append(("arr url", url.lower()))
        host = urllib.parse.urlsplit(url).netloc.lower()
        if len(host) >= MIN_NEEDLE:
            out.append(("arr host", host))
    for path in paths:
        if len(path) >= MIN_NEEDLE:
            out.append(("library path", path.lower()))
    out.extend(("arr marker", m) for m in MARKERS)
    return out


def scan(root: Path, needles: list[tuple[str, str]]) -> None:
    """Raise LeakError if any needle appears in any file under root, or in any name."""
    keys = [(kind, n) for kind, n in needles if kind == "api key"]
    others = [(kind, n) for kind, n in needles if kind != "api key"]
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        for kind, needle in keys + others:
            if needle.lower() in rel.lower():
                raise LeakError(f"{kind} in a file name ({rel})")
        if not path.is_file():
            continue
        data = path.read_bytes()
        if data.startswith((b"\xff\xd8\xff", b"\x89PNG", b"RIFF")):
            continue  # poster bytes: binary, checked by name only
        text = data.decode("utf-8", errors="replace")
        lowered = text.lower()
        for kind, needle in keys:
            if needle in text:
                raise LeakError(f"{kind} in {rel}")
        for kind, needle in others:
            if needle in lowered:
                raise LeakError(f"{kind} in {rel}")
