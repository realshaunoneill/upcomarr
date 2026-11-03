import hashlib
import tempfile
import unittest
from pathlib import Path

from upcomarr.http import Client
from upcomarr.model import PosterRef
from upcomarr.posters import PosterCache

from . import fixtures
from .fakearr import FakeArr


class PosterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache_dir = self.root / "posters"
        self.state = self.root / "posters.json"

    def tearDown(self):
        self.tmp.cleanup()

    def cache(self):
        return PosterCache(self.cache_dir, self.state)

    def test_fetch_name_and_reuse(self):
        with FakeArr() as arr:
            clients = {"sonarr": Client(arr.url, fixtures.API_KEY, 5)}
            ref = PosterRef("sonarr", fixtures.SERIES_IDS[0], "v1")
            names = self.cache().sync([ref], clients)
            want = hashlib.sha256(fixtures.JPEG).hexdigest()[:16] + ".jpg"
            self.assertEqual(names, {ref.key: want})
            self.assertTrue((self.cache_dir / want).is_file())
            self.assertNotIn(str(fixtures.SERIES_IDS[0]), want)
            self.assertIn(f"/api/v3/mediacover/{fixtures.SERIES_IDS[0]}/poster-250.jpg", arr.requests[0][0])
            self.cache().sync([ref], clients)
            self.assertEqual(arr.poster_requests, 1)  # unchanged version: not fetched again
            self.cache().sync([PosterRef("sonarr", fixtures.SERIES_IDS[0], "v2")], clients)
            self.assertEqual(arr.poster_requests, 2)

    def test_failure_keeps_the_old_file(self):
        with FakeArr() as arr:
            clients = {"sonarr": Client(arr.url, fixtures.API_KEY, 5)}
            first = self.cache().sync([PosterRef("sonarr", 1, "v1")], clients)
            arr.fail_status = 500
            again = self.cache().sync([PosterRef("sonarr", 1, "v2")], clients)
            self.assertEqual(first, again)

    def test_rejects_non_images(self):
        with FakeArr() as arr:
            arr.poster_bytes = b"<html>login page</html>"
            names = self.cache().sync([PosterRef("radarr", 1, "v")], {"radarr": Client(arr.url, fixtures.API_KEY, 5)})
            self.assertEqual(names, {})

    def test_prunes_unused(self):
        with FakeArr() as arr:
            clients = {"sonarr": Client(arr.url, fixtures.API_KEY, 5)}
            self.cache().sync([PosterRef("sonarr", 1, "v")], clients)
            arr.poster_bytes = fixtures.PNG
            self.cache().sync([PosterRef("sonarr", 2, "v")], clients)
            files = sorted(p.suffix for p in self.cache_dir.iterdir())
            self.assertEqual(files, [".png"])


if __name__ == "__main__":
    unittest.main()
