import os
import stat
import tempfile
import unittest
from pathlib import Path

from upcomarr import leakcheck
from upcomarr.publish import KEEP_BUILDS, Layout, prune, publish


def write(text):
    def build(target: Path) -> None:
        (target / "index.html").write_text(text)

    return build


def no_check(_: Path) -> None:
    pass


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout = Layout(Path(self.tmp.name))
        self.layout.ensure()
        self.old_umask = os.umask(0o022)

    def tearDown(self):
        os.umask(self.old_umask)
        self.tmp.cleanup()

    def current_text(self):
        return (self.layout.current / "index.html").read_text()

    def test_relative_symlink_and_modes(self):
        build_id = publish(self.layout, write("one"), no_check)
        target = os.readlink(self.layout.current)
        self.assertFalse(os.path.isabs(target))
        self.assertEqual(target, os.path.join("builds", build_id))
        self.assertEqual(self.current_text(), "one")
        mode = stat.S_IMODE((self.layout.current / "index.html").stat().st_mode)
        self.assertEqual(mode, 0o644)
        self.assertEqual(stat.S_IMODE(self.layout.current.resolve().stat().st_mode), 0o755)

    def test_failed_build_or_check_leaves_current(self):
        publish(self.layout, write("good"), no_check)

        def broken(target: Path) -> None:
            (target / "index.html").write_text("half")
            raise OSError("disk full")

        with self.assertRaises(OSError):
            publish(self.layout, broken, no_check)
        self.assertEqual(self.current_text(), "good")

        def leaky(_: Path) -> None:
            raise leakcheck.LeakError("api key in index.html")

        with self.assertRaises(leakcheck.LeakError):
            publish(self.layout, write("bad"), leaky)
        self.assertEqual(self.current_text(), "good")
        leftovers = [p.name for p in self.layout.builds.iterdir() if p.name.endswith(".partial")]
        self.assertEqual(leftovers, [])

    def test_prune_keeps_newest_and_current(self):
        ids = [publish(self.layout, write(str(i)), no_check) for i in range(KEEP_BUILDS + 3)]
        names = sorted(p.name for p in self.layout.builds.iterdir())
        self.assertEqual(names, sorted(ids[-KEEP_BUILDS:]))
        # Point current at an old build by hand: prune must not remove it.
        os.remove(self.layout.current)
        os.symlink(os.path.join("builds", ids[-KEEP_BUILDS]), self.layout.current)
        publish(self.layout, write("new"), no_check)
        prune(self.layout)
        self.assertTrue((self.layout.builds / os.path.basename(os.readlink(self.layout.current))).is_dir())

    def test_prune_ignores_foreign_names(self):
        (self.layout.builds / "keep-me").mkdir()
        for i in range(KEEP_BUILDS + 2):
            publish(self.layout, write(str(i)), no_check)
        self.assertTrue((self.layout.builds / "keep-me").is_dir())


class LeakScanTest(unittest.TestCase):
    def test_finds_needles_in_content_and_names(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            needles = leakcheck.needles_for(["SECRETKEY123"], ["http://sonarr.lan:8989"], ["/data/tv/Show"])
            (root / "ok.html").write_text("nothing to see")
            leakcheck.scan(root, needles)
            for name, text in [
                ("a.html", "key SECRETKEY123"),
                ("b.json", '{"p": "/DATA/tv/show"}'),
                ("c.html", "see http://sonarr.lan:8989/x"),
                ("d.html", "/MediaCover/1/poster.jpg"),
            ]:
                with self.subTest(name=name):
                    (root / name).write_text(text)
                    with self.assertRaises(leakcheck.LeakError) as ctx:
                        leakcheck.scan(root, needles)
                    self.assertNotIn("SECRETKEY123", str(ctx.exception))
                    (root / name).unlink()
            (root / "SECRETKEY123.txt").write_text("x")
            with self.assertRaises(leakcheck.LeakError):
                leakcheck.scan(root, needles)


if __name__ == "__main__":
    unittest.main()
