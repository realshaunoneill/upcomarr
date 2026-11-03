import os
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from upcomarr import __main__ as cli
from upcomarr.config import load
from upcomarr.metrics import Registry, serve
from upcomarr.publish import Layout

from . import fixtures


class HealthcheckTest(unittest.TestCase):
    def test_heartbeat_age(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"OUT_DIR": d}):
            layout = Layout(Path(d))
            self.assertEqual(cli.cmd_healthcheck(), 1)  # no heartbeat yet
            layout.ensure()
            layout.heartbeat.touch()
            self.assertEqual(cli.cmd_healthcheck(), 0)
            old = time.time() - cli.HEARTBEAT_STALE - 5
            os.utime(layout.heartbeat, (old, old))
            self.assertEqual(cli.cmd_healthcheck(), 1)


class ScheduleLoopTest(unittest.TestCase):
    def test_runs_just_after_local_midnight(self):
        cfg = load({"SONARR_URL": "http://s", "SONARR_API_KEY": "k", "TZ": "Europe/Dublin", "INTERVAL_SECONDS": "1800"})
        # 23:50 GMT: midnight is 10 minutes away, so the next run is at 00:01.
        self.assertEqual(cli._seconds_until_next_run(cfg, datetime(2026, 11, 3, 23, 50, tzinfo=UTC)), 660)
        self.assertEqual(cli._seconds_until_next_run(cfg, datetime(2026, 11, 3, 12, 0, tzinfo=UTC)), 1800)


class DemoTest(unittest.TestCase):
    def test_demo_renders(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cli.cmd_demo(Path(d)), 0)
            html = (Path(d) / "current" / "index.html").read_text()
            self.assertIn("Night Market", html)


class ProbeTest(unittest.TestCase):
    def test_probe_prints_no_secret(self):
        from .fakearr import FakeArr

        with FakeArr() as arr, mock.patch("builtins.print") as printed:
            cfg = load({"SONARR_URL": arr.url, "SONARR_API_KEY": fixtures.API_KEY})
            self.assertEqual(cli.cmd_probe(cfg), 0)
            output = " ".join(str(c.args) for c in printed.call_args_list)
            self.assertIn("reached Sonarr", output)
            self.assertNotIn(fixtures.API_KEY, output)


class MetricsTest(unittest.TestCase):
    def test_render_and_serve(self):
        registry = Registry()
        registry.set("upcomarr_source_up", "help", 1, source="sonarr")
        registry.set("upcomarr_last_run_success", "help", 0)
        text = registry.render()
        self.assertIn('upcomarr_source_up{source="sonarr"} 1', text)
        self.assertIn("# TYPE upcomarr_last_run_success gauge", text)
        server = serve(registry, 0)
        try:
            port = server.server_address[1]
            body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5).read().decode()
            self.assertIn("upcomarr_source_up", body)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5)
            self.assertEqual(ctx.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
