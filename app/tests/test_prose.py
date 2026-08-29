"""Tests for verbatim_app.prose, the validation sheet read out of an answer
that ignored its tool.

This path is not a nicety. `tool_choice` is enforced by the provider on the
native wire and advisory on an OpenAI compatible one: measured two calls out of
six on Ollama, see docs/smoke.md. Without this, asking for the sheet on a local
runtime does nothing visible most turns, and the guard the whole skill is built
on never fires.

The labels are the skill's own, in skills/linkedin-post/SKILL.md. A test pins
them there rather than trusting this file to stay in step.

Runs with the standard library only:  python3 app/tests/test_prose.py
"""

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app import prose  # noqa: E402

PLAIN = """ANGLE
Le segment abandonné, avec ce qu'il a coûté

CONCRETE ELEMENTS
- onze conversations
- deux propositions

THE STRONG MOMENT
rien de signé au bout de quatre mois

CENTRAL CONVICTION
"le canal direct est le seul qui paie"

FIRST LINE
- Quatre mois à vendre aux agences.
- Onze conversations, zéro contrat.
"""


class TestTheLabels(unittest.TestCase):
    def test_they_are_the_ones_the_shipped_skill_shows(self):
        # Structure, not instruction: the app names the shape the skill
        # defines, exactly as anchors.py names the ANCHORS block. A label
        # renamed in skills/ fails here rather than on somebody's screen.
        skill = (REPO / "skills" / "linkedin-post" / "SKILL.md").read_text(
            encoding="utf-8")
        block = re.search(r"```\n(ANGLE.*?)```", skill, re.DOTALL).group(1)
        shown = [line.split("  ")[0].strip() for line in block.splitlines()
                 if line.strip()]
        self.assertEqual(sorted(prose.LABELS.values()), sorted(shown))

    def test_the_field_names_are_the_ones_the_sheet_takes(self):
        # The keys are what `interview.propose` reads, so a rename on either
        # side has to break something. This is that something.
        self.assertEqual(
            sorted(prose.LABELS),
            sorted(["angle", "elements", "moment", "conviction",
                    "first_lines"]))


class TestReadingASheet(unittest.TestCase):
    def test_a_plain_answer_comes_back_whole(self):
        read = prose.sheet(PLAIN)
        self.assertEqual(read.fields["angle"],
                         "Le segment abandonné, avec ce qu'il a coûté")
        self.assertEqual(read.fields["elements"],
                         ["onze conversations", "deux propositions"])
        self.assertEqual(read.fields["moment"],
                         "rien de signé au bout de quatre mois")
        self.assertEqual(read.fields["conviction"],
                         "le canal direct est le seul qui paie")
        self.assertEqual(read.fields["first_lines"],
                         ["Quatre mois à vendre aux agences.",
                          "Onze conversations, zéro contrat."])
        self.assertEqual(read.problems, ())

    def test_the_quotes_the_skill_asks_for_come_off(self):
        # "in quotes, what they conclude". The tool called version carries no
        # quotes, and two sheets that say the same thing must look the same.
        self.assertEqual(prose.sheet(PLAIN).fields["conviction"],
                         "le canal direct est le seul qui paie")

    def test_markdown_decoration_does_not_hide_a_label(self):
        for decorated in ("## ANGLE", "**ANGLE**", "- ANGLE:", "1. ANGLE",
                          "ANGLE :", "**ANGLE :**", "### **ANGLE**"):
            text = PLAIN.replace("ANGLE\n", decorated + "\n", 1)
            self.assertEqual(prose.sheet(text).fields.get("angle"),
                             "Le segment abandonné, avec ce qu'il a coûté",
                             decorated)

    def test_a_value_on_the_label_line_is_the_value(self):
        text = PLAIN.replace(
            "ANGLE\nLe segment abandonné, avec ce qu'il a coûté",
            "ANGLE: Le segment abandonné, avec ce qu'il a coûté")
        self.assertEqual(prose.sheet(text).fields["angle"],
                         "Le segment abandonné, avec ce qu'il a coûté")

    def test_the_case_of_a_label_does_not_matter(self):
        self.assertTrue(prose.sheet(PLAIN.lower()).fields)

    def test_prose_around_the_block_is_not_part_of_it(self):
        text = ("Voici la fiche de validation que je propose.\n\n" + PLAIN
                + "\n\nDites-moi si cela vous convient.")
        read = prose.sheet(text)
        self.assertEqual(read.fields["angle"],
                         "Le segment abandonné, avec ce qu'il a coûté")
        # The trailing sentence follows the last label, so it lands in the
        # last field unless the parser stops at the blank line run. It does
        # not: first_lines is a bullet list, and a sentence is not a bullet.
        self.assertEqual(read.fields["first_lines"],
                         ["Quatre mois à vendre aux agences.",
                          "Onze conversations, zéro contrat."])

    def test_a_list_written_as_plain_lines_still_reads(self):
        text = PLAIN.replace("- onze conversations\n- deux propositions",
                             "onze conversations\ndeux propositions")
        self.assertEqual(prose.sheet(text).fields["elements"],
                         ["onze conversations", "deux propositions"])

    def test_a_wrapped_scalar_joins_into_one_line(self):
        text = PLAIN.replace(
            "rien de signé au bout de quatre mois",
            "rien de signé au bout\nde quatre mois")
        self.assertEqual(prose.sheet(text).fields["moment"],
                         "rien de signé au bout de quatre mois")


class TestWhatIsRefused(unittest.TestCase):
    """A partial sheet is worse than none. `propose` refuses a missing field
    anyway; guessing one here would be the invention the sheet exists to
    catch, wearing the sheet's own authority."""

    def test_an_answer_with_no_label_at_all_is_not_a_sheet(self):
        read = prose.sheet("Bien sûr, je peux préparer cela pour vous.")
        self.assertEqual(read.fields, {})
        self.assertTrue(read.problems)

    def test_a_missing_field_takes_the_whole_sheet_with_it(self):
        text = PLAIN.replace('CENTRAL CONVICTION\n"le canal direct est le '
                             'seul qui paie"\n', "")
        read = prose.sheet(text)
        self.assertEqual(read.fields, {})
        self.assertIn("CENTRAL CONVICTION", " ".join(read.problems))

    def test_a_label_with_nothing_under_it_is_missing(self):
        text = PLAIN.replace("THE STRONG MOMENT\nrien de signé au bout de "
                             "quatre mois", "THE STRONG MOMENT")
        read = prose.sheet(text)
        self.assertEqual(read.fields, {})
        self.assertIn("THE STRONG MOMENT", " ".join(read.problems))

    def test_an_empty_answer_is_not_a_sheet(self):
        for nothing in ("", "   ", "\n\n"):
            self.assertEqual(prose.sheet(nothing).fields, {})

    def test_a_label_said_twice_keeps_the_first_and_says_so(self):
        # Two angles is a model padding, and picking the later one would let
        # it quietly overwrite what it already committed to.
        text = PLAIN + "\nANGLE\nUn autre angle entièrement\n"
        read = prose.sheet(text)
        self.assertEqual(read.fields["angle"],
                         "Le segment abandonné, avec ce qu'il a coûté")
        self.assertIn("ANGLE", " ".join(read.problems))

    def test_more_than_two_first_lines_is_reported_not_trimmed(self):
        # The sheet takes at most two. Silently dropping the third would hide
        # a proposal the person never got to see.
        text = PLAIN + "- Une troisième proposition.\n"
        read = prose.sheet(text)
        self.assertEqual(len(read.fields.get("first_lines", [])), 3)
        self.assertTrue(read.problems)


class TestWhatItHandsOn(unittest.TestCase):
    def test_the_fields_are_what_propose_takes(self):
        from verbatim_app import interview
        conversation = interview.Conversation(
            id="2026-08-29-1200", skill="linkedin-post", sections=(),
            interface_language="fr", output_language="fr",
            provider="openai", model="qwen2.5:14b",
            started="", updated="")
        read = prose.sheet(PLAIN)
        sheet = interview.propose(conversation, read.fields,
                                  problems=["read out of prose"])
        self.assertEqual(sheet.angle, read.fields["angle"])
        self.assertEqual(sheet.problems, ("read out of prose",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
