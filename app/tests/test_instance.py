"""Tests for verbatim_app.instance, the disk-is-the-database layer.

The fixture is examples/, the Nadia Feriel persona, copied to a temp
directory so write tests never touch the shipped files. Every behaviour
asserted here is a clause of references/instance.md; when the two disagree,
the contract wins and this file is wrong.

Runs with the standard library only:  python3 app/tests/test_instance.py
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app import instance as inst  # noqa: E402
from verbatim_app.instance import (  # noqa: E402
    Instance, InstanceError, atomic_write,
)


class InstanceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-test-")
        self.root = Path(self.tmp) / "instance"
        shutil.copytree(REPO / "examples", self.root)
        (self.root / "README.md").unlink(missing_ok=True)
        self.instance = Instance(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestConformance(InstanceCase):
    def test_examples_instance_is_conformant(self):
        self.assertEqual(self.instance.conformance(), [])

    def test_missing_companion_file_is_reported(self):
        (self.root / "voice.md").unlink()
        gaps = self.instance.conformance()
        self.assertIn(("file-missing", "voice.md"), [(g.code, g.detail) for g in gaps])

    def test_missing_profile_stops_everything(self):
        (self.root / "profile.md").unlink()
        codes = [g.code for g in self.instance.conformance()]
        self.assertEqual(codes, ["profile-missing"])

    def test_unfilled_profile_is_a_gap(self):
        text = self.instance.read("profile.md").replace("- filled: yes", "- filled: no")
        self.instance.write("profile.md", text)
        codes = [g.code for g in self.instance.conformance()]
        self.assertIn("not-filled", codes)

    def test_missing_signature_section_is_a_gap(self):
        text = self.instance.read("profile.md").replace("## Signature block", "## Signature gone")
        self.instance.write("profile.md", text)
        codes = [g.code for g in self.instance.conformance()]
        self.assertIn("signature-missing", codes)

    def test_post_missing_a_measure_key_is_reported_not_guessed(self):
        crippled = self.root / "posts" / "2026-08-26-crippled.md"
        crippled.write_text(
            "---\ndate: 2026-08-26\npillar: 1\nformat: the-breakdown\n"
            "label: TRUST\nchars: 900\nstate: draft\n---\n\nbody\n",
            encoding="utf-8",
        )
        gaps = [g for g in self.instance.conformance() if g.code == "post-keys-missing"]
        self.assertEqual(len(gaps), 1)
        self.assertIn("2026-08-26-crippled.md", gaps[0].detail)
        self.assertIn("meeting_mentions", gaps[0].detail)


class TestStatus(InstanceCase):
    def test_status_block_parses(self):
        status = self.instance.status()
        self.assertTrue(status.filled)
        self.assertEqual(status.interface_language, "en")
        self.assertEqual(status.output_language_default, "en")
        self.assertEqual(status.source, "interview")

    def test_status_none_when_block_absent(self):
        self.instance.write("profile.md", "# Profile\n\nno status here\n")
        self.assertIsNone(self.instance.status())


class TestPosts(InstanceCase):
    def test_posts_are_parsed_and_sorted_newest_first(self):
        posts = self.instance.posts()
        self.assertEqual([p.date for p in posts], ["2026-08-25", "2026-08-18"])
        latest = posts[0]
        self.assertEqual(latest.pillar, 3)
        self.assertEqual(latest.label, "VISIBILITY")
        self.assertEqual(latest.chars, 1622)
        self.assertEqual(latest.state, "published")
        self.assertTrue(latest.hook.startswith("I spent four months"))

    def test_empty_measurement_is_none_not_zero(self):
        latest = self.instance.posts()[0]
        self.assertIsNone(latest.measured)
        self.assertIsNone(latest.inbound_connections)
        older = self.instance.posts()[1]
        self.assertEqual(older.measured, "2026-08-25")
        self.assertEqual(older.inbound_connections, 3)

    def test_pillar_counter_runs_over_published_only(self):
        self.assertEqual(self.instance.pillar_counter(), {2: 1, 3: 1})
        draft = self.root / "posts" / "2026-08-27-draft.md"
        draft.write_text(
            (self.root / "posts" / "2026-08-25-agency-segment.md")
            .read_text(encoding="utf-8")
            .replace("state: published", "state: draft"),
            encoding="utf-8",
        )
        self.assertEqual(self.instance.pillar_counter(), {2: 1, 3: 1})

    def test_post_body_is_the_text_after_front_matter(self):
        body = self.instance.post_body("2026-08-18-board-pack-hours.md")
        self.assertTrue(body.startswith("Eleven hours."))
        self.assertIn("Session notes", body)

    def test_post_raw_keeps_the_front_matter(self):
        raw = self.instance.post_raw("2026-08-18-board-pack-hours.md")
        self.assertTrue(raw.startswith("---\n"))
        self.assertIn("state: published", raw)
        with self.assertRaises(InstanceError):
            self.instance.post_raw("2099-01-01-ghost.md")


class TestMeasurementUpdate(InstanceCase):
    def test_update_writes_the_line_and_keeps_the_body_byte_for_byte(self):
        name = "2026-08-25-agency-segment.md"
        before_body = self.instance.post_body(name)
        self.instance.update_post_measurement(
            name,
            measured="2026-09-01",
            inbound_connections=2,
            inbound_dms=0,
            meeting_mentions=1,
            note="One founder call, post came up unprompted.",
        )
        self.assertEqual(self.instance.post_body(name), before_body)
        post = [p for p in self.instance.posts() if p.filename == name][0]
        self.assertEqual(post.measured, "2026-09-01")
        self.assertEqual(post.inbound_connections, 2)
        self.assertEqual(post.inbound_dms, 0)
        self.assertEqual(post.meeting_mentions, 1)
        self.assertEqual(post.note, "One founder call, post came up unprompted.")
        self.assertEqual(post.chars, 1622)
        self.assertEqual(post.state, "published")

    def test_a_backslash_in_the_note_survives_both_parsers(self):
        # A raw backslash inside a double-quoted YAML scalar is an escape
        # sequence; written unescaped it makes the file unreadable and every
        # consumer dies on it. Found by review, kept as a regression test.
        name = "2026-08-18-board-pack-hours.md"
        note = r"screenshot saved to C:\Users\alex\post.png, 100\% real"
        self.instance.update_post_measurement(
            name, measured="2026-09-01", inbound_connections=0,
            inbound_dms=0, meeting_mentions=0, note=note,
        )
        post = [p for p in self.instance.posts() if p.filename == name][0]
        self.assertEqual(post.note, note)
        raw = (self.root / "posts" / name).read_text(encoding="utf-8")
        block, _ = inst.split_front_matter(raw)
        self.assertEqual(inst.parse_front_matter_fallback(block).get("note"), note)
        try:
            import yaml
        except ImportError:
            return
        self.assertEqual(yaml.safe_load(block).get("note"), note)

    def test_update_refuses_an_unknown_post(self):
        with self.assertRaises(InstanceError):
            self.instance.update_post_measurement("nope.md", measured="2026-09-01",
                                                  inbound_connections=0, inbound_dms=0,
                                                  meeting_mentions=0, note="")


class TestIdeas(InstanceCase):
    def test_next_session_line_is_surfaced(self):
        bank = self.instance.ideas()
        self.assertIn("2026-09-03", bank.next_session)

    def test_angles_carry_pillar_and_funnel_label(self):
        bank = self.instance.ideas()
        self.assertEqual(len(bank.angles), 9)
        first = bank.angles[0]
        self.assertEqual(first.pillar, 1)
        self.assertEqual(first.label, "VISIBILITY")
        self.assertIn("commentary", first.text)
        labels = {a.label for a in bank.angles}
        self.assertTrue(labels <= {"VISIBILITY", "TRUST", "ACTION"})

    def test_used_entries_are_parsed(self):
        bank = self.instance.ideas()
        self.assertEqual(len(bank.used), 1)
        self.assertEqual(bank.used[0].file, "posts/2026-08-18-board-pack-hours.md")


class TestReadWrite(InstanceCase):
    def test_write_is_limited_to_contract_files(self):
        with self.assertRaises(InstanceError):
            self.instance.write("evil.txt", "x")
        with self.assertRaises(InstanceError):
            self.instance.write("../outside.md", "x")

    def test_write_roundtrips(self):
        text = self.instance.read("ideas.md") + "\n- [P1] `TRUST` A new angle. Material: none yet.\n"
        self.instance.write("ideas.md", text)
        self.assertEqual(self.instance.read("ideas.md"), text)

    def test_corpus_is_listed_and_readable(self):
        names = self.instance.corpus()
        self.assertEqual(names, ["2026-07-02-eleven-slides.md"])
        self.assertTrue(self.instance.corpus_text(names[0]).strip())

    def test_post_body_refuses_traversal(self):
        with self.assertRaises(InstanceError):
            self.instance.post_body("../profile.md")


class TestFrontMatterFallback(InstanceCase):
    def test_fallback_parser_matches_pyyaml_on_the_examples(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML not installed, nothing to compare against")
        for name in ("2026-08-25-agency-segment.md", "2026-08-18-board-pack-hours.md"):
            raw = (self.root / "posts" / name).read_text(encoding="utf-8")
            block, _ = inst.split_front_matter(raw)
            self.assertEqual(inst.parse_front_matter_fallback(block),
                             inst.parse_front_matter(block))



class TestAtomicWrite(unittest.TestCase):
    """The promise `atomic_write` makes: the whole file, or the previous one
    untouched. It covers a crash and a failed write; it does not fsync, so it
    does not cover a power loss, and the docstring says so."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-atomic-")
        self.path = Path(self.tmp) / "profile.md"
        self.path.write_text("the previous one\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def leftovers(self):
        return [p.name for p in Path(self.tmp).iterdir()
                if p.name != self.path.name]

    def test_a_write_that_fails_leaves_the_previous_file(self):
        original = os.replace

        def refusing(source, target):
            raise OSError("no space left on device")

        os.replace = refusing
        try:
            with self.assertRaises(OSError):
                atomic_write(self.path, "the new one\n")
        finally:
            os.replace = original
        self.assertEqual(self.path.read_text(encoding="utf-8"),
                         "the previous one\n")
        self.assertEqual(self.leftovers(), [])

    def test_a_write_that_succeeds_leaves_no_temporary_behind(self):
        atomic_write(self.path, "the new one\n")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "the new one\n")
        self.assertEqual(self.leftovers(), [])

    def test_the_file_is_never_seen_half_written(self):
        # os.replace is the whole mechanism: the name points at the old inode
        # until it points at the complete new one, never at a partial file.
        seen = []
        original = os.replace

        def watching(source, target):
            seen.append(Path(target).read_text(encoding="utf-8"))
            return original(source, target)

        os.replace = watching
        try:
            atomic_write(self.path, "the new one\n")
        finally:
            os.replace = original
        self.assertEqual(seen, ["the previous one\n"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
