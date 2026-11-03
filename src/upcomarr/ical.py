"""One-off calendar files (RFC 5545) for the "Add to calendar" button.

Built from the public Entry and nothing else, so no field outside the allowlist can reach them. Each file holds one
event, imported once by whatever opens it. It is not a subscription, so nothing has to fetch it later, and it works
behind any login that the page itself sits behind.

- TV: a timed event at the first air time, in UTC, lasting the runtime (60 minutes if Sonarr does not know it), or an
  all-day event when there is no air time.
- Films: an all-day event on the day the card sits on: the day it is expected on Plex, or its cinema date.
- Events are TRANSPARENT ("free"), so they never block anyone's diary.
- The UID comes from the title and the label, not the date. Re-adding a card after its date moves updates the event in
  calendars that honour UIDs, rather than adding a second one.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import UTC, date, datetime, timedelta

from .model import AIRS, EXPECTED, IN_CINEMAS, PARTIAL, Entry
from .schedule import Schedule, short_date

DEFAULT_MINUTES = 60


def uid_hash(entry: Entry) -> str:
    return hashlib.sha256(f"{entry.kind}|{entry.title}|{entry.label}".encode()).hexdigest()[:20]


def path_for(entry: Entry) -> str:
    return f"cal/{uid_hash(entry)}.ics"


def wanted(entry: Entry) -> bool:
    """A card gets a calendar file only while it is still coming: an episode not yet all on Plex, or a film
    expected or in cinemas. Nothing in "Just arrived", and not a film already released."""
    if entry.kind == "tv":
        return entry.badge in (AIRS, PARTIAL)
    return entry.badge in (EXPECTED, IN_CINEMAS)


def attach(schedule: Schedule, enabled: bool) -> Schedule:
    """The schedule with each eligible card's calendar path filled in (or unchanged when disabled)."""
    if not enabled:
        return schedule
    days = tuple(
        dataclasses.replace(
            day, entries=tuple(dataclasses.replace(e, calendar=path_for(e)) if wanted(e) else e for e in day.entries)
        )
        for day in schedule.days
    )
    return dataclasses.replace(schedule, days=days)


def escape(text: str) -> str:
    """RFC 5545 TEXT: backslash, semicolon and comma are escaped, and newlines become \\n."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    """Fold to 75 octets per line, continuation lines starting with a space, never inside a UTF-8 character."""
    parts: list[str] = []
    current, size = "", 0
    for char in line:
        width = len(char.encode())
        limit = 75 if not parts else 74  # the leading space of a continuation line is one of its 75
        if size + width > limit:
            parts.append(current)
            current, size = char, width
        else:
            current += char
            size += width
    parts.append(current)
    return "\r\n ".join(parts)


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def summary(entry: Entry) -> str:
    if entry.kind == "tv":
        text = f"{entry.title} {entry.label}"
        return f"{text}: {entry.episode_title}" if entry.episode_title else text
    if entry.badge == IN_CINEMAS:
        return f"{entry.title} in cinemas"
    if entry.badge == EXPECTED:
        return f"{entry.title} on Plex"
    return entry.title


def description(entry: Entry) -> str:
    parts = []
    if entry.network:
        parts.append(entry.network)
    if entry.badge == IN_CINEMAS and entry.expected_date:
        parts.append(f"Expected on Plex from about {short_date(date.fromisoformat(entry.expected_date))}.")
    if entry.overview:
        parts.append(entry.overview)
    if entry.link:
        parts.append(entry.link)
    return "\n\n".join(parts)


def event(entry: Entry, generated_at: datetime, version: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//upcomarr//{version}//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid_hash(entry)}@upcomarr",
        f"DTSTAMP:{_utc(generated_at)}",
    ]
    if entry.kind == "tv" and entry.starts_at:
        start = datetime.fromisoformat(entry.starts_at)
        end = start + timedelta(minutes=entry.runtime or DEFAULT_MINUTES)
        lines += [f"DTSTART:{_utc(start)}", f"DTEND:{_utc(end)}"]
    else:
        day = date.fromisoformat(entry.date)
        lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    lines.append(f"SUMMARY:{escape(summary(entry))}")
    text = description(entry)
    if text:
        lines.append(f"DESCRIPTION:{escape(text)}")
    if entry.link:
        lines.append(f"URL:{entry.link}")
    lines += ["TRANSP:TRANSPARENT", "END:VEVENT", "END:VCALENDAR"]
    return "".join(fold(line) + "\r\n" for line in lines)
