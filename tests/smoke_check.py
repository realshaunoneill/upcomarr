"""Checks the running web container, from inside the smoke test's network.

    python -m tests.smoke_check http://upcomarr-web:8080 /site

/site is the shared volume, mounted read-only, for the canary scan.
"""

from __future__ import annotations

import http.client
import json
import sys
import urllib.parse
from pathlib import Path

from . import fixtures

HEADERS = {
    "content-security-policy": "default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
}
failures: list[str] = []


def request(base: str, method: str, path: str) -> tuple[int, dict[str, str], bytes]:
    parts = urllib.parse.urlsplit(base)
    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=10)
    conn.request(method, path)
    resp = conn.getresponse()
    body = resp.read()
    headers = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, headers, body


def expect(cond: bool, what: str) -> None:
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        failures.append(what)


def main(base: str, site: str) -> int:
    status, headers, body = request(base, "GET", "/")
    expect(status == 200, "/ is 200")
    page = body.decode()
    expect("Night Market" in page and "The Last Ferry" in page, "/ lists the fixture items")
    for name, value in HEADERS.items():
        expect(headers.get(name) == value, f"/ sends {name}")
    expect(headers.get("cache-control") == "no-cache", "/ is no-cache")
    expect("server" not in headers or "/" not in headers["server"], "server version hidden")

    status, headers, body = request(base, "GET", "/upcoming.json")
    expect(status == 200 and json.loads(body)["schema"] == 1, "/upcoming.json is served")
    expect(headers.get("x-frame-options") == "DENY", "/upcoming.json has the headers")

    status, headers, body = request(base, "GET", "/_status.json")
    expect(status == 200 and json.loads(body)["ok"] is True, "/_status.json says ok")
    expect(headers.get("cache-control") == "no-store", "/_status.json is no-store")

    posters = json.loads(request(base, "GET", "/upcoming.json")[2])["days"][0]["entries"]
    poster = next((e["poster"] for e in posters if e["poster"]), None)
    expect(poster is not None, "an entry has a poster")
    if poster:
        status, headers, body = request(base, "GET", f"/p/{poster}")
        expect(status == 200 and body.startswith(b"\xff\xd8\xff"), "the poster is served")
        expect("immutable" in headers.get("cache-control", ""), "the poster is cached as immutable")
        expect(headers.get("x-content-type-options") == "nosniff", "the poster has the headers")

    for path in ("/p/", "/builds/", "/.state/sonarr.json", "/status.json", "/../status.json", "/nope", "/.hidden"):
        status, headers, _ = request(base, "GET", path)
        expect(status in (403, 404), f"{path} is not served ({status})")
        expect(headers.get("x-frame-options") == "DENY", f"{path} error still has the headers")
    for method in ("POST", "PUT", "DELETE"):
        status, _, _ = request(base, method, "/")
        expect(status == 405, f"{method} / is 405")

    root = Path(site)
    forbidden = ["CANARY", fixtures.API_KEY, fixtures.OTHER_KEY, "/api/", "lastWrite", "MediaCover", "/data/"]
    files = [p for p in (root / "current").resolve().rglob("*") if p.is_file()] + [root / "status.json"]
    leaks = []
    for path in files:
        data = path.read_bytes()
        text = "" if data.startswith(b"\xff\xd8\xff") else data.decode("utf-8")
        leaks += [f"{n!r} in {path.name}" for n in forbidden if n in text or n in path.name]
    expect(not leaks, f"no canary, key or path in {len(files)} published files {leaks or ''}")

    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
