"""Tests for publish.py. Run: python3 lib/test_publish.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import publish  # noqa: E402

POST = "First line that survives the fold.\n\nThe body.\n"


class TestTierResolution(unittest.TestCase):
    def test_defaults_to_copy_paste(self):
        t = publish.resolve({})
        self.assertEqual(t.name, "copy")
        self.assertFalse(t.leaves_the_machine)

    def test_postiz_needs_an_integration_id(self):
        with self.assertRaises(publish.ConfigError):
            publish.resolve({"LINKEDIN_PUBLISH": "postiz"})

    def test_postiz_configured(self):
        t = publish.resolve({"LINKEDIN_PUBLISH": "postiz",
                             "POSTIZ_INTEGRATION_ID": "abc123",
                             "POSTIZ_INTEGRATION_NAME": "Personal profile"})
        self.assertEqual(t.name, "postiz")
        self.assertEqual(t.target, "abc123")
        self.assertTrue(t.leaves_the_machine)

    def test_command_needs_a_command(self):
        with self.assertRaises(publish.ConfigError):
            publish.resolve({"LINKEDIN_PUBLISH": "command"})

    def test_unknown_tier_is_refused(self):
        with self.assertRaises(publish.ConfigError):
            publish.resolve({"LINKEDIN_PUBLISH": "carrier-pigeon"})

    def test_tier_name_is_case_insensitive(self):
        self.assertEqual(publish.resolve({"LINKEDIN_PUBLISH": "COPY"}).name, "copy")


class TestGuards(unittest.TestCase):
    def test_refuses_an_empty_post(self):
        with self.assertRaises(publish.PostError):
            publish.check("   \n  ")

    def test_refuses_past_the_platform_limit(self):
        with self.assertRaises(publish.PostError):
            publish.check("x" * (publish.MAX_CHARS + 1))

    def test_accepts_exactly_the_limit(self):
        publish.check("x" * publish.MAX_CHARS)


class TestPlan(unittest.TestCase):
    def test_plan_names_the_target_channel(self):
        t = publish.resolve({"LINKEDIN_PUBLISH": "postiz",
                             "POSTIZ_INTEGRATION_ID": "abc123",
                             "POSTIZ_INTEGRATION_NAME": "Personal profile"})
        text = publish.plan(POST, t, when=None)
        self.assertIn("abc123", text)
        self.assertIn("Personal profile", text)

    def test_plan_shows_the_first_line_and_the_count(self):
        text = publish.plan(POST, publish.resolve({}), when=None)
        self.assertIn("First line that survives the fold.", text)
        self.assertIn(str(len(POST.strip())), text)


class TestDispatch(unittest.TestCase):
    def test_copy_tier_returns_the_text_and_sends_nothing(self):
        out = publish.dispatch(POST, publish.resolve({}), when=None, confirmed=False)
        self.assertEqual(out.sent, False)
        self.assertIn("First line", out.payload)

    def test_command_tier_does_nothing_without_confirmation(self):
        t = publish.resolve({"LINKEDIN_PUBLISH": "command",
                             "LINKEDIN_PUBLISH_CMD": "/bin/false"})
        out = publish.dispatch(POST, t, when=None, confirmed=False)
        self.assertFalse(out.sent)

    def test_command_tier_runs_the_command_and_pipes_the_post(self):
        t = publish.resolve({"LINKEDIN_PUBLISH": "command",
                             "LINKEDIN_PUBLISH_CMD": "cat"})
        out = publish.dispatch(POST, t, when=None, confirmed=True)
        self.assertTrue(out.sent)
        self.assertIn("First line that survives the fold.", out.payload)

    def test_command_tier_reports_a_failing_command(self):
        t = publish.resolve({"LINKEDIN_PUBLISH": "command",
                             "LINKEDIN_PUBLISH_CMD": "false"})
        with self.assertRaises(publish.PublishError):
            publish.dispatch(POST, t, when=None, confirmed=True)

    def test_postiz_tier_emits_a_payload_and_does_not_call_the_network(self):
        t = publish.resolve({"LINKEDIN_PUBLISH": "postiz",
                             "POSTIZ_INTEGRATION_ID": "abc123"})
        out = publish.dispatch(POST, t, when="2026-09-01T07:30:00", confirmed=True)
        self.assertFalse(out.sent)
        self.assertIn("abc123", out.payload)
        self.assertIn("2026-09-01T07:30:00", out.payload)


class TestSchedulerHtml(unittest.TestCase):
    """A scheduling tool takes HTML, and the shape decides how the post reads.

    Found the hard way: paragraphs sent without empty separators came out as a
    wall of text in the feed.
    """

    def test_paragraphs_are_separated_by_an_empty_one(self):
        html = publish.to_scheduler_html("Un.\n\nDeux.")
        self.assertEqual(html, "<p>Un.</p><p></p><p>Deux.</p>")

    def test_a_single_paragraph_gets_no_separator(self):
        self.assertEqual(publish.to_scheduler_html("Seul."), "<p>Seul.</p>")

    def test_soft_line_breaks_inside_a_paragraph_become_spaces(self):
        self.assertEqual(publish.to_scheduler_html("Un\ndeux."), "<p>Un deux.</p>")

    def test_blank_runs_do_not_produce_empty_paragraphs_of_their_own(self):
        self.assertEqual(
            publish.to_scheduler_html("Un.\n\n\n\nDeux."),
            "<p>Un.</p><p></p><p>Deux.</p>",
        )

    def test_bold_is_carried_over_from_markdown(self):
        self.assertEqual(
            publish.to_scheduler_html("**1. Titre**"), "<p><strong>1. Titre</strong></p>"
        )

    def test_decomposed_accents_are_normalised(self):
        # e + combining acute is what shows up as a floating accent in a feed
        html = publish.to_scheduler_html("cle\u0301")
        self.assertEqual(html, "<p>cl\u00e9</p>")
        self.assertNotIn("\u0301", html)

    def test_angle_brackets_are_escaped(self):
        self.assertEqual(
            publish.to_scheduler_html("a < b & c"), "<p>a &lt; b &amp; c</p>"
        )

    def test_bold_survives_escaping(self):
        self.assertEqual(
            publish.to_scheduler_html("**a & b**"), "<p><strong>a &amp; b</strong></p>"
        )

    def test_empty_text_is_refused(self):
        with self.assertRaises(publish.PostError):
            publish.to_scheduler_html("   ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
