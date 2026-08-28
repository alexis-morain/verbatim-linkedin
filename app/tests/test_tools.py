"""Tests for the tool set the loop hands to a model.

The instance fixture is the shipped persona under examples/. The lint and
publish tools run the real lib/ scripts in a subprocess, so these tests also
prove the wiring to them, network excluded: publish is only ever driven in
plan mode here, and there is no tier that opens a socket without --confirm.

    python3 app/tests/test_tools.py
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app.agent import ToolRefused  # noqa: E402
from verbatim_app.interview import InterviewError  # noqa: E402
from verbatim_app.tools import (  # noqa: E402
    DRAFT_TOOL, SHEET_TOOL, draft_tool, instance_tools,
)


class ToolsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-tools-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.root = Path(self.tmp) / "instance"
        shutil.copytree(REPO / "examples", self.root)
        (self.root / "README.md").unlink(missing_ok=True)
        (self.root / ".env").write_text(
            "VERBATIM_PROVIDER=openai\nVERBATIM_MODEL=zephyr-test\n",
            encoding="utf-8")
        self.environ = dict(os.environ)
        self.environ.pop("LINKEDIN_PUBLISH", None)
        self.tools = {tool.name: tool
                      for tool in instance_tools(self.root, REPO,
                                                 environ=self.environ)}

    def run_tool(self, name, **arguments):
        return self.tools[name].run(arguments)


class TestTheSet(ToolsCase):
    def test_four_tools_with_schemas(self):
        self.assertEqual(sorted(self.tools),
                         ["lint_post", "publish_plan", "read_instance",
                          "write_instance"])
        for tool in self.tools.values():
            self.assertEqual(tool.input_schema.get("type"), "object")
            self.assertTrue(tool.input_schema.get("required"))
            self.assertTrue(tool.description)


class TestReadInstance(ToolsCase):
    def test_a_root_file_is_read(self):
        self.assertIn("## Status", self.run_tool("read_instance",
                                                 path="profile.md"))

    def test_posts_alone_lists_the_directory(self):
        listing = self.run_tool("read_instance", path="posts")
        self.assertIn("2026-08-18-board-pack-hours.md", listing)
        self.assertIn("2026-08-25-agency-segment.md", listing)

    def test_a_post_is_read_raw_with_its_front_matter(self):
        text = self.run_tool("read_instance",
                             path="posts/2026-08-18-board-pack-hours.md")
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("state: published", text)

    def test_corpus_is_readable(self):
        listing = self.run_tool("read_instance", path="corpus")
        self.assertIn("2026-07-02-eleven-slides.md", listing)
        text = self.run_tool("read_instance",
                             path="corpus/2026-07-02-eleven-slides.md")
        self.assertIn("eleven", text.lower())

    def test_the_env_file_is_refused_without_quoting_it(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("read_instance", path=".env")
        message = str(caught.exception)
        self.assertIn("profile.md", message)
        self.assertNotIn("zephyr-test", message)

    def test_a_name_outside_the_contract_is_refused_with_the_list(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("read_instance", path="notes.txt")
        self.assertIn("voice.md", str(caught.exception))

    def test_traversal_inside_posts_is_refused(self):
        with self.assertRaises(ToolRefused):
            self.run_tool("read_instance", path="posts/../.env")

    def test_a_missing_post_is_refused_naming_what_exists(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("read_instance", path="posts/2099-01-01-ghost.md")
        self.assertIn("2026-08-25-agency-segment.md", str(caught.exception))

    def test_a_missing_optional_file_is_refused_naming_what_exists(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("read_instance", path="linkedin-page.md")
        self.assertIn("profile.md", str(caught.exception))

    def test_a_missing_argument_is_a_refusal_not_a_crash(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("read_instance")
        self.assertIn("path", str(caught.exception))


class TestWriteInstance(ToolsCase):
    def test_a_writable_file_is_written(self):
        answer = self.run_tool("write_instance", path="voice.md",
                               text="# Voice\n\nnew trait\n")
        self.assertIn("voice.md", answer)
        self.assertEqual((self.root / "voice.md").read_text(encoding="utf-8"),
                         "# Voice\n\nnew trait\n")

    def test_a_post_file_is_refused_naming_the_writable_set(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("write_instance", path="posts/2026-09-01-x.md",
                          text="x")
        self.assertIn("ideas.md", str(caught.exception))
        self.assertTrue((self.root / "posts"
                         / "2026-08-25-agency-segment.md").is_file())

    def test_the_env_file_is_refused(self):
        with self.assertRaises(ToolRefused):
            self.run_tool("write_instance", path=".env", text="x=y")

    def test_a_missing_text_argument_is_a_refusal(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("write_instance", path="voice.md")
        self.assertIn("text", str(caught.exception))


class TestLintPost(ToolsCase):
    def test_findings_come_back_as_the_report(self):
        report = self.run_tool("lint_post", lang="fr",
                               body="Voici — un test.\n")
        self.assertIn("finding", report)
        self.assertNotIn("0 finding(s)", report)

    def test_a_clean_body_reports_zero_findings(self):
        report = self.run_tool("lint_post", lang="fr",
                               body="Onze heures. Le chiffre est public.\n")
        self.assertIn("clean", report)

    def test_an_unknown_pack_is_refused_naming_the_packs(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("lint_post", lang="xx", body="text")
        message = str(caught.exception)
        self.assertIn("fr", message)
        self.assertIn("en", message)


class TestPublishPlan(ToolsCase):
    def test_the_default_tier_plans_to_copy(self):
        plan = self.run_tool("publish_plan", text="A short post.\n\nDone.")
        self.assertIn("copy", plan)
        self.assertIn("tier", plan)

    def test_a_configured_tier_is_planned_never_sent(self):
        self.environ["LINKEDIN_PUBLISH"] = "postiz"
        self.environ["POSTIZ_INTEGRATION_ID"] = "chan-123"
        plan = self.run_tool("publish_plan", text="A short post.")
        self.assertIn("chan-123", plan)
        self.assertNotIn("integrationId", plan)  # the payload, only built on send

    def test_a_confirm_argument_changes_nothing(self):
        plan = self.run_tool("publish_plan", text="A short post.",
                             confirm=True)
        self.assertIn("tier", plan)

    def test_an_unpublishable_post_is_a_refusal_that_says_why(self):
        with self.assertRaises(ToolRefused) as caught:
            self.run_tool("publish_plan", text="x" * 3200)
        self.assertIn("3000", str(caught.exception))

    def test_a_secret_value_never_reaches_the_model(self):
        self.environ["MY_API_KEY"] = "hunter2-secret-value"
        self.environ["LINKEDIN_PUBLISH"] = "command"
        self.environ["LINKEDIN_PUBLISH_CMD"] = "cat hunter2-secret-value"
        plan = self.run_tool("publish_plan", text="A short post.")
        self.assertNotIn("hunter2-secret-value", plan)
        self.assertIn("[MY_API_KEY]", plan)


class TestTheDraftTool(unittest.TestCase):
    """The engine's half of the draft: offer, never decide. Bound to one
    conversation, like the sheet tool, and it can no more archive a post
    than the sheet tool can approve a sheet."""

    def setUp(self):
        self.offered = []

        def write(arguments):
            self.offered.append(arguments)
        self.tool = draft_tool(write)

    def test_it_is_named_the_way_the_wire_carries_it(self):
        self.assertEqual(self.tool.name, DRAFT_TOOL)
        self.assertNotEqual(DRAFT_TOOL, SHEET_TOOL)

    def test_the_schema_asks_for_the_body_and_its_anchors(self):
        schema = self.tool.input_schema
        self.assertEqual(schema["required"], ["body"])
        pair = schema["properties"]["anchors"]["items"]
        self.assertEqual(sorted(pair["properties"]), ["post", "said"])

    def test_an_offer_reaches_the_conversation(self):
        answer = self.tool.run({"body": "Quatre mois pour rien.",
                                "anchors": [{"post": "Quatre mois",
                                             "said": "quatre mois"}]})
        self.assertEqual(len(self.offered), 1)
        self.assertEqual(self.offered[0]["body"], "Quatre mois pour rien.")
        self.assertIsInstance(answer, str)

    def test_a_refusal_reaches_the_model_as_a_tool_refusal(self):
        def write(arguments):
            raise InterviewError("the sheet is not approved yet")
        with self.assertRaisesRegex(ToolRefused, "not approved"):
            draft_tool(write).run({"body": "x"})


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
