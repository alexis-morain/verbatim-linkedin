"""The measure screen, against the Nadia Feriel example instance.

Needs fastapi and httpx, so run through the project environment:
    cd app && uv run --extra test python -m unittest discover -s tests

Everything on that screen is recomputed at read time, so what is asserted
here is the fixture posts of examples/ read through the routes. The numbers
themselves are pinned in test_instance.py.
"""

import unittest

from test_web import WebCase  # noqa: E402


class TestMeasureScreen(WebCase):
    def test_every_section_is_on_the_page(self):
        page = self.client.get("/measure")
        self.assertEqual(page.status_code, 200)
        for heading in ("To fill in", "Published posts", "Per pillar",
                        "Per format", "Per objective", "Two guards"):
            self.assertIn(heading, page.text, heading)

    def test_the_nav_carries_it(self):
        self.assertIn('href="/measure"', self.client.get("/posts").text)

    def test_the_table_holds_every_published_post_and_not_the_draft(self):
        page = self.client.get("/measure").text
        for date in ("2026-06-16", "2026-06-30", "2026-07-13", "2026-07-27",
                     "2026-08-04", "2026-08-18", "2026-08-25"):
            self.assertIn(date, page, date)
        self.assertNotIn("2026-08-29", page)

    def test_the_totals_sentence_is_there(self):
        page = self.client.get("/measure").text
        self.assertIn("Over 6 measured posts of 7 published", page)
        self.assertIn("13 inbound connections", page)

    def test_the_statuses_of_measure_md_are_shown(self):
        page = self.client.get("/measure").text
        self.assertIn("emerging", page)     # pillar 2, four measured posts
        self.assertIn("provisional", page)  # TRUST, three measured posts
        self.assertIn("not enough", page)   # pillar 1, one measured post

    def test_a_bucket_under_two_measured_shows_no_sum(self):
        page = self.client.get("/measure").text
        self.assertIn("there is nothing to conclude", page)

    def test_the_due_list_names_the_post_nobody_has_looked_at(self):
        page = self.client.get("/measure").text
        self.assertIn("2026-08-25-agency-segment.md", page)
        self.assertIn("nobody has looked yet", page)

    def test_both_guards_are_displayed_with_whether_they_bite(self):
        page = self.client.get("/measure").text
        self.assertIn("does not generalise to the others", page)
        self.assertIn("format effect until proven otherwise", page)
        self.assertIn("It does not bite right now.", page)

    def test_nothing_due_says_so_rather_than_showing_an_empty_list(self):
        (self.root / "posts" / "2026-08-25-agency-segment.md").unlink()
        self.assertIn("Nothing to fill in", self.client.get("/measure").text)

    def test_an_instance_with_no_published_post_says_so(self):
        for name in [p.name for p in (self.root / "posts").glob("*.md")]:
            (self.root / "posts" / name).unlink()
        page = self.client.get("/measure")
        self.assertEqual(page.status_code, 200)
        self.assertIn("No published post yet", page.text)


class TestMeasureOnThePostScreen(WebCase):
    def test_a_measured_post_shows_the_numbers_as_the_block(self):
        page = self.client.get("/posts/2026-08-18-board-pack-hours.md").text
        self.assertIn('class="measured"', page)
        self.assertIn("What this post produced", page)
        self.assertIn("2026-08-25", page)
        self.assertIn("Correct these numbers", page)

    def test_an_unmeasured_post_shows_the_form_and_no_block(self):
        page = self.client.get("/posts/2026-08-25-agency-segment.md").text
        self.assertNotIn('class="measured"', page)
        self.assertNotIn("Correct these numbers", page)
        self.assertIn('action="/posts/2026-08-25-agency-segment.md/measure"',
                      page)

    def test_the_hint_about_empty_against_zero_is_kept(self):
        page = self.client.get("/posts/2026-08-25-agency-segment.md").text
        self.assertIn("zero means it produced nothing", page)

    def test_no_pattern_status_is_claimed_about_one_post(self):
        # A status counts measured posts across a bucket, so it cannot be a
        # fact about a single post. The words themselves appear in this page
        # for other reasons, the author's own note included, so what is
        # asserted is the markup that would render one.
        page = self.client.get("/posts/2026-08-18-board-pack-hours.md").text
        self.assertNotIn("status-", page)


class TestOverviewPointsAtIt(WebCase):
    def test_the_pillar_table_gains_a_measured_count(self):
        page = self.client.get("/").text
        self.assertIn("4 measured", page)

    def test_a_due_post_puts_a_link_to_measure_on_the_overview(self):
        page = self.client.get("/").text
        self.assertIn("carries no measurement line yet", page)
        self.assertIn('href="/measure"', page)

    def test_no_due_post_no_link_in_the_body(self):
        (self.root / "posts" / "2026-08-25-agency-segment.md").unlink()
        page = self.client.get("/").text
        self.assertNotIn("carries no measurement line yet", page)


class TestAMeasuredLineWithNoFigures(WebCase):
    """A date with three blank fields is a line somebody started and did not
    finish. The block shows the word for an empty line in each cell rather
    than three blank cells under a heading that says what the post produced."""

    def test_the_empty_figures_say_so(self):
        name = "2026-08-25-agency-segment.md"
        self.client.post(f"/posts/{name}/measure",
                         data={"measured": "2026-09-01", "inbound_connections": "",
                               "inbound_dms": "", "meeting_mentions": ""})
        page = self.client.get(f"/posts/{name}").text
        self.assertIn('<dl class="measured">', page)
        self.assertEqual(page.count('<dd><span class="empty">not yet</span></dd>'), 3)


class TestTheDayIsASeam(WebCase):
    """The screens are drawn on the day the app is given, not the wall clock:
    on the sixth day after the unmeasured post, nothing is due anywhere."""
    from datetime import date as _d
    today = _d(2026, 8, 31)

    def test_nothing_is_due_the_day_before_the_seventh(self):
        page = self.client.get("/measure").text
        due_list = page.split("Published posts")[0]
        self.assertNotIn("2026-08-25-agency-segment.md", due_list)
        self.assertIn("Nothing to fill in", due_list)
        self.assertNotIn('href="/measure"', self.client.get("/").text.split("<main>")[1])

if __name__ == "__main__":
    unittest.main(verbosity=2)
