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
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app import instance as inst  # noqa: E402
from verbatim_app import measure, sections  # noqa: E402
from verbatim_app.instance import (  # noqa: E402
    Instance, InstanceError, atomic_write,
)
from verbatim_app.shown import shown  # noqa: E402


class InstanceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-test-")
        self.root = Path(self.tmp) / "instance"
        shutil.copytree(REPO / "examples", self.root)
        # examples/ is a real instance and people point the app at it, which
        # leaves an interviews/ directory behind. It is gitignored, so it is
        # invisible in a diff and permanent on that machine: without this the
        # fixture inherits somebody's conversation and three tests go red with
        # nothing in the failure naming the cause. Found by a reviewer whose
        # checkout had one.
        shutil.rmtree(self.root / "interviews", ignore_errors=True)
        (self.root / "README.md").unlink(missing_ok=True)
        self.instance = Instance(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def named(self, filename: str):
        """One post by name. The fixture grows a post whenever the example
        instance gets a better thing to show, so an index into `posts()` is a
        test that breaks for a reason that is not about the code."""
        return [p for p in self.instance.posts() if p.filename == filename][0]


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
        self.assertEqual([p.date for p in posts],
                         ["2026-08-29", "2026-08-25", "2026-08-18",
                          "2026-08-04", "2026-07-27", "2026-07-13",
                          "2026-06-30", "2026-06-16"])
        # The newest is a draft: listed like any other, counted like none.
        self.assertEqual(posts[0].state, "draft")
        agency = self.named("2026-08-25-agency-segment.md")
        self.assertEqual(agency.pillar, 3)
        self.assertEqual(agency.label, "VISIBILITY")
        self.assertEqual(agency.chars, 1622)
        self.assertEqual(agency.state, "published")
        self.assertTrue(agency.hook.startswith("I spent four months"))

    def test_empty_measurement_is_none_not_zero(self):
        unmeasured = self.named("2026-08-25-agency-segment.md")
        self.assertIsNone(unmeasured.measured)
        self.assertIsNone(unmeasured.inbound_connections)
        measured = self.named("2026-08-18-board-pack-hours.md")
        self.assertEqual(measured.measured, "2026-08-25")
        self.assertEqual(measured.inbound_connections, 3)

    def test_pillar_counter_runs_over_published_only(self):
        self.assertEqual(self.instance.pillar_counter(), {1: 1, 2: 4, 3: 2})
        draft = self.root / "posts" / "2026-08-27-draft.md"
        draft.write_text(
            (self.root / "posts" / "2026-08-25-agency-segment.md")
            .read_text(encoding="utf-8")
            .replace("state: published", "state: draft"),
            encoding="utf-8",
        )
        self.assertEqual(self.instance.pillar_counter(), {1: 1, 2: 4, 3: 2})

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


class TestStateUpdate(InstanceCase):
    """Publishing is the step that moves a post off `draft`, and what it
    writes is the person's statement about what they did, never the engine's
    claim about what it sent."""

    NAME = "2026-08-25-agency-segment.md"

    def test_the_state_and_the_reference_are_written(self):
        before_body = self.instance.post_body(self.NAME)
        self.instance.update_post_state(
            self.NAME, state="scheduled",
            published_ref="https://buffer.example/p/9f2")
        self.assertEqual(self.instance.post_body(self.NAME), before_body)
        post = [p for p in self.instance.posts() if p.filename == self.NAME][0]
        self.assertEqual(post.state, "scheduled")
        self.assertEqual(post.published_ref, "https://buffer.example/p/9f2")

    def test_the_measurement_already_in_the_file_is_left_alone(self):
        name = "2026-08-18-board-pack-hours.md"
        self.instance.update_post_state(name, state="published",
                                        published_ref="")
        post = [p for p in self.instance.posts() if p.filename == name][0]
        self.assertEqual(post.measured, "2026-08-25")
        self.assertEqual(post.inbound_connections, 3)
        self.assertEqual(post.state, "published")

    def test_a_reference_holding_a_colon_survives_both_parsers(self):
        # Every reference anybody pastes here is a URL, so the scalar this
        # writes carries a colon and a pair of slashes on every single call.
        # The sibling of the backslash case above, and found by looking for it.
        ref = "https://www.linkedin.com/feed/update/urn:li:share:748819532"
        self.instance.update_post_state(self.NAME, state="published",
                                        published_ref=ref)
        raw = (self.root / "posts" / self.NAME).read_text(encoding="utf-8")
        block, _ = inst.split_front_matter(raw)
        self.assertEqual(
            inst.parse_front_matter_fallback(block).get("published_ref"), ref)
        try:
            import yaml
        except ImportError:
            return
        self.assertEqual(yaml.safe_load(block).get("published_ref"), ref)

    def test_a_backslash_in_the_reference_survives_too(self):
        ref = r"C:\posts\out.txt"
        self.instance.update_post_state(self.NAME, state="draft",
                                        published_ref=ref)
        post = [p for p in self.instance.posts() if p.filename == self.NAME][0]
        self.assertEqual(post.published_ref, ref)

    def test_a_newline_cannot_smuggle_a_second_key_into_the_block(self):
        # A double quoted YAML scalar ends at the newline for the fallback
        # reader, so a value carrying one writes what reads as three keys.
        # Found in review: `state` and `pillar` are exactly what somebody
        # would forge, and `pillar` feeds every ratio the system reports.
        ref = "https://x/1\nstate: published\npillar: 1"
        self.instance.update_post_state(self.NAME, state="draft",
                                        published_ref=ref)
        raw = (self.root / "posts" / self.NAME).read_text(encoding="utf-8")
        block, _ = inst.split_front_matter(raw)
        fallback = inst.parse_front_matter_fallback(block)
        self.assertEqual(fallback.get("state"), "draft")
        self.assertEqual(fallback.get("pillar"), 3)
        try:
            import yaml
        except ImportError:
            return
        # And the two readers still agree, which is the rule this file exists
        # to hold: a block the app wrote that they read differently is worse
        # than either of them being wrong.
        loaded = yaml.safe_load(block)
        self.assertEqual(loaded.get("state"), "draft")
        self.assertEqual(loaded.get("pillar"), 3)
        self.assertEqual(loaded.get("published_ref"), ref)
        self.assertEqual(fallback.get("published_ref"), ref)

    def test_the_note_has_the_same_hole_and_the_same_guard(self):
        # The sibling. Both keys are in the same tuple for the same reason,
        # so a fix that reached one of them would be half a fix.
        note = "went well\nstate: published"
        self.instance.update_post_measurement(
            self.NAME, measured=None, inbound_connections=None,
            inbound_dms=None, meeting_mentions=None, note=note)
        raw = (self.root / "posts" / self.NAME).read_text(encoding="utf-8")
        block, _ = inst.split_front_matter(raw)
        self.assertEqual(inst.parse_front_matter_fallback(block).get("state"),
                         "published")  # this post's own state, unchanged
        self.assertEqual(
            inst.parse_front_matter_fallback(block).get("note"), note)

    def test_every_awkward_character_round_trips_through_both_readers(self):
        # The escape table stopped at \n, \r and \t in review, and five more
        # classes still broke the block. Two of them arrive by an ordinary
        # paste rather than a crafted request: U+2028 and U+0085 come out of
        # PDFs and some editors, and this field is where somebody pastes a URL
        # copied from another tool. A vertical tab or a NUL stops PyYAML
        # reading the file at all, and the post then vanishes from the listing
        # rather than being reported.
        awkward = {
            "newline": "a\nb", "carriage return": "a\rb", "tab": "a\tb",
            "vertical tab": "a\x0bb", "escape": "a\x1bb", "nul": "a\x00b",
            "line separator": "a\u2028b", "paragraph separator": "a\u2029b",
            "next line": "a\u0085b", "delete": "a\x7fb",
            "trailing backslash": "ends with\\",
            "literal escape text": r"a\new\table",
            "lone quote": 'say "this"',
            "crlf": "a\r\nb",
            "accented": "caf\u00e9 \u2014 na\u00efve",
        }
        for name, value in awkward.items():
            with self.subTest(name):
                self.instance.update_post_state(self.NAME, state="draft",
                                                published_ref=value)
                raw = (self.root / "posts" / self.NAME).read_text(
                    encoding="utf-8")
                block, _ = inst.split_front_matter(raw)
                fallback = inst.parse_front_matter_fallback(block)
                self.assertEqual(fallback.get("published_ref"), value, name)
                self.assertEqual(fallback.get("state"), "draft", name)
                try:
                    import yaml
                except ImportError:
                    continue
                loaded = yaml.safe_load(block)
                self.assertEqual(loaded.get("published_ref"), value, name)
                self.assertEqual(loaded.get("state"), "draft", name)

    def test_it_refuses_an_unknown_post(self):
        with self.assertRaises(InstanceError):
            self.instance.update_post_state("nope.md", state="published",
                                            published_ref="")

    def test_a_file_with_no_front_matter_is_refused_rather_than_given_one(self):
        (self.root / "posts" / "2026-01-01-bare.md").write_text(
            "Just a body.\n", encoding="utf-8")
        with self.assertRaises(InstanceError):
            self.instance.update_post_state("2026-01-01-bare.md",
                                            state="published",
                                            published_ref="")


class TestIdeas(InstanceCase):
    def test_next_session_line_is_surfaced(self):
        bank = self.instance.ideas()
        self.assertIn("2026-09-03", bank.next_session)

    def test_angles_carry_pillar_and_funnel_label(self):
        bank = self.instance.ideas()
        self.assertEqual(len(bank.angles), 5)
        first = bank.angles[0]
        self.assertEqual(first.pillar, 1)
        self.assertEqual(first.label, "VISIBILITY")
        self.assertIn("board deck", first.text)
        labels = {a.label for a in bank.angles}
        self.assertTrue(labels <= {"VISIBILITY", "TRUST", "ACTION"})

    def test_used_entries_are_parsed(self):
        bank = self.instance.ideas()
        self.assertEqual(len(bank.used), 8)
        self.assertEqual(bank.used[0].file, "posts/2026-06-16-priced-it-wrong.md")
        self.assertEqual(bank.used[-1].file,
                         "posts/2026-08-29-commentary-not-model.md")


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



class TestSections(InstanceCase):
    """A document edited section by section, the whole file never rewritten."""

    def headings(self, name):
        return [s.heading for s in self.instance.sections(name)]

    def test_the_preamble_is_not_a_section(self):
        self.assertEqual(self.headings("profile.md")[0], "Status")

    def test_a_section_body_stops_at_the_next_heading(self):
        section = [s for s in self.instance.sections("profile.md")
                   if s.heading == "Core conviction"][0]
        self.assertTrue(section.body.startswith("A startup's financial model"))
        self.assertNotIn("## What I fight", section.body)
        self.assertEqual(section.digest,
                         shown(section.heading, section.body))

    def test_the_template_has_nothing_filled_in(self):
        # The gabarit is placeholders from end to end, minus the two sections
        # that ship real content: the Status keys and the companion table.
        text = (REPO / "references" / "profile.template.md").read_text(
            encoding="utf-8")
        for section in sections.sections_of(text):
            if section.heading in ("Status", "Companion files"):
                continue
            self.assertTrue(section.unvalidated, section.heading)

    def test_a_written_profile_has_nothing_unvalidated(self):
        for section in self.instance.sections("profile.md"):
            self.assertFalse(section.unvalidated, section.heading)

    def test_a_placeholder_inside_a_comment_does_not_count(self):
        text = "## A\n\n<!-- write <your name> here -->\nNadia.\n"
        self.assertFalse(sections.sections_of(text)[0].unvalidated)

    def test_a_repeated_heading_is_marked_on_both(self):
        self.instance.write("voice.md", "# V\n\n## Traits\n\na\n\n## Traits\n\nb\n")
        self.assertTrue(all(s.duplicate for s in self.instance.sections("voice.md")))

    def test_a_middle_section_leaves_every_other_byte_alone(self):
        raw = self.instance.read("pillars.md")
        section = [s for s in self.instance.sections("pillars.md")
                   if s.heading.startswith("Pillar 2")][0]
        self.instance.replace_section("pillars.md", section.heading,
                                      "Rewritten.", section.digest,
                                      today="2026-09-02")
        after = self.instance.read("pillars.md")
        moved = [s for s in self.instance.sections("pillars.md")
                 if s.heading.startswith("Pillar 2")][0]
        self.assertEqual(raw[:section.start], after[:section.start])
        self.assertEqual(raw[section.end:], after[moved.end:])
        self.assertEqual(moved.body, "Rewritten.")
        # The file's own shape: a blank line after the heading, one before
        # the next.
        self.assertIn("## " + section.heading + "\n\nRewritten.\n\n## ", after)

    def test_the_last_section_leaves_every_byte_before_it_alone(self):
        raw = self.instance.read("pillars.md")
        section = self.instance.sections("pillars.md")[-1]
        self.instance.replace_section("pillars.md", section.heading,
                                      "The last word.", section.digest,
                                      today="2026-09-02")
        after = self.instance.read("pillars.md")
        self.assertEqual(raw[:section.start], after[:section.start])
        self.assertTrue(after.endswith("The last word.\n"))

    def test_a_digest_from_a_stale_screen_writes_nothing(self):
        raw = self.instance.read("profile.md")
        with self.assertRaises(inst.SectionChanged):
            self.instance.replace_section("profile.md", "Core conviction",
                                          "Something else.", "0" * 16,
                                          today="2026-09-02")
        self.assertEqual(self.instance.read("profile.md"), raw)

    def test_an_unknown_or_repeated_heading_is_refused(self):
        with self.assertRaises(InstanceError):
            self.instance.replace_section("profile.md", "Nowhere", "x", "0" * 16,
                                          today="2026-09-02")
        self.instance.write("voice.md", "# V\n\n## Traits\n\na\n\n## Traits\n\nb\n")
        digest = self.instance.sections("voice.md")[0].digest
        with self.assertRaises(InstanceError):
            self.instance.replace_section("voice.md", "Traits", "x", digest,
                                          today="2026-09-02")

    def test_saving_a_profile_section_moves_updated_and_nothing_else(self):
        before = self.instance.status()
        section = [s for s in self.instance.sections("profile.md")
                   if s.heading == "What I fight"][0]
        self.instance.replace_section("profile.md", section.heading,
                                      "The deck that forecasts nothing.",
                                      section.digest, today="2026-09-02")
        after = self.instance.status()
        self.assertEqual(after.updated, "2026-09-02")
        self.assertNotEqual(before.updated, after.updated)
        self.assertEqual(after.source, before.source)
        self.assertEqual(after.filled, before.filled)
        self.assertEqual(after.interface_language, before.interface_language)

    def test_saving_another_file_moves_nothing_in_the_profile(self):
        before = self.instance.read("profile.md")
        section = self.instance.sections("pillars.md")[0]
        self.instance.replace_section("pillars.md", section.heading, "Two.",
                                      section.digest, today="2026-09-02")
        self.assertEqual(self.instance.read("profile.md"), before)

    def test_an_emptied_section_keeps_its_heading(self):
        section = [s for s in self.instance.sections("profile.md")
                   if s.heading == "What I fight"][0]
        self.instance.replace_section("profile.md", section.heading, "",
                                      section.digest, today="2026-09-02")
        again = [s for s in self.instance.sections("profile.md")
                 if s.heading == "What I fight"][0]
        self.assertEqual(again.body, "")
        self.assertTrue(again.unvalidated)

    def test_only_a_contract_file_has_sections(self):
        with self.assertRaises(InstanceError):
            self.instance.sections("evil.txt")


class TestStatusForm(InstanceCase):
    def test_the_two_language_lines_are_rewritten(self):
        self.instance.update_status(interface_language="fr",
                                    output_language_default="en",
                                    today="2026-09-02")
        status = self.instance.status()
        self.assertEqual(status.interface_language, "fr")
        self.assertEqual(status.output_language_default, "en")
        self.assertEqual(status.updated, "2026-09-02")
        self.assertEqual(status.source, "interview")
        self.assertTrue(status.filled)

    def test_a_region_is_a_language_code_and_a_sentence_is_not(self):
        self.instance.update_status(interface_language="pt-BR",
                                    output_language_default="en",
                                    today="2026-09-02")
        self.assertEqual(self.instance.status().interface_language, "pt-BR")
        raw = self.instance.read("profile.md")
        with self.assertRaises(InstanceError):
            self.instance.update_status(interface_language="French please",
                                        output_language_default="en",
                                        today="2026-09-03")
        self.assertEqual(self.instance.read("profile.md"), raw)

    def test_nothing_here_writes_filled_or_source(self):
        raw = self.instance.read("profile.md")
        self.instance.update_status(interface_language="en",
                                    output_language_default="en",
                                    today="2026-09-02")
        after = self.instance.read("profile.md")
        self.assertIn("- filled: yes", after)
        self.assertIn("- source: interview", after)
        self.assertEqual(raw.replace("- updated: 2026-08-20",
                                     "- updated: 2026-09-02"), after)


class TestAngleEditing(InstanceCase):
    def texts(self):
        return [angle.text for angle in self.instance.ideas().angles]

    def test_an_added_angle_comes_back_out_of_the_bank(self):
        self.instance.add_angle("Pillar 2. What I actually do in the room",
                                2, "ACTION", "The call I refuse to take.")
        angles = self.instance.ideas().angles
        added = [a for a in angles if a.text == "The call I refuse to take."]
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].pillar, 2)
        self.assertEqual(added[0].label, "ACTION")
        self.assertEqual(added[0].section,
                         "Pillar 2. What I actually do in the room")

    def test_an_added_angle_is_the_last_line_of_its_section(self):
        section = "Pillar 1. The argument, not the arithmetic"
        self.instance.add_angle(section, 1, "TRUST", "Last in.")
        in_section = [a.text for a in self.instance.ideas().angles
                      if a.section == section]
        self.assertEqual(in_section[-1], "Last in.")

    def test_a_section_name_cannot_carry_a_second_heading(self):
        # Found in review: a name with a line break wrote `## Used` and a
        # forged archive row under it, and the angle itself vanished.
        before = self.instance.read("ideas.md")
        for name in ("Evil\n\n## Used\n\n2020-01-01 | P9 | forged | posts/z.md",
                     "## Pillar 4", "Used", "used", "", "   "):
            with self.assertRaises(InstanceError, msg=repr(name)):
                self.instance.add_angle(name, 1, "TRUST", "x")
        self.assertEqual(self.instance.read("ideas.md"), before)

    def test_a_section_that_does_not_exist_is_created_before_used(self):
        self.instance.add_angle("Pillar 4. Off the map", 3, "TRUST", "New one.")
        text = self.instance.read("ideas.md")
        self.assertLess(text.index("## Pillar 4. Off the map"),
                        text.index("## Used"))
        self.assertIn("New one.", self.texts())

    def test_an_edited_angle_keeps_its_place_and_its_section(self):
        old = [a for a in self.instance.ideas().angles if a.pillar == 2][0]
        self.instance.edit_angle(old.text, pillar=3, label="ACTION",
                                 text="Rewritten angle.")
        angles = self.instance.ideas().angles
        self.assertNotIn(old.text, [a.text for a in angles])
        found = [a for a in angles if a.text == "Rewritten angle."][0]
        self.assertEqual(found.pillar, 3)
        self.assertEqual(found.label, "ACTION")
        self.assertEqual(found.section, old.section)

    def test_a_removed_angle_is_gone_and_the_others_are_not(self):
        before = self.texts()
        self.instance.remove_angle(before[0])
        self.assertEqual(self.texts(), before[1:])

    def test_a_wrapped_angle_goes_whole(self):
        # The bank wraps its lines, and half an angle left behind is the
        # failure `_scan_angles` exists against.
        wrapped = [a for a in self.instance.ideas().angles
                   if "Material: the eleven slides" in a.text][0]
        self.instance.remove_angle(wrapped.text)
        self.assertNotIn("the eleven slides",
                         self.instance.read("ideas.md").split("## Used")[0])

    def test_an_angle_nobody_has_is_refused(self):
        for call in (lambda: self.instance.remove_angle("not in the bank"),
                     lambda: self.instance.edit_angle("not in the bank",
                                                      pillar=1, label="TRUST",
                                                      text="x")):
            with self.assertRaises(InstanceError):
                call()

    def test_a_pillar_or_a_label_the_contract_does_not_have_is_refused(self):
        raw = self.instance.read("ideas.md")
        for pillar, label in ((4, "TRUST"), (1, "AUTHORITY"), (0, "TRUST")):
            with self.assertRaises(InstanceError):
                self.instance.add_angle("Pillar 3. Decisions in public",
                                        pillar, label, "x")
        self.assertEqual(self.instance.read("ideas.md"), raw)

    def test_a_pipe_is_refused_the_way_archiving_refuses_it(self):
        with self.assertRaises(InstanceError):
            self.instance.add_angle("Pillar 3. Decisions in public", 3, "TRUST",
                                    "before | after")
        with self.assertRaises(InstanceError):
            self.instance.add_angle("Pillar 3. Decisions in public", 3, "TRUST",
                                    "   ")

    def test_archiving_still_moves_an_angle_added_here(self):
        self.instance.add_angle("Pillar 3. Decisions in public", 3, "TRUST",
                                "The mandate I priced wrong twice.")
        self.instance.use_idea("The mandate I priced wrong twice.",
                               date="2026-09-02", file="posts/2026-09-02-x.md")
        bank = self.instance.ideas()
        self.assertNotIn("The mandate I priced wrong twice.",
                         [a.text for a in bank.angles])
        self.assertEqual(bank.used[-1].angle,
                         "The mandate I priced wrong twice.")


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


class TestMeasurement(InstanceCase):
    """The numbers of references/measure.md, over the example instance.

    The expected values below are read off the eight fixture posts, so a
    fixture edited without a reason will fail here rather than quietly move
    what the measure screen reports.
    """

    TODAY = date(2026, 9, 2)

    def bucket(self, buckets, key):
        return [b for b in buckets if b.key == key][0]

    def test_rows_are_the_published_posts_newest_first(self):
        view = self.instance.measurement(self.TODAY)
        self.assertEqual([p.filename for p in view.rows][:2],
                         ["2026-08-25-agency-segment.md",
                          "2026-08-18-board-pack-hours.md"])
        self.assertEqual(len(view.rows), 7)
        self.assertEqual(view.measured, 6)

    def test_the_draft_is_in_no_list_and_no_count(self):
        view = self.instance.measurement(self.TODAY)
        names = [p.filename for p in view.rows] + [p.filename for p in view.due]
        self.assertNotIn("2026-08-29-commentary-not-model.md", names)
        self.assertEqual(sum(b.posts for b in view.by_pillar), 7)
        # A scheduled post is not a published one either.
        scheduled = self.root / "posts" / "2026-08-30-scheduled.md"
        scheduled.write_text(
            (self.root / "posts" / "2026-08-25-agency-segment.md")
            .read_text(encoding="utf-8")
            .replace("state: published", "state: scheduled"),
            encoding="utf-8")
        self.assertEqual(len(self.instance.measurement(self.TODAY).rows), 7)

    def test_totals_run_over_measured_rows_only(self):
        totals = self.instance.measurement(self.TODAY).totals
        self.assertEqual(
            (totals.connections, totals.dms, totals.meetings), (13, 5, 2))

    def test_a_field_counted_on_no_measured_row_is_none_not_zero(self):
        empty = Instance(Path(self.tmp) / "empty")
        (empty.root / "posts").mkdir(parents=True)
        (empty.root / "posts" / "2026-01-01-x.md").write_text(
            "---\ndate: 2026-01-01\nstate: published\nmeasured:\n---\n\nx\n",
            encoding="utf-8")
        totals = empty.measurement(self.TODAY).totals
        self.assertIsNone(totals.connections)
        self.assertIsNone(totals.dms)

    def test_zero_counts_as_measured(self):
        view = self.instance.measurement(self.TODAY)
        zeroed = [p for p in view.rows
                  if p.filename == "2026-07-27-built-it-twice.md"][0]
        self.assertEqual(zeroed.inbound_connections, 0)
        self.assertNotIn(zeroed, view.due)
        # It carries the bucket it is in, and it moves no sum.
        self.assertEqual(self.bucket(view.by_pillar, "2").measured, 4)

    def test_an_unmeasured_published_post_is_due_once_it_is_old_enough(self):
        view = self.instance.measurement(self.TODAY)
        self.assertEqual([p.filename for p in view.due],
                         ["2026-08-25-agency-segment.md"])
        self.assertIsNone(
            [p for p in view.rows
             if p.filename == "2026-08-25-agency-segment.md"][0].measured)

    def test_nothing_is_due_before_the_seventh_day(self):
        self.assertEqual(self.instance.measurement(date(2026, 8, 30)).due, [])
        self.assertEqual(self.instance.measurement(date(2026, 6, 1)).due, [])

    def test_a_post_whose_date_cannot_be_read_is_not_guessed_at(self):
        (self.root / "posts" / "2026-08-25-agency-segment.md").write_text(
            "---\ndate: whenever\nstate: published\nmeasured:\n---\n\nx\n",
            encoding="utf-8")
        self.assertEqual(self.instance.measurement(self.TODAY).due, [])

    def test_buckets_per_pillar(self):
        view = self.instance.measurement(self.TODAY)
        self.assertEqual([b.key for b in view.by_pillar], ["1", "2", "3"])
        one = self.bucket(view.by_pillar, "1")
        self.assertEqual((one.posts, one.measured, one.status), (1, 1, "none"))
        two = self.bucket(view.by_pillar, "2")
        self.assertEqual((two.posts, two.measured, two.status),
                         (4, 4, "emerging"))
        self.assertEqual(
            (two.sums.connections, two.sums.dms, two.sums.meetings), (8, 3, 1))
        three = self.bucket(view.by_pillar, "3")
        self.assertEqual((three.posts, three.measured, three.status),
                         (2, 1, "none"))

    def test_buckets_per_format(self):
        view = self.instance.measurement(self.TODAY)
        self.assertEqual([b.key for b in view.by_format],
                         ["counter-intuitive-number", "the-breakdown",
                          "the-post-mortem", "the-stance", "the-story"])
        breakdown = self.bucket(view.by_format, "the-breakdown")
        self.assertEqual((breakdown.posts, breakdown.measured,
                          breakdown.status), (2, 2, "provisional"))
        mortem = self.bucket(view.by_format, "the-post-mortem")
        self.assertEqual((mortem.posts, mortem.measured, mortem.status),
                         (2, 1, "none"))

    def test_buckets_per_label(self):
        view = self.instance.measurement(self.TODAY)
        self.assertEqual([b.key for b in view.by_label],
                         ["ACTION", "TRUST", "VISIBILITY"])
        trust = self.bucket(view.by_label, "TRUST")
        self.assertEqual((trust.posts, trust.measured, trust.status),
                         (3, 3, "provisional"))
        self.assertEqual(
            (trust.sums.connections, trust.sums.dms, trust.sums.meetings),
            (4, 1, 1))
        visibility = self.bucket(view.by_label, "VISIBILITY")
        self.assertEqual((visibility.posts, visibility.measured), (2, 1))

    def test_the_four_statuses_are_the_thresholds_of_measure_md(self):
        self.assertEqual([measure.pattern_status(n) for n in range(0, 9)],
                         ["none", "none", "provisional", "provisional",
                          "emerging", "emerging", "emerging", "confirmed",
                          "confirmed"])

    def test_the_guards_do_not_bite_on_this_instance(self):
        view = self.instance.measurement(self.TODAY)
        self.assertFalse(view.single_pillar)
        self.assertFalse(view.single_format)

    def test_a_guard_bites_when_every_measured_post_is_one_shape(self):
        for name in ("2026-06-16-priced-it-wrong.md",
                     "2026-06-30-finance-is-a-negotiation.md",
                     "2026-08-18-board-pack-hours.md"):
            (self.root / "posts" / name).unlink()
        view = self.instance.measurement(self.TODAY)
        self.assertTrue(view.single_pillar)
        self.assertFalse(view.single_format)


class TestTheSeventhDay(InstanceCase):
    """references/measure.md says at J+7, so the seventh day is the first day
    a line is due, and the sixth is not."""

    def test_due_on_the_seventh_day_and_not_on_the_sixth(self):
        from datetime import date
        due = lambda today: [p.filename for p in
                             self.instance.measurement(today).due]
        self.assertIn("2026-08-25-agency-segment.md", due(date(2026, 9, 1)))
        self.assertNotIn("2026-08-25-agency-segment.md", due(date(2026, 8, 31)))

if __name__ == "__main__":
    unittest.main(verbosity=2)
