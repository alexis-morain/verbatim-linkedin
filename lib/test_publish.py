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


if __name__ == "__main__":
    unittest.main(verbosity=2)
