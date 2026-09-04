"""Tests for the interview contract, which lives in the bundle and not in code.

Files that have to agree while no module reads any of them: the intents in
`references/interview-intents.md`, the ladder map in that same file, and the
wording packs under `locales/`. A model reads all of them at run time, so a
disagreement never crashes anything. It comes out as a rung named in a ladder
that no intent declares, or a wording nobody uses, and the only symptom is a
worse interview.

The map is keyed on `archive.FORMATS`, which is where the five formats were
already slugged and is what every archived post carries in its front matter.
A second spelling of the same five, invented here because it read better in a
table, would be the kind of divergence somebody reconciles by hand a year
later. `test_archive.py` pins that tuple against `references/formats.md`, so
this file leans on it rather than parsing the prose a second time.

What is a rule here and what is not, because the packs settle it themselves.
A pack may leave an intent unworded: the model writes one from the intent and
says out loud that it did, which is degradation announced rather than hidden.
So a missing section is legal and is not tested. A section whose heading is
not an intent is the opposite case: the wording is invisible, the model
generates one anyway, and whoever wrote that section believes it is in use.
The template is held tighter than a pack, because it is the checklist a new
pack gets filled from. An intent absent from it is an intent no translator is
ever shown.

Runs with the standard library only:  python3 app/tests/test_intents.py
"""

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app.archive import FORMATS  # noqa: E402

INTENTS = REPO / "references" / "interview-intents.md"
LOCALES = REPO / "locales"

#: A cell holding an id and nothing else. A cell naming two of them, or one
#: inside a sentence, is prose about ids and not a declaration of one.
CELL = re.compile(r"\A`([a-z][a-z0-9-]*)`\Z")

#: The sections that declare intents. Everything else in that file talks
#: about them, the ladder map included, and a parser harvesting those too
#: would let the map stand as its own proof.
DECLARING = re.compile(r"\ASet ([ABC])\b")

#: The set the post interview climbs. A ladder is checked against this one
#: and not against every intent the bundle declares: `thesis` is a real id,
#: it is a setup question, and a ladder row naming it would be a post
#: interview asking a question that belongs to another skill.
CLIMBED = "B"

#: An id anywhere inside a run of prose, for the sentence naming the formats
#: that deliberately have no ladder.
ANYWHERE = re.compile(r"`([a-z][a-z0-9-]*)`")

#: The section carrying the per format ladder, in the same file.
LADDER = "Where the interview breaks once, on purpose"

#: The packs that ship. `_template` is checked by its own test, against a
#: stricter rule.
SHIPPED = ("en", "fr")


def sections(text: str) -> dict:
    """The `##` sections of a markdown file, as {title: body}."""
    found, title, body = {}, None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if title is not None:
                found[title] = "\n".join(body)
            title, body = line[3:].strip(), []
        elif title is not None:
            body.append(line)
    if title is not None:
        found[title] = "\n".join(body)
    return found


def cells(line: str) -> list:
    """The cells of a markdown table row, or nothing if it is not one."""
    if not line.lstrip().startswith("|"):
        return []
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def declared(body: str) -> list:
    """Every id declared by a table row in this body, in order.

    One row declares at most one id: the first cell that is an id and nothing
    else. The columns around it hold prose, and that prose has backticks of
    its own.
    """
    found = []
    for line in body.splitlines():
        for cell in cells(line):
            match = CELL.match(cell)
            if match:
                found.append(match.group(1))
                break
    return found


def intents(which: str = "") -> list:
    """The intents the bundle declares, all of them or one set's worth."""
    found = []
    for title, body in sections(INTENTS.read_text(encoding="utf-8")).items():
        match = DECLARING.match(title)
        if match and which in ("", match.group(1)):
            found += declared(body)
    return found


def unwritten() -> list:
    """The formats the ladder section names as having no row, read off the
    sentence that says so. Prose, and checked like everything else: a
    misspelling there is a format somebody looks for and does not find."""
    body = sections(INTENTS.read_text(encoding="utf-8"))[LADDER]
    said = re.search(r"^(`[^`]+`[^.]*?) have no row\s*\n?\s*here, on purpose",
                     body, re.M)
    return ANYWHERE.findall(said.group(1)) if said else []


def ladder() -> dict:
    """The per format ladder: {format: (rung, ...)}, entry cell to last.

    A row that does not open on an id is not a ladder row, which is how the
    header and the rule under the table stay out of it.
    """
    rows = {}
    for line in sections(
            INTENTS.read_text(encoding="utf-8"))[LADDER].splitlines():
        row = [CELL.match(cell) for cell in cells(line)]
        if row and row[0]:
            rows[row[0].group(1)] = tuple(
                match.group(1) for match in row[1:] if match)
    return rows


def worded(pack: str) -> list:
    """The intents a pack writes a question for, by its `###` headings."""
    path = LOCALES / pack / "interview.md"
    return [line[4:].strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("### ")]


class TestTheParserItself(unittest.TestCase):
    """It has to be wrong out loud rather than harvest half a file. Every
    test below reads whatever this returns, so a parser that quietly found
    nothing would turn all of them green on an empty set."""

    def test_a_row_declares_its_first_bare_id(self):
        self.assertEqual(
            declared("| 1 | `scene` | `number` is the next one |"), ["scene"])

    def test_a_separator_declares_nothing(self):
        self.assertEqual(declared("|---|---|---|"), [])

    def test_an_id_inside_a_sentence_declares_nothing(self):
        self.assertEqual(
            declared("| Seeks | what `scene` did not give |"), [])

    def test_a_cell_naming_two_declares_neither(self):
        self.assertEqual(declared("| `scene` or `witnessed-instance` |"), [])

    def test_prose_outside_a_table_declares_nothing(self):
        self.assertEqual(declared("The `scene` rung comes first."), [])

    def test_the_three_sets_are_all_found(self):
        found = intents()
        for known in ("false-belief", "scene", "proof-pick"):
            self.assertIn(known, found)
        self.assertEqual(len(found), len(set(found)), "an id declared twice")


class TestTheTemplateIsTheChecklist(unittest.TestCase):
    def test_every_intent_is_listed_in_the_template(self):
        """A pack author fills the template. An intent that is not in it is
        an intent nobody is ever asked to word, in any language."""
        missing = [name for name in intents() if name not in worded("_template")]
        self.assertEqual(missing, [], "intents no translator is shown")


class TestNoPackWordsAGhost(unittest.TestCase):
    def test_every_heading_in_a_pack_is_a_real_intent(self):
        """The failure this catches is a heading typo. The pack looks
        written, the intent has no wording, the model generates one, and the
        line that says so scrolls past somebody who wrote that section
        yesterday."""
        known = set(intents())
        for pack in SHIPPED + ("_template",):
            with self.subTest(pack=pack):
                ghosts = [name for name in worded(pack) if name not in known]
                self.assertEqual(ghosts, [], f"{pack} words no such intent")


class TestTheLadderMap(unittest.TestCase):
    def test_it_names_only_formats_that_exist(self):
        unknown = [name for name in ladder() if name not in FORMATS]
        self.assertEqual(unknown, [], "a ladder for no format")

    def test_it_names_only_rungs_that_exist(self):
        known = set(intents(CLIMBED))
        for name, rungs in ladder().items():
            with self.subTest(format=name):
                self.assertTrue(rungs, "a format with an empty climb")
                unknown = [rung for rung in rungs if rung not in known]
                self.assertEqual(unknown, [], "a rung no intent declares")

    def test_the_story_climbs_in_the_order_the_ladder_was_written_in(self):
        """The one order that was measured before it was written down."""
        self.assertEqual(ladder()["the-story"],
                         ("scene", "friction", "number", "position"))

    def test_the_formats_left_out_are_named_and_spelled_right(self):
        """The three without a row are named in prose, and that prose is the
        only place somebody reads to know the absence was a decision. A
        typo there points at a format that does not exist, and the map
        itself would still be green."""
        left_out = unwritten()
        self.assertEqual(sorted(left_out),
                         sorted(set(FORMATS) - set(ladder())))
        for name in left_out:
            self.assertIn(name, FORMATS)

    def test_the_stance_does_not_open_on_a_scene(self):
        """The whole reason the map exists. A stance starts from a thesis,
        and asking it for a scene it never had is how an interview invents
        one."""
        climb = ladder()["the-stance"]
        self.assertNotEqual(climb[0], "scene")
        self.assertIn("witnessed-instance", climb)
        self.assertNotIn("scene", climb)


if __name__ == "__main__":
    unittest.main(verbosity=2)
