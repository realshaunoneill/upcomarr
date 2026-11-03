"""Atomic publishing into OUT_DIR.

    OUT_DIR/
      current -> builds/<id>     what the web server serves (a RELATIVE symlink, because the
                                 two containers mount this volume at different paths)
      builds/<id>/               complete builds; the newest few are kept so requests already
                                 in flight finish
      posters/                   the poster cache; builds hard-link from it
      status.json                the last run's result, served as /_status.json
      .state/                    private: projected records, the poster map, the heartbeat.
                                 Never under `current`, so never served.

A build is written to builds/.<id>.partial, checked, renamed, and only then does `current`
move, with os.replace on a temporary link. A failed run leaves `current` exactly as it was.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KEEP_BUILDS = 3
_BUILD_ID = re.compile(r"^\d{8}T\d{6}\.\d{9}Z-[0-9a-f]{6}$")


class Layout:
    def __init__(self, out_dir: Path):
        self.root = out_dir
        self.builds = out_dir / "builds"
        self.posters = out_dir / "posters"
        self.state = out_dir / ".state"
        self.current = out_dir / "current"
        self.status = out_dir / "status.json"
        self.heartbeat = self.state / "heartbeat"

    def ensure(self) -> None:
        for d in (self.builds, self.posters, self.state):
            d.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    os.replace(tmp, path)


def link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def publish(layout: Layout, build: Callable[[Path], None], check: Callable[[Path], None]) -> str:
    """Build into a fresh folder, check it, then point `current` at it. Returns the build id."""
    # Sortable by creation time to the nanosecond: pruning keeps the newest by name.
    ns = time.time_ns()
    stamp = datetime.fromtimestamp(ns // 1_000_000_000, UTC).strftime("%Y%m%dT%H%M%S")
    build_id = f"{stamp}.{ns % 1_000_000_000:09d}Z-{secrets.token_hex(3)}"
    partial = layout.builds / f".{build_id}.partial"
    partial.mkdir()
    try:
        build(partial)
        check(partial)
        final = layout.builds / build_id
        os.rename(partial, final)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    tmp_link = layout.root / ".current.new"
    if tmp_link.is_symlink() or tmp_link.exists():
        tmp_link.unlink()
    os.symlink(os.path.join("builds", build_id), tmp_link)
    os.replace(tmp_link, layout.current)
    prune(layout)
    return build_id


def prune(layout: Layout) -> None:
    """Keep the newest KEEP_BUILDS builds, never the one `current` points at, and clear any
    partial build left by a crash. Only names this module creates are ever removed."""
    target = os.path.basename(os.readlink(layout.current)) if layout.current.is_symlink() else None
    names = sorted(p.name for p in layout.builds.iterdir() if _BUILD_ID.match(p.name))
    for name in names[:-KEEP_BUILDS]:
        if name != target:
            shutil.rmtree(layout.builds / name, ignore_errors=True)
    for p in layout.builds.iterdir():
        if p.name.startswith(".") and p.name.endswith(".partial"):
            age = datetime.now(UTC).timestamp() - p.stat().st_mtime
            if age > 3600:
                shutil.rmtree(p, ignore_errors=True)
