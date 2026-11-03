"""Prometheus metrics on METRICS_PORT, path /metrics only.

The generator holds the arr keys, so this listener serves numbers and nothing else: no
labels besides the source name and entry kind, no error text.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Registry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._gauges: dict[str, tuple[str, dict[tuple[tuple[str, str], ...], float]]] = {}

    def set(self, name: str, help_text: str, value: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            _, series = self._gauges.setdefault(name, (help_text, {}))
            series[key] = float(value)

    def render(self) -> str:
        lines = []
        with self._lock:
            for name in sorted(self._gauges):
                help_text, series = self._gauges[name]
                lines.append(f"# HELP {name} {help_text}")
                lines.append(f"# TYPE {name} gauge")
                for labels, value in sorted(series.items()):
                    label_text = ",".join(f'{k}="{v}"' for k, v in labels)
                    suffix = f"{{{label_text}}}" if label_text else ""
                    lines.append(f"{name}{suffix} {value:g}")
        return "\n".join(lines) + "\n"


def serve(registry: Registry, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "upcomarr"
        sys_version = ""

        def do_GET(self) -> None:
            if self.path != "/metrics":
                self.send_error(404)
                return
            body = registry.render().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass  # scrapes every 30 s would drown the real log

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104 - the point is to be scraped
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="metrics", daemon=True).start()
    return server
