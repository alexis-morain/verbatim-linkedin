"""Tests for the skill loader and the system block builder.

Two fixtures: a synthetic bundle in a temp directory for the edge cases, and
the repository itself for the sweep that proves every shipped skill loads and
every file it cites resolves. That sweep exists because this project already
shipped a skill citing a reference that was not in the tree.

    python3 app/tests/test_skills.py
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app.skills import (  # noqa: E402
    SkillError, citations, list_skills, load_skill, split_sections,
    system_block,
)

FRONT = ('---\nname: demo\ndescription: "A demo. Not for real use."\n'
         'version: 0.1.0\n---\n')

BODY = """# Demo

Read `references/one.md` before anything.

## First step

Wording comes from `locales/<lang>/thing.md`, conduct from
`locales/<interface_language>/inter.md`.

## Second step

Again `references/one.md`, and `references/two.md` closes.
"""


class BundleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="verbatim-skills-"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bundle = self.tmp / "bundle"
        (self.bundle / "skills" / "demo").mkdir(parents=True)
        (self.bundle / "references").mkdir()
        for lang in ("en", "fr"):
            (self.bundle / "locales" / lang).mkdir(parents=True)
        self.write_skill(FRONT + BODY)
        (self.bundle / "references" / "one.md").write_text(
            "reference one text\n", encoding="utf-8")
        (self.bundle / "references" / "two.md").write_text(
            "reference two text\n", encoding="utf-8")
        (self.bundle / "locales" / "en" / "thing.md").write_text(
            "english thing\n", encoding="utf-8")
        (self.bundle / "locales" / "fr" / "thing.md").write_text(
            "chose francaise\n", encoding="utf-8")
        (self.bundle / "locales" / "en" / "inter.md").write_text(
            "english conduct\n", encoding="utf-8")
        (self.bundle / "locales" / "fr" / "inter.md").write_text(
            "conduite francaise\n", encoding="utf-8")

    def write_skill(self, text, name="demo"):
        path = self.bundle / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class TestLoadSkill(BundleCase):
    def test_front_matter_and_body_are_parsed(self):
        skill = load_skill(self.bundle, "demo")
        self.assertEqual(skill.name, "demo")
        self.assertEqual(skill.version, "0.1.0")
        self.assertIn("Not for", skill.description)
        self.assertTrue(skill.body.startswith("# Demo"))
        self.assertNotIn("version:", skill.body)

    def test_an_unknown_skill_is_refused_naming_the_known_ones(self):
        with self.assertRaises(SkillError) as caught:
            load_skill(self.bundle, "ghost")
        self.assertIn("demo", str(caught.exception))

    def test_missing_front_matter_key_is_an_error(self):
        self.write_skill('---\nname: demo\ndescription: "x. Not for y."\n---\n'
                         + BODY)
        with self.assertRaises(SkillError) as caught:
            load_skill(self.bundle, "demo")
        self.assertIn("version", str(caught.exception))

    def test_no_front_matter_at_all_is_an_error(self):
        self.write_skill(BODY)
        with self.assertRaises(SkillError):
            load_skill(self.bundle, "demo")

    def test_list_skills_names_the_directories(self):
        self.write_skill(FRONT + BODY, name="other")
        self.assertEqual(list_skills(self.bundle), ["demo", "other"])


class TestCitations(BundleCase):
    def test_placeholders_resolve_to_the_asked_language(self):
        found = citations(self.bundle, BODY, "fr")
        resolved = [c.resolved for c in found]
        self.assertIn("locales/fr/thing.md", resolved)
        self.assertNotIn("locales/en/thing.md", resolved)

    def test_a_citation_is_kept_once_in_first_seen_order(self):
        found = citations(self.bundle, BODY, "en")
        self.assertEqual([c.resolved for c in found],
                         ["references/one.md", "locales/en/thing.md",
                          "locales/en/inter.md", "references/two.md"])

    def test_a_language_gap_falls_back_to_english_and_says_so(self):
        (self.bundle / "locales" / "fr" / "thing.md").unlink()
        found = citations(self.bundle, BODY, "fr")
        thing = [c for c in found if c.cited == "locales/<lang>/thing.md"][0]
        self.assertEqual(thing.resolved, "locales/en/thing.md")
        self.assertTrue(thing.fallback)

    def test_a_dangling_literal_citation_is_an_error(self):
        with self.assertRaises(SkillError) as caught:
            citations(self.bundle, "see references/ghost.md", "en")
        self.assertIn("references/ghost.md", str(caught.exception))

    def test_a_placeholder_missing_in_english_too_is_an_error(self):
        with self.assertRaises(SkillError) as caught:
            citations(self.bundle, "see locales/<lang>/ghost.md", "fr")
        self.assertIn("ghost.md", str(caught.exception))


class TestSystemBlock(BundleCase):
    def test_the_block_is_the_body_then_every_cited_file(self):
        block = system_block(self.bundle, "demo", "fr")
        self.assertTrue(block.text.startswith("# Demo"))
        body_end = block.text.index("reference one text")
        self.assertLess(block.text.index("## Second step"), body_end)
        self.assertIn("chose francaise", block.text)
        self.assertIn("reference two text", block.text)
        self.assertEqual(block.text.count("reference one text"), 1)

    def test_every_cited_file_is_named_before_its_content(self):
        block = system_block(self.bundle, "demo", "fr")
        self.assertIn("references/one.md", block.text)
        self.assertLess(block.text.index("locales/fr/thing.md"),
                        block.text.index("chose francaise"))

    def test_front_matter_stays_out_of_the_block(self):
        block = system_block(self.bundle, "demo", "en")
        self.assertNotIn("version: 0.1.0", block.text)

    def test_the_body_keeps_its_placeholders(self):
        # A rewrite would have to pick one language axis per placeholder,
        # and the ambiguous ones cannot be picked mechanically. The headers
        # under the body carry the resolution instead.
        block = system_block(self.bundle, "demo", "fr")
        self.assertIn("locales/<lang>/thing.md", block.text)
        self.assertIn("===== locales/fr/thing.md", block.text)

    def test_a_fallback_is_announced_next_to_the_content(self):
        (self.bundle / "locales" / "fr" / "thing.md").unlink()
        block = system_block(self.bundle, "demo", "fr")
        marker = [line for line in block.text.splitlines()
                  if "locales/en/thing.md" in line and "fr" in line]
        self.assertTrue(marker, "the stand-in file is not announced")

    def test_selecting_sections_keeps_the_preamble_and_the_chosen_ones(self):
        block = system_block(self.bundle, "demo", "en",
                             sections=("Second step",))
        self.assertIn("# Demo", block.text)
        self.assertIn("## Second step", block.text)
        self.assertNotIn("## First step", block.text)

    def test_selected_sections_only_pull_their_own_citations(self):
        block = system_block(self.bundle, "demo", "en",
                             sections=("Second step",))
        resolved = [c.resolved for c in block.citations]
        self.assertIn("references/two.md", resolved)
        self.assertNotIn("locales/en/thing.md", resolved)

    def test_an_unknown_section_is_refused_naming_the_real_ones(self):
        with self.assertRaises(SkillError) as caught:
            system_block(self.bundle, "demo", "en", sections=("Third step",))
        self.assertIn("Second step", str(caught.exception))

    def test_sections_come_out_in_file_order_not_call_order(self):
        block = system_block(self.bundle, "demo", "en",
                             sections=("Second step", "First step"))
        self.assertLess(block.text.index("## First step"),
                        block.text.index("## Second step"))


class TestTwoLanguageAxes(BundleCase):
    """Interviewed in one language, published in another. The regression
    behind this class: a first cut resolved every placeholder to a single
    language, which either wrote the post against the wrong market pack or
    ran the interview from the wrong wording, depending on which language
    was passed."""

    def test_interface_placeholders_stay_on_the_interview_side(self):
        found = citations(self.bundle, BODY, "fr", "en")
        interface = [c for c in found
                     if c.cited == "locales/<interface_language>/inter.md"]
        self.assertEqual([c.resolved for c in interface],
                         ["locales/fr/inter.md"])

    def test_ambiguous_placeholders_resolve_to_both_languages(self):
        found = citations(self.bundle, BODY, "fr", "en")
        lang_cited = [c.resolved for c in found
                      if c.cited == "locales/<lang>/thing.md"]
        self.assertIn("locales/fr/thing.md", lang_cited)
        self.assertIn("locales/en/thing.md", lang_cited)

    def test_the_block_carries_both_packs(self):
        block = system_block(self.bundle, "demo", "fr", output_lang="en")
        self.assertIn("chose francaise", block.text)
        self.assertIn("english thing", block.text)
        self.assertIn("conduite francaise", block.text)
        self.assertNotIn("english conduct", block.text)

    def test_equal_languages_collapse_to_one_set(self):
        same = system_block(self.bundle, "demo", "fr", output_lang="fr")
        alone = system_block(self.bundle, "demo", "fr")
        self.assertEqual(same.text, alone.text)

    def test_the_shipped_post_skill_crosses_the_axes(self):
        block = system_block(REPO, "linkedin-post", "fr", output_lang="en")
        resolved = [c.resolved for c in block.citations]
        self.assertIn("locales/fr/interview.md", resolved)
        self.assertIn("locales/fr/style.md", resolved)
        self.assertIn("locales/en/style.md", resolved)
        self.assertIn("locales/en/market.md", resolved)
        # The interview wording is interface side only: English questions
        # injected into a French interview are the language leak itself.
        self.assertNotIn("locales/en/interview.md", resolved)


class TestSplitSections(unittest.TestCase):
    def test_preamble_and_sections_are_separated(self):
        found = split_sections(BODY)
        self.assertEqual([h for h, _ in found],
                         ["", "First step", "Second step"])
        self.assertIn("# Demo", found[0][1])
        self.assertIn("closes", found[2][1])


class TestShippedSkills(unittest.TestCase):
    """Every skill in the repository loads, and every file it cites exists,
    in both shipped languages. The measure.md incident, never again."""

    def test_the_three_skills_are_listed(self):
        self.assertEqual(list_skills(REPO),
                         ["linkedin-post", "linkedin-profile", "linkedin-setup"])

    def test_every_shipped_skill_builds_a_block_in_every_language(self):
        for name in list_skills(REPO):
            for lang in ("en", "fr"):
                block = system_block(REPO, name, lang)
                self.assertGreater(len(block.text), 1000, (name, lang))
                for cite in block.citations:
                    self.assertTrue((REPO / cite.resolved).is_file(),
                                    (name, lang, cite.resolved))
                    self.assertFalse(cite.fallback, (name, lang, cite.resolved))

    def test_the_post_skill_carries_the_anchoring_contract(self):
        block = system_block(REPO, "linkedin-post", "fr")
        self.assertIn("references/anchoring.md",
                      [c.resolved for c in block.citations])
        self.assertIn("ANCHORS", block.text)

    def test_the_post_skill_block_speaks_the_asked_language(self):
        block = system_block(REPO, "linkedin-post", "fr")
        self.assertIn("locales/fr/interview.md",
                      [c.resolved for c in block.citations])


class TestALanguageCodeIsAPathSegment(unittest.TestCase):
    """It comes out of somebody's profile and becomes a directory name."""

    def test_a_code_that_is_not_one_is_refused(self):
        for bad in ("../../etc", "\\1", "en/../..", "e", "toolongforacode",
                    "en;rm", ".", ""):
            with self.assertRaises(SkillError, msg=repr(bad)):
                citations(REPO, "locales/<lang>/style.md", bad)

    def test_the_codes_this_bundle_ships_are_accepted(self):
        for good in ("en", "fr"):
            found = citations(REPO, "locales/<lang>/style.md", good)
            self.assertEqual(found[0].resolved, f"locales/{good}/style.md")


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
