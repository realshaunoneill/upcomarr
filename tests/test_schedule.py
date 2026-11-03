import unittest
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from upcomarr import schedule
from upcomarr.model import EXPECTED, IN_CINEMAS, ON_PLEX, PARTIAL, RELEASED, Episode, Links, Movie, PosterRef

DUBLIN = ZoneInfo("Europe/Dublin")
LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def ep(
    season,
    number,
    air_utc=None,
    air_date=None,
    has_file=False,
    series_id=1,
    title="Show",
    ep_title=None,
    finale=None,
    tmdb=None,
):
    return Episode(
        series_id,
        title,
        "Net",
        "About.",
        season,
        number,
        ep_title,
        air_utc,
        air_date,
        has_file,
        PosterRef("sonarr", series_id, "v1"),
        tmdb=tmdb,
        finale=finale,
    )


def mv(**kw):
    base = dict(
        movie_id=1,
        title="Film",
        year=2026,
        studio="Studio",
        overview="About.",
        cinema=None,
        digital=None,
        physical=None,
        has_file=False,
        file_added=None,
        poster=None,
    )
    base.update(kw)
    return Movie(**base)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


class LabelTest(unittest.TestCase):
    def test_labels(self):
        cases = [
            ([(2, 5)], "S02E05"),
            ([(2, n) for n in range(1, 9)], "S02E01–E08"),
            ([(2, 1), (2, 2), (2, 3), (2, 5)], "S02E01–E03, E05"),
            ([(1, 10), (2, 1)], "S01E10, S02E01"),
            ([(0, 3)], "Special"),
            ([(0, 3), (0, 4)], "2 specials"),
            ([(3, 100)], "S03E100"),
        ]
        for pairs, want in cases:
            with self.subTest(want=want):
                self.assertEqual(schedule.episode_label([ep(s, n) for s, n in pairs]), want)


class TvTest(unittest.TestCase):
    def build(self, episodes, tz=DUBLIN, now=NOW, behind=3):
        return schedule.build(episodes, [], now, tz, behind, 60, 90, {"sonarr:1": "abc.jpg"})

    def test_same_day_collapses(self):
        sched = self.build([ep(1, n, utc(2026, 11, 5, 20)) for n in range(1, 9)])
        (day,) = sched.days
        (entry,) = day.entries
        self.assertEqual(entry.label, "S01E01–E08")
        self.assertEqual(entry.count, 8)
        self.assertIsNone(entry.episode_title)
        self.assertEqual(entry.poster, "abc.jpg")
        self.assertEqual(day.heading, "Thursday")
        self.assertEqual(day.date_text, "5 November")

    def test_us_prime_time_lands_next_day_in_dublin(self):
        # 20:00 Eastern on 3 Nov is 01:00 UTC on 4 Nov.
        sched = self.build([ep(1, 1, utc(2026, 11, 4, 1, 0))])
        entry = sched.days[0].entries[0]
        self.assertEqual((entry.date, entry.time), ("2026-11-04", "01:00"))
        self.assertEqual(sched.days[0].heading, "Tomorrow")
        sched = self.build([ep(1, 1, utc(2026, 11, 4, 1, 0))], tz=LA)
        entry = sched.days[0].entries[0]
        self.assertEqual((entry.date, entry.time), ("2026-11-03", "17:00"))
        self.assertEqual(sched.days[0].heading, "Today")

    def test_dst_changes_in_dublin(self):
        # Clocks go back at 02:00 IST on 2026-10-25, forward at 01:00 GMT on 2027-03-28.
        cases = [
            (utc(2026, 10, 24, 23, 30), "2026-10-25", "00:30"),  # IST, UTC+1
            (utc(2026, 10, 25, 1, 30), "2026-10-25", "01:30"),  # GMT
            (utc(2027, 3, 28, 0, 30), "2027-03-28", "00:30"),  # GMT
            (utc(2027, 3, 28, 1, 30), "2027-03-28", "02:30"),  # IST
        ]
        for air, want_date, want_time in cases:
            with self.subTest(air=air):
                now = air - timedelta(hours=12)
                entry = self.build([ep(1, 1, air)], now=now).days[0].entries[0]
                self.assertEqual((entry.date, entry.time), (want_date, want_time))

    def test_all_day_episode(self):
        entry = self.build([ep(1, 1, None, date(2026, 11, 6))]).days[0].entries[0]
        self.assertEqual((entry.date, entry.time), ("2026-11-06", None))

    def test_past_without_file_is_dropped_and_with_file_is_recent(self):
        sched = self.build([ep(1, 1, utc(2026, 11, 1, 20)), ep(1, 2, utc(2026, 11, 2, 20), has_file=True, series_id=2)])
        self.assertEqual(sched.days, ())
        (recent,) = sched.recent
        self.assertEqual((recent.label, recent.badge, recent.on_plex), ("S01E02", ON_PLEX, True))

    def test_outside_window(self):
        sched = self.build([ep(1, 1, utc(2026, 10, 20, 20), has_file=True), ep(1, 2, utc(2027, 2, 1, 20))])
        self.assertEqual((sched.days, sched.recent), ((), ()))

    def test_partial_today(self):
        sched = self.build([ep(1, 1, utc(2026, 11, 3, 6), has_file=True), ep(1, 2, utc(2026, 11, 3, 6))])
        entry = sched.days[0].entries[0]
        self.assertEqual((entry.badge, entry.on_plex_count, entry.count, entry.on_plex), (PARTIAL, 1, 2, False))

    def test_placeholder_titles_hidden(self):
        entry = self.build([ep(1, 1, utc(2026, 11, 5, 20), ep_title="TBA")]).days[0].entries[0]
        self.assertIsNone(entry.episode_title)
        entry = self.build([ep(1, 1, utc(2026, 11, 5, 20), ep_title="The Storm")]).days[0].entries[0]
        self.assertEqual(entry.episode_title, "The Storm")


class MovieTest(unittest.TestCase):
    today = date(2026, 11, 3)

    def place(self, **kw):
        return schedule.place_movie(mv(**kw), self.today, 3, 90)

    def d(self, offset):
        return self.today + timedelta(days=offset)

    def test_placement(self):
        d = self.d
        cases = [
            (dict(digital=d(10)), (d(10), EXPECTED, d(10), "digital")),
            (dict(digital=d(-1)), (d(0), RELEASED, d(-1), "digital")),
            (dict(digital=d(-60), physical=d(20)), (d(20), EXPECTED, d(20), "physical")),
            (dict(cinema=d(5)), (d(5), IN_CINEMAS, None, None)),
            (dict(cinema=d(5), digital=d(120)), (d(5), IN_CINEMAS, d(120), "digital")),
            (dict(cinema=d(-10), digital=d(-60)), None),
            (dict(digital=d(200)), None),
        ]
        for kw, want in cases:
            with self.subTest(kw=kw):
                self.assertEqual(self.place(**kw), want)

    def test_files_only_in_recent(self):
        movies = [
            mv(movie_id=1, title="New", digital=self.d(-30), physical=self.d(5), has_file=True, file_added=self.d(-1)),
            mv(movie_id=2, title="Old", physical=self.d(5), has_file=True, file_added=self.d(-100)),
        ]
        sched = schedule.build([], movies, NOW, DUBLIN, 3, 60, 90, {})
        self.assertEqual(sched.days, ())
        self.assertEqual([e.title for e in sched.recent], ["New"])

    def test_dates_not_shifted_by_timezone(self):
        sched = schedule.build([], [mv(digital=date(2026, 11, 14))], NOW, LA, 3, 60, 90, {})
        self.assertEqual(sched.days[0].entries[0].date, "2026-11-14")

    def test_overview_trimmed(self):
        sched = schedule.build([], [mv(digital=self.d(2), overview="word " * 400)], NOW, DUBLIN, 3, 60, 90, {})
        overview = sched.days[0].entries[0].overview
        self.assertLessEqual(len(overview), schedule.OVERVIEW_LIMIT + 1)
        self.assertTrue(overview.endswith("…"))

    def test_sorting_tv_before_movies_by_time(self):
        sched = schedule.build(
            [ep(1, 1, utc(2026, 11, 5, 21), title="Late"), ep(1, 1, utc(2026, 11, 5, 19), series_id=2, title="Early")],
            [mv(digital=date(2026, 11, 5), title="A film")],
            NOW,
            DUBLIN,
            3,
            60,
            90,
            {},
        )
        self.assertEqual([e.title for e in sched.days[0].entries], ["Early", "Late", "A film"])


class HighlightTest(unittest.TestCase):
    def test_rules(self):
        cases = [
            ([ep(1, 1)], "new_series"),
            ([ep(3, 1)], "season_premiere"),
            ([ep(3, 4)], None),
            ([ep(3, 9, finale="midseason")], "midseason_finale"),
            ([ep(3, 10, finale="season")], "season_finale"),
            ([ep(5, 12, finale="series")], "series_finale"),
            ([ep(2, n, finale="season" if n == 8 else None) for n in range(1, 9)], "full_season"),
            ([ep(1, n, finale="series" if n == 6 else None) for n in range(1, 7)], "new_series_full"),
            ([ep(0, 1)], None),  # specials never
            ([ep(0, 1, finale="season")], None),
        ]
        for eps, want in cases:
            with self.subTest(want=want, eps=[(e.season, e.episode, e.finale) for e in eps]):
                self.assertEqual(schedule.highlight(eps), want)

    def test_highlight_reaches_the_entry(self):
        sched = schedule.build([ep(2, 10, utc(2026, 11, 5, 20), finale="season")], [], NOW, DUBLIN, 3, 60, 90, {})
        self.assertEqual(sched.days[0].entries[0].highlight, "season_finale")


class LinkTest(unittest.TestCase):
    def test_fill(self):
        self.assertEqual(schedule.fill("https://x.example/movie/{tmdb}", tmdb=603), "https://x.example/movie/603")
        self.assertEqual(
            schedule.fill("https://x.example/t/{imdb}?s={tvdb}", tvdb=12, imdb="tt0133093"),
            "https://x.example/t/tt0133093?s=12",
        )
        self.assertIsNone(schedule.fill("https://x.example/movie/{tmdb}"))  # id unknown: no half link
        self.assertIsNone(schedule.fill(None, tmdb=1))

    def test_entries_get_links_and_trailers(self):
        links = Links(movie="https://r.example/movie/{tmdb}", tv="https://r.example/tv/{tmdb}")
        sched = schedule.build(
            [ep(1, 3, utc(2026, 11, 5, 20), tmdb=1399), ep(1, 3, utc(2026, 11, 5, 21), series_id=2, title="No ids")],
            [mv(digital=date(2026, 11, 6), tmdb=603, trailer="vKQi3bBA1y8")],
            NOW,
            DUBLIN,
            3,
            60,
            90,
            {},
            links,
        )
        by_title = {e.title: e for d in sched.days for e in d.entries}
        self.assertEqual(by_title["Show"].link, "https://r.example/tv/1399")
        self.assertIsNone(by_title["No ids"].link)
        self.assertEqual(by_title["Film"].link, "https://r.example/movie/603")
        self.assertEqual(by_title["Film"].trailer, "https://www.youtube.com/watch?v=vKQi3bBA1y8")
        self.assertIsNone(by_title["Show"].trailer)
        no_trailers = schedule.build(
            [],
            [mv(digital=date(2026, 11, 6), trailer="vKQi3bBA1y8")],
            NOW,
            DUBLIN,
            3,
            60,
            90,
            {},
            Links(trailers=False),
        )
        self.assertIsNone(no_trailers.days[0].entries[0].trailer)


if __name__ == "__main__":
    unittest.main()
