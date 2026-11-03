"""upcomarr command line.

python -m upcomarr run          refresh every INTERVAL_SECONDS, and just after local midnight
python -m upcomarr once         one run, then exit (0 = every source fetched and published)
python -m upcomarr healthcheck  exit 0 if the run loop is alive (for Docker's HEALTHCHECK)
python -m upcomarr probe        check the configuration and reach each arr; prints no secrets
python -m upcomarr demo         render a site from built-in sample data into OUT_DIR
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import __version__
from .app import run_once
from .config import Config, ConfigError, load
from .http import Client, FetchError
from .metrics import Registry, serve
from .publish import Layout

HEARTBEAT_SECONDS = 30
HEARTBEAT_STALE = 180
log = logging.getLogger("upcomarr")


def _seconds_until_next_run(cfg: Config, now: datetime) -> float:
    """The interval, or sooner if local midnight comes first: "Today" must be right."""
    local = now.astimezone(cfg.tz)
    midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), cfg.tz)
    after_midnight = (midnight.astimezone(UTC) - now).total_seconds() + 60
    return max(1.0, min(cfg.interval_seconds, after_midnight))


def cmd_run(cfg: Config) -> int:
    layout = Layout(cfg.out_dir)
    layout.ensure()
    registry = Registry()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    if cfg.metrics_port:
        serve(registry, cfg.metrics_port)
    log.info("upcomarr %s: %s, every %ds", __version__, ", ".join(s.name for s in cfg.sources), cfg.interval_seconds)
    while not stop.is_set():
        layout.heartbeat.touch()
        try:
            run_once(cfg, layout, registry)
        except Exception:
            log.exception("run crashed")
            registry.set("upcomarr_last_run_success", "1 if the last run fetched every source and published.", 0)
        deadline = time.monotonic() + _seconds_until_next_run(cfg, datetime.now(UTC))
        while not stop.is_set() and (remaining := deadline - time.monotonic()) > 0:
            layout.heartbeat.touch()
            stop.wait(min(HEARTBEAT_SECONDS, remaining))
    log.info("stopping")
    return 0


def cmd_once(cfg: Config) -> int:
    return 0 if run_once(cfg, Layout(cfg.out_dir), Registry()) else 1


def cmd_healthcheck() -> int:
    beat = Layout(Path(os.environ.get("OUT_DIR", "/out"))).heartbeat
    try:
        age = time.time() - beat.stat().st_mtime
    except OSError:
        return 1
    return 0 if age < HEARTBEAT_STALE else 1


def cmd_probe(cfg: Config) -> int:
    failed = False
    print(f"upcomarr {__version__}; TZ {cfg.tz_name}; output {cfg.out_dir}")
    for src in cfg.sources:
        upper = src.name.upper()
        print(f"{src.name}: {upper}_URL set, {upper}_API_KEY set, {src.days_ahead} days ahead")
        try:
            status = Client(src.url, src.api_key, cfg.request_timeout).get_json("/api/v3/system/status")
            name = status.get("appName", "?") if isinstance(status, dict) else "?"
            version = status.get("version", "?") if isinstance(status, dict) else "?"
            print(f"  reached {name} {version}")
        except FetchError as e:
            failed = True
            print(f"  FAILED: {e.code}")
    return 1 if failed else 0


def cmd_demo(out_dir: Path) -> int:
    from .demo import render_demo

    render_demo(Layout(out_dir))
    print(f"demo site written to {out_dir / 'current'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="upcomarr", description="Coming soon, from Sonarr and Radarr.")
    parser.add_argument("command", choices=("run", "once", "healthcheck", "probe", "demo"))
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    os.umask(0o022)

    if args.command == "healthcheck":
        return cmd_healthcheck()
    if args.command == "demo":
        return cmd_demo(Path(os.environ.get("OUT_DIR", "/out")))
    try:
        cfg = load(os.environ)
    except ConfigError as e:
        print(f"upcomarr: configuration error: {e}", file=sys.stderr)
        return 2
    return {"run": cmd_run, "once": cmd_once, "probe": cmd_probe}[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
