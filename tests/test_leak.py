"""End to end: a full run against fake arrs whose replies are full of canaries.

This is the test that matters most. The page is meant for people who must never learn
anything about the server beyond what is coming: no paths, no ids, no keys, no hosts.
"""

import json
import tempfile
import unittest
from pathlib import Path

from upcomarr.app import run_once
from upcomarr.config import load
from upcomarr.metrics import Registry
from upcomarr.publish import Layout

from . import fixtures
from .fakearr import FakeArr

# The complete set of keys allowed anywhere in upcoming.json. Changing the public data
# means changing this set too, on purpose.
ALLOWED_KEYS = {
    # top level
    "schema", "version", "title", "generated_at", "tz", "sources", "days", "recent",
    # sources
    "tv", "movies", "ok", "stale", "last_success",
    # days
    "date", "label", "entries",
    # entries
    "kind", "episode_title", "count", "on_plex_count", "network", "overview", "time", "badge",
    "on_plex", "expected_date", "expected_via", "cinema_date", "poster", "highlight", "trailer", "link",
}  # fmt: skip


def all_keys(value, found=None):
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            all_keys(v, found)
    elif isinstance(value, list):
        for v in value:
            all_keys(v, found)
    return found


class LeakTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.sonarr = FakeArr(fixtures.sonarr_calendar(), key=fixtures.API_KEY).__enter__()
        self.radarr = FakeArr(fixtures.radarr_calendar(), key=fixtures.OTHER_KEY, app="Radarr").__enter__()

    def tearDown(self):
        self.sonarr.__exit__()
        self.radarr.__exit__()
        self.tmp.cleanup()

    def config(self):
        return load(
            {
                "SONARR_URL": self.sonarr.url,
                "SONARR_API_KEY": fixtures.API_KEY,
                "RADARR_URL": self.radarr.url,
                "RADARR_API_KEY": fixtures.OTHER_KEY,
                "TZ": "Europe/Dublin",
                "OUT_DIR": str(self.out),
                "SEERR_URL": "https://request.example.com",
            }
        )

    def published(self):
        """Every file a viewer can fetch: the current build and the status file."""
        root = self.out / "current"
        files = [p for p in root.resolve().rglob("*") if p.is_file()]
        return [*files, self.out / "status.json"]

    def test_nothing_sensitive_is_published(self):
        registry = Registry()
        ok = run_once(self.config(), Layout(self.out), registry, now=fixtures.NOW)
        self.assertTrue(ok)
        line = next(
            x for x in registry.render().splitlines() if x.startswith("upcomarr_last_publish_timestamp_seconds ")
        )
        self.assertEqual(float(line.split()[1]), fixtures.NOW.timestamp())  # parsed back, at full precision
        forbidden = [
            "CANARY",
            fixtures.API_KEY,
            fixtures.OTHER_KEY,
            self.sonarr.url.split("//")[1],
            self.radarr.url.split("//")[1],
            "127.0.0.1",
            "/api/",
            "lastWrite",
            "MediaCover",
            "/data/",
            *(str(i) for i in fixtures.INTERNAL_IDS),
        ]
        checked = 0
        for path in self.published():
            rel = path.name
            data = path.read_bytes()
            text = "" if data.startswith(b"\xff\xd8\xff") else data.decode("utf-8")
            for needle in forbidden:
                self.assertNotIn(needle, text, f"{needle!r} in {rel}")
                self.assertNotIn(needle, rel, f"{needle!r} in the name {rel}")
            checked += 1
        self.assertGreater(checked, 6)

    def test_upcoming_json_keys_are_exactly_the_allowlist(self):
        run_once(self.config(), Layout(self.out), Registry(), now=fixtures.NOW)
        data = json.loads((self.out / "current" / "upcoming.json").read_text())
        self.assertLessEqual(all_keys(data), ALLOWED_KEYS)
        titles = {e["title"] for d in data["days"] for e in d["entries"]}
        self.assertEqual(
            titles,
            {"The Lighthouse Keepers", "Night Market", "Paper Moons", "The Last Ferry", "Signal Fires", "Orchard"},
        )
        self.assertEqual({e["title"] for e in data["recent"]}, {"Paper Moons", "Small Hours"})
        entries = {e["title"]: e for d in data["days"] for e in d["entries"]}
        # Valid ids become links; the canary trailer ids and finale types were rejected, not passed on.
        self.assertEqual(entries["The Last Ferry"]["trailer"], "https://www.youtube.com/watch?v=aBcDeFgHiJk")
        self.assertIsNone(entries["Signal Fires"]["trailer"])
        self.assertEqual(entries["The Last Ferry"]["link"], "https://request.example.com/movie/4440001")
        self.assertEqual(entries["Night Market"]["link"], "https://request.example.com/tv/610001")
        self.assertEqual(entries["The Lighthouse Keepers"]["highlight"], "season_finale")
        self.assertEqual(entries["Night Market"]["highlight"], "new_series")

    def test_private_state_is_outside_the_served_tree(self):
        run_once(self.config(), Layout(self.out), Registry(), now=fixtures.NOW)
        served = self.out / "current"
        self.assertFalse((served / ".state").exists())
        self.assertTrue((self.out / ".state" / "sonarr.json").is_file())

    def test_a_leak_fails_the_run_and_publishes_nothing(self):
        run_once(self.config(), Layout(self.out), Registry(), now=fixtures.NOW)
        before = (self.out / "current" / "index.html").read_text()
        # A series whose overview quotes its own folder: the allowlist passes the overview,
        # so only the leak check stands between that path and the page.
        show = fixtures.series(
            fixtures.SERIES_IDS[0], "Leaky", overview=f"/data/tv/CANARY-series-path-{fixtures.SERIES_IDS[0]}"
        )
        self.sonarr.calendar = [fixtures.episode(show, 1, 1, "2026-11-04T20:00:00Z")]
        registry = Registry()
        ok = run_once(self.config(), Layout(self.out), registry, now=fixtures.NOW)
        self.assertFalse(ok)
        self.assertEqual((self.out / "current" / "index.html").read_text(), before)
        metrics = registry.render()
        self.assertIn("upcomarr_last_publish_success 0", metrics)
        self.assertIn('upcomarr_source_up{source="sonarr"} 1', metrics)  # the fetch itself was fine
        self.assertNotIn("upcomarr_last_publish_timestamp_seconds", metrics)
        status = json.loads((self.out / "status.json").read_text())
        self.assertEqual((status["ok"], status["error"]), (False, "leak"))

    def test_one_arr_down_keeps_its_last_data(self):
        run_once(self.config(), Layout(self.out), Registry(), now=fixtures.NOW)
        self.sonarr.fail_status = 503
        ok = run_once(self.config(), Layout(self.out), Registry(), now=fixtures.NOW)
        self.assertFalse(ok)
        status = json.loads((self.out / "status.json").read_text())
        self.assertEqual(
            status["sources"]["tv"],
            {
                "ok": False,
                "stale": True,
                "last_success": fixtures.NOW.isoformat(timespec="seconds"),
                "error": "http_503",
            },
        )
        self.assertTrue(status["sources"]["movies"]["ok"])
        page = (self.out / "current" / "index.html").read_text()
        self.assertIn("The Lighthouse Keepers", page)
        self.assertIn("could not be refreshed", page)


if __name__ == "__main__":
    unittest.main()
