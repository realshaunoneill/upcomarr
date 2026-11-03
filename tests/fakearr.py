"""A fake Sonarr/Radarr for tests, on 127.0.0.1 and a random port."""

from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from . import fixtures


class FakeArr:
    def __init__(
        self,
        calendar: list[dict[str, Any]] | None = None,
        key: str = fixtures.API_KEY,
        app: str = "Sonarr",
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        self.calendar = calendar if calendar is not None else []
        self.tags = fixtures.tags()
        self.key = key
        self.app = app
        self.poster_bytes: bytes = fixtures.JPEG
        self.fail_status: int | None = None  # answer every request with this status
        self.redirect_to: str | None = None  # answer every request with a 302 here
        self.delay = 0.0
        self.body_override: bytes | None = None
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.poster_requests = 0
        self._server = ThreadingHTTPServer((host, port), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> FakeArr:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _send(self, status: int, body: bytes, ctype: str, headers: dict[str, str] | None = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                parts = urlsplit(self.path)
                fake.requests.append((self.path, dict(self.headers)))
                if fake.delay:
                    time.sleep(fake.delay)
                if fake.redirect_to:
                    self._send(302, b"", "text/plain", {"Location": fake.redirect_to})
                    return
                if fake.fail_status:
                    self._send(fake.fail_status, b"{}", "application/json")
                    return
                if self.headers.get("X-Api-Key") != fake.key:
                    self._send(401, b"", "text/plain")
                    return
                if fake.body_override is not None:
                    self._send(200, fake.body_override, "application/json")
                    return
                if parts.path == "/api/v3/calendar":
                    query = parse_qs(parts.query)
                    data = fake.calendar
                    if query.get("unmonitored") == ["false"]:
                        data = [i for i in data if i.get("monitored")]
                    self._send(200, json.dumps(data).encode(), "application/json")
                elif parts.path == "/api/v3/tag":
                    self._send(200, json.dumps(fake.tags).encode(), "application/json")
                elif parts.path == "/api/v3/system/status":
                    body = json.dumps({"appName": fake.app, "version": "5.0.0.2907"}).encode()
                    self._send(200, body, "application/json")
                elif re.fullmatch(r"/api/v3/mediacover/\d+/poster-250\.jpg", parts.path):
                    fake.poster_requests += 1
                    self._send(200, fake.poster_bytes, "image/jpeg")
                else:
                    self._send(404, b"", "text/plain")

        return Handler


class Recorder:
    """Records every request it gets, and answers 200. Stands in for a redirect target or a
    proxy that must never be contacted."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                recorder.requests.append((self.path, dict(self.headers)))
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"[]")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
