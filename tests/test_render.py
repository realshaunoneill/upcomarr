import dataclasses
import re
import unittest
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from upcomarr import render, schedule
from upcomarr.model import Episode, Links, Movie, PosterRef

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
VOID = {"meta", "link", "img", "input", "br", "hr"}


def meta(**sources):
    return render.Meta(
        title="Coming <soon>",
        generated_at=NOW,
        tz_name="Europe/Dublin",
        version="0.1.0",
        asset_version="abc123",
        sources=sources or {"tv": render.SourceStatus("TV", True, False, NOW, None)},
    )


def sample(title="Show", overview="About.", network="Net", links=False):
    eps = [
        Episode(
            1,
            title,
            network,
            overview,
            1,
            1,
            "Pilot",
            NOW + timedelta(hours=9),
            None,
            False,
            PosterRef("sonarr", 1, "v"),
        )
    ]
    movies = [
        Movie(
            2,
            "Film",
            2026,
            "Studio",
            "About the film.",
            date(2026, 11, 8),
            None,
            None,
            False,
            None,
            None,
            tmdb=603 if links else None,
            trailer="vKQi3bBA1y8" if links else None,
        )
    ]
    if links:
        eps = [dataclasses.replace(eps[0], finale="season")]
    cfg = (
        Links(movie="https://request.example.com/movie/{tmdb}", tv="https://request.example.com/tv/{tmdb}")
        if links
        else None
    )
    return schedule.build(eps, movies, NOW, ZoneInfo("Europe/Dublin"), 3, 60, 90, {"sonarr:1": "abcd.jpg"}, cfg)


class Balance(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.errors, self.imgs = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.imgs.append(dict(attrs))
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.errors.append(tag)


class RenderTest(unittest.TestCase):
    def test_escapes_untrusted_text(self):
        html = render.render_index(
            sample(title="<script>alert(1)</script>", overview='"><img src=x onerror=alert(1)>'), meta()
        )
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("Coming &lt;soon&gt;", html)

    def test_no_inline_code_or_external_loads(self):
        html = render.render_index(sample(links=True), meta())
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)", html), "inline script")
        self.assertNotRegex(html, r"\sstyle=")
        self.assertNotRegex(html, r"\son[a-z]+=")
        self.assertNotIn("javascript:", html)
        # Nothing is loaded from another origin; links out are allowed, but only as new-tab, no-referrer links.
        self.assertNotRegex(html, r"\ssrc=\"(?:https?:)?//")
        external = re.findall(r"<a [^>]*href=\"https?://[^\"]+\"[^>]*>", html)
        self.assertEqual(len(external), 2)  # the trailer and the details link
        for tag in external:
            self.assertIn('rel="noopener noreferrer"', tag)
            self.assertIn('target="_blank"', tag)

    def test_actions_and_highlight(self):
        html = render.render_index(sample(links=True), meta())
        self.assertIn('href="https://www.youtube.com/watch?v=vKQi3bBA1y8"', html)
        self.assertIn('href="https://request.example.com/movie/603"', html)
        self.assertIn(">New series · full season<", html)  # S01E01 that is also the season finale
        self.assertIn('aria-label="Trailer: Film"', html)
        plain = render.render_index(sample(), meta())
        self.assertNotIn("card-actions", plain)

    def test_calendar_button(self):
        from upcomarr import ical

        sched = ical.attach(sample(), True)
        html = render.render_index(sched, meta())
        self.assertRegex(
            html, r'<a class="action action-calendar" href="cal/[0-9a-f]{20}\.ics" aria-label="Add to calendar: Show">'
        )
        self.assertNotRegex(html, r"action-calendar[^>]*target=")  # same origin, same tab
        self.assertNotIn("action-calendar", render.render_index(ical.attach(sample(), False), meta()))

    def test_structure(self):
        html = render.render_index(sample(), meta())
        parser = Balance()
        parser.feed(html)
        self.assertEqual(parser.errors, [])
        self.assertEqual(parser.stack, ["html"] if parser.stack else [])
        for tag in ("<main>", "<header", "<footer", "<h1>", 'lang="en"'):
            self.assertIn(tag, html)
        self.assertTrue(parser.imgs)
        for img in parser.imgs:
            self.assertIn("alt", img)
        self.assertIn('src="p/abcd.jpg"', html)
        self.assertIn('src="placeholder.svg"', html)  # the movie has no poster

    def test_stale_banner(self):
        stale = render.SourceStatus("TV", False, True, NOW - timedelta(hours=3), "http_503")
        html = render.render_index(sample(), meta(tv=stale))
        self.assertIn("The tv schedule could not be refreshed", html)
        self.assertNotIn("http_503", html)
        gone = render.SourceStatus("Movies", False, False, None, "connect")
        self.assertIn("unavailable right now", render.render_index(sample(), meta(movies=gone)))

    def test_empty(self):
        empty = schedule.Schedule(date(2026, 11, 3), (), ())
        self.assertIn("Nothing is scheduled yet", render.render_index(empty, meta()))

    def test_json_has_only_public_fields(self):
        data = render.upcoming_json(sample(), meta())
        self.assertEqual(data["schema"], 1)
        entry = data["days"][0]["entries"][0]
        self.assertEqual(entry["poster"], "abcd.jpg")
        self.assertNotIn("series_id", entry)


if __name__ == "__main__":
    unittest.main()
