import unittest
from datetime import UTC, date, datetime

from upcomarr import tags
from upcomarr.http import Client, FetchError
from upcomarr.sources import collect_sensitive, radarr, sonarr

from . import fixtures
from .fakearr import FakeArr


class SonarrTest(unittest.TestCase):
    def test_projection(self):
        show = fixtures.series(fixtures.SERIES_IDS[0], "Keepers\u202e evil", tags=(2,))
        ep = sonarr.project(fixtures.episode(show, 2, 5, "2026-11-03T21:00:00Z"), False, None)
        self.assertEqual(ep.series_id, fixtures.SERIES_IDS[0])
        self.assertEqual(ep.series_title, "Keepers evil")  # bidi override stripped
        self.assertEqual((ep.season, ep.episode), (2, 5))
        self.assertEqual(ep.air_utc, datetime(2026, 11, 3, 21, 0, tzinfo=UTC))
        self.assertEqual(ep.poster.version, "638987000000000000")
        self.assertEqual(ep.series_overview, "About Keepers evil.")

    def test_drops_unmonitored_and_malformed(self):
        show = fixtures.series(1, "Show")
        self.assertIsNone(
            sonarr.project(fixtures.episode(show, 1, 1, "2026-11-03T21:00:00Z", monitored=False), False, None)
        )
        self.assertIsNotNone(
            sonarr.project(fixtures.episode(show, 1, 1, "2026-11-03T21:00:00Z", monitored=False), True, None)
        )
        broken = fixtures.episode(show, 1, 1, None)
        broken["airDate"] = None
        self.assertIsNone(sonarr.project(broken, False, None))
        self.assertIsNone(sonarr.project({"series": "nope"}, False, None))
        self.assertIsNone(sonarr.project(["not", "a", "dict"], False, None))
        wrong_type = fixtures.episode(show, 1, 1, "2026-11-03T21:00:00Z")
        wrong_type["seasonNumber"] = "1"
        self.assertIsNone(sonarr.project(wrong_type, False, None))

    def test_tag_filter(self):
        tagged = fixtures.series(1, "Tagged", tags=(2,))
        plain = fixtures.series(2, "Plain")
        self.assertIsNotNone(
            sonarr.project(fixtures.episode(tagged, 1, 1, "2026-11-03T21:00:00Z"), False, frozenset({2}))
        )
        self.assertIsNone(sonarr.project(fixtures.episode(plain, 1, 1, "2026-11-03T21:00:00Z"), False, frozenset({2})))

    def test_fetch_collects_paths(self):
        with FakeArr(fixtures.sonarr_calendar()) as arr:
            client = Client(arr.url, fixtures.API_KEY, 5)
            episodes, sensitive = sonarr.fetch(client, date(2026, 10, 30), date(2027, 1, 3), False, ())
            self.assertEqual(len(episodes), 11)
            self.assertIn(f"/data/tv/CANARY-series-path-{fixtures.SERIES_IDS[0]}", sensitive)
            query = arr.requests[0][0]
            self.assertIn("includeSeries=true", query)
            self.assertIn("unmonitored=false", query)


class RadarrTest(unittest.TestCase):
    def test_dates_are_days(self):
        raw = fixtures.movie(1, "Film", cinema="2026-11-14", digital="2026-12-01", has_file=True, added="2026-11-02")
        m = radarr.project(raw, False, None)
        self.assertEqual(m.cinema, date(2026, 11, 14))
        self.assertEqual(m.digital, date(2026, 12, 1))
        self.assertIsNone(m.physical)
        self.assertTrue(m.has_file)
        self.assertEqual(m.file_added, date(2026, 11, 2))
        self.assertEqual(m.studio, "Tidewater Pictures")

    def test_collects_file_paths(self):
        found = collect_sensitive(fixtures.movie(7, "Film", has_file=True, added="2026-11-01"))
        self.assertIn("/data/movies/CANARY-file-7.mkv", found)
        self.assertIn("CANARY-relative-7.mkv", found)
        self.assertIn("/data/movies/CANARY-folder-7", found)

    def test_unmonitored(self):
        self.assertIsNone(radarr.project(fixtures.movie(1, "Film", monitored=False), False, None))


class TagsTest(unittest.TestCase):
    def test_resolves_case_insensitively(self):
        with FakeArr() as arr:
            client = Client(arr.url, fixtures.API_KEY, 5)
            self.assertIsNone(tags.resolve(client, "v3", ()))
            self.assertEqual(tags.resolve(client, "v3", ("shared", "kids")), frozenset({1, 2}))

    def test_unknown_label_fails_closed(self):
        with FakeArr() as arr:
            client = Client(arr.url, fixtures.API_KEY, 5)
            with self.assertRaises(FetchError) as ctx:
                tags.resolve(client, "v3", ("kids", "nope"))
            self.assertEqual(ctx.exception.code, "tag_not_found")


if __name__ == "__main__":
    unittest.main()
