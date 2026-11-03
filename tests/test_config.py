import tempfile
import unittest
from pathlib import Path

from upcomarr.config import ConfigError, load

from . import fixtures

BASE = {"SONARR_URL": "http://sonarr:8989/", "SONARR_API_KEY": fixtures.API_KEY}


class ConfigTest(unittest.TestCase):
    def test_minimal(self):
        cfg = load(BASE)
        self.assertEqual([s.name for s in cfg.sources], ["sonarr"])
        self.assertEqual(cfg.sources[0].url, "http://sonarr:8989")
        self.assertEqual(cfg.sources[0].days_ahead, 60)
        self.assertEqual(cfg.tz_name, "UTC")
        self.assertEqual(cfg.metrics_port, 0)
        self.assertFalse(cfg.include_unmonitored)

    def test_needs_a_source(self):
        with self.assertRaises(ConfigError):
            load({})

    def test_url_and_key_together(self):
        with self.assertRaises(ConfigError):
            load({"RADARR_URL": "http://radarr:7878"})
        with self.assertRaises(ConfigError):
            load({"RADARR_API_KEY": "x"})

    def test_key_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "key"
            path.write_text(fixtures.API_KEY + "\n")
            cfg = load({"RADARR_URL": "https://radarr.example", "RADARR_API_KEY_FILE": str(path)})
            self.assertEqual(cfg.sources[0].api_key, fixtures.API_KEY)
            with self.assertRaises(ConfigError):
                load({**BASE, "SONARR_API_KEY_FILE": str(path)})

    def test_missing_key_file_does_not_crash(self):
        with self.assertRaises(ConfigError):
            load({"SONARR_URL": "http://s", "SONARR_API_KEY_FILE": "/nonexistent/key"})

    def test_rejects_unsafe_urls(self):
        for url in ("ftp://sonarr", "sonarr:8989", "http://user:pass@sonarr", "http://sonarr/?apikey=x", "http://"):
            with self.subTest(url=url), self.assertRaises(ConfigError):
                load({"SONARR_URL": url, "SONARR_API_KEY": "k"})

    def test_keeps_a_base_path(self):
        cfg = load({"SONARR_URL": "https://example.com/sonarr/", "SONARR_API_KEY": "k"})
        self.assertEqual(cfg.sources[0].url, "https://example.com/sonarr")

    def test_key_is_not_in_repr_or_errors(self):
        cfg = load(BASE)
        self.assertNotIn(fixtures.API_KEY, repr(cfg))
        with self.assertRaises(ConfigError) as ctx:
            load({**BASE, "SONARR_DAYS_AHEAD": "lots"})
        self.assertNotIn(fixtures.API_KEY, str(ctx.exception))

    def test_bounds_and_types(self):
        with self.assertRaises(ConfigError):
            load({**BASE, "INTERVAL_SECONDS": "5"})
        with self.assertRaises(ConfigError):
            load({**BASE, "INCLUDE_UNMONITORED": "maybe"})
        with self.assertRaises(ConfigError):
            load({**BASE, "TZ": "Mars/Olympus_Mons"})
        cfg = load({**BASE, "TZ": "Europe/Dublin", "INCLUDE_UNMONITORED": "yes", "SONARR_TAGS": " Kids, shared ,"})
        self.assertEqual(cfg.tz_name, "Europe/Dublin")
        self.assertTrue(cfg.include_unmonitored)
        self.assertEqual(cfg.sources[0].tags, ("kids", "shared"))


if __name__ == "__main__":
    unittest.main()
