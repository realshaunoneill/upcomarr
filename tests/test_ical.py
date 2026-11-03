import unittest
from datetime import UTC, date, datetime

from upcomarr import ical
from upcomarr.model import AIRS, EXPECTED, IN_CINEMAS, ON_PLEX, RELEASED, Entry
from upcomarr.schedule import Day, Schedule

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def entry(**kw):
    base = dict(
        kind="tv", title="Night Market", label="S01E01–E08", episode_title=None, count=8, on_plex_count=0,
        network="Channel 9", overview="A street-food stall, after dark.", date="2026-11-05", time="20:00",
        badge=AIRS, on_plex=False, expected_date=None, expected_via=None, cinema_date=None, poster=None,
        starts_at="2026-11-05T20:00:00+00:00", runtime=45,
    )  # fmt: skip
    base.update(kw)
    return Entry(**base)


def unfold(text):
    return text.replace("\r\n ", "")


class TextTest(unittest.TestCase):
    def test_escape(self):
        self.assertEqual(ical.escape("a, b; c\\d\nnext"), "a\\, b\\; c\\\\d\\nnext")
        self.assertEqual(ical.escape("crlf\r\nlf\rcr"), "crlf\\nlf\\ncr")

    def test_fold_keeps_lines_short_and_characters_whole(self):
        for text in ("x" * 300, "é" * 200, "Ünïcødé — " * 30, "🎬" * 60):
            with self.subTest(sample=text[:12]):
                folded = ical.fold("DESCRIPTION:" + text)
                for line in folded.split("\r\n"):
                    self.assertLessEqual(len(line.encode()), 75)
                self.assertEqual(unfold(folded), "DESCRIPTION:" + text)
        self.assertEqual(ical.fold("SHORT:yes"), "SHORT:yes")


class EventTest(unittest.TestCase):
    def test_timed_tv_event(self):
        text = ical.event(entry(), NOW, "0.3.0")
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"))
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))
        self.assertNotIn("\n\n", text.replace("\r\n", "\n\n").replace("\n\n", "\n"))  # only CRLF endings
        self.assertIn("\r\nDTSTART:20261105T200000Z\r\n", text)
        self.assertIn("\r\nDTEND:20261105T204500Z\r\n", text)  # 45-minute runtime
        self.assertIn("\r\nSUMMARY:Night Market S01E01–E08\r\n", unfold(text))
        self.assertIn("\r\nTRANSP:TRANSPARENT\r\n", text)
        self.assertIn("\r\nDTSTAMP:20261103T120000Z\r\n", text)

    def test_default_runtime_and_all_day_tv(self):
        self.assertIn("DTEND:20261105T210000Z", ical.event(entry(runtime=None), NOW, "x"))
        text = ical.event(entry(starts_at=None, time=None), NOW, "x")
        self.assertIn("DTSTART;VALUE=DATE:20261105", text)
        self.assertIn("DTEND;VALUE=DATE:20261106", text)

    def test_films(self):
        film = entry(kind="movie", title="The Odyssey", label="Movie (2026)", network="Universal", date="2026-11-17",
                     time=None, starts_at=None, runtime=None, badge=EXPECTED, expected_date="2026-11-17",
                     link="https://request.example.com/movie/1")  # fmt: skip
        text = unfold(ical.event(film, NOW, "x"))
        self.assertIn("DTSTART;VALUE=DATE:20261117", text)
        self.assertIn("SUMMARY:The Odyssey on Plex", text)
        self.assertIn("URL:https://request.example.com/movie/1", text)
        cinema = ical.event(
            film.__class__(**{**film.__dict__, "badge": IN_CINEMAS, "expected_date": "2026-12-20"}), NOW, "x"
        )
        self.assertIn("SUMMARY:The Odyssey in cinemas", unfold(cinema))
        self.assertIn("Expected on Plex from about 20 Dec", unfold(cinema))

    def test_uid_survives_a_date_change(self):
        self.assertEqual(
            ical.uid_hash(entry()), ical.uid_hash(entry(date="2026-11-12", starts_at="2026-11-12T20:00:00+00:00"))
        )
        self.assertNotEqual(ical.uid_hash(entry()), ical.uid_hash(entry(label="S01E09")))
        self.assertRegex(ical.path_for(entry()), r"^cal/[0-9a-f]{20}\.ics$")

    def test_untrusted_text_cannot_break_the_file(self):
        text = ical.event(entry(title="Evil\r\nEND:VEVENT\r\nBEGIN:VEVENT", overview="x;y,z\\"), NOW, "x")
        lines = unfold(text).split("\r\n")[:-1]
        # The injected text stays inside one escaped SUMMARY value: only real lines are structure.
        self.assertEqual([line for line in lines if line == "BEGIN:VEVENT"], ["BEGIN:VEVENT"])
        self.assertEqual([line for line in lines if line == "END:VEVENT"], ["END:VEVENT"])
        for line in lines:
            self.assertRegex(line, r"^[A-Z][A-Z-]*[:;]", "every line is a property")
        self.assertIn("SUMMARY:Evil\\nEND:VEVENT\\nBEGIN:VEVENT S01E01", unfold(text))


class AttachTest(unittest.TestCase):
    def test_only_cards_still_coming(self):
        cards = (
            entry(),
            entry(title="Done", badge=ON_PLEX, on_plex=True),
            entry(kind="movie", title="Out", label="Movie", badge=RELEASED),
            entry(kind="movie", title="Soon", label="Movie", badge=IN_CINEMAS),
        )
        sched = Schedule(date(2026, 11, 3), (Day(date(2026, 11, 5), "Thursday", "5 November", cards),), (entry(),))
        attached = ical.attach(sched, True)
        got = {e.title: e.calendar for e in attached.days[0].entries}
        self.assertIsNotNone(got["Night Market"])
        self.assertIsNone(got["Done"])
        self.assertIsNone(got["Out"])
        self.assertIsNotNone(got["Soon"])
        self.assertIsNone(attached.recent[0].calendar)
        self.assertIs(ical.attach(sched, False), sched)


if __name__ == "__main__":
    unittest.main()
