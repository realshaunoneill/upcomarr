"""A deliberately narrow HTTP client for the arr APIs.

Three things urllib does by default would leak or weaken the API key, so each is turned off:

- **Redirects.** urllib's redirect handler copies every header, the key included, to the new
  URL whatever its host. Here any 3xx is an error, and the key is attached as an
  "unredirected" header besides.
- **Proxies from the environment.** `HTTP(S)_PROXY` would route the key through a proxy
  nobody configured for this app.
- **Unbounded reads.** urllib's timeout applies to each socket read, so a server trickling
  bytes can hold a request open forever. Reads here share one deadline and a size cap.

Errors carry a short code and nothing else: no URL, no exception text.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import __version__

MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_IMAGE_BYTES = 4 * 1024 * 1024
_CHUNK = 64 * 1024


class FetchError(Exception):
    """A request failed. `code` is safe to log, publish and put in a metric label."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FetchError("redirect")


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RefuseRedirects(),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
    )


class Client:
    def __init__(self, base_url: str, api_key: str, timeout: float):
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._timeout = timeout
        self._opener = _opener()

    def __repr__(self) -> str:  # never show the key
        return f"Client({self._base!r})"

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        body, _ = self._get(path, params, "application/json", MAX_JSON_BYTES)
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise FetchError("bad_json") from None

    def get_bytes(self, path: str, max_bytes: int = MAX_IMAGE_BYTES) -> tuple[bytes, str]:
        return self._get(path, None, "image/*", max_bytes)

    def _get(self, path: str, params: dict[str, Any] | None, accept: str, max_bytes: int) -> tuple[bytes, str]:
        url = self._base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": f"upcomarr/{__version__}"})
        req.add_unredirected_header("X-Api-Key", self._key)
        deadline = time.monotonic() + self._timeout
        try:
            with self._opener.open(req, timeout=self._timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                chunks, size = [], 0
                while True:
                    if time.monotonic() > deadline:
                        raise FetchError("timeout")
                    # read1 returns after at most one socket read, so the deadline is checked
                    # between reads; each read is bounded by the socket timeout.
                    chunk = resp.read1(_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError("too_large")
                    chunks.append(chunk)
                return b"".join(chunks), ctype
        except FetchError:
            raise
        except urllib.error.HTTPError as e:
            raise FetchError(f"http_{e.code}") from None
        except urllib.error.URLError as e:
            reason = e.reason
            if isinstance(reason, FetchError):
                raise reason from None
            if isinstance(reason, ssl.SSLError):
                raise FetchError("tls") from None
            if isinstance(reason, TimeoutError):
                raise FetchError("timeout") from None
            raise FetchError("connect") from None
        except TimeoutError:
            raise FetchError("timeout") from None
        except ssl.SSLError:
            raise FetchError("tls") from None
        except (ConnectionError, OSError):
            raise FetchError("connect") from None
