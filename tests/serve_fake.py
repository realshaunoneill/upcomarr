"""Serve the fixture Sonarr (8989) and Radarr (7878) for the container smoke test.

Fixture dates are written around fixtures.NOW. They are shifted by whole days to today, so
the smoke test keeps finding upcoming items whenever it runs.
"""

from __future__ import annotations

import re
import threading
from datetime import UTC, date, datetime, timedelta
from typing import Any

from . import fixtures
from .fakearr import FakeArr

_DAY = re.compile(r"^(\d{4}-\d{2}-\d{2})(.*)$")


def shift(value: Any, days: int) -> Any:
    if isinstance(value, dict):
        return {k: shift(v, days) for k, v in value.items()}
    if isinstance(value, list):
        return [shift(v, days) for v in value]
    if isinstance(value, str) and (m := _DAY.match(value)):
        try:
            moved = date.fromisoformat(m.group(1)) + timedelta(days=days)
        except ValueError:
            return value
        return moved.isoformat() + m.group(2)
    return value


def main() -> None:
    days = (datetime.now(UTC).date() - fixtures.NOW.date()).days
    sonarr = FakeArr(shift(fixtures.sonarr_calendar(), days), fixtures.API_KEY, "Sonarr", "0.0.0.0", 8989)
    radarr = FakeArr(shift(fixtures.radarr_calendar(), days), fixtures.OTHER_KEY, "Radarr", "0.0.0.0", 7878)
    sonarr.__enter__()
    radarr.__enter__()
    print(f"fake arrs up, fixtures shifted {days} days", flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
