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

#: The set the ladder climbs, holding both the rungs and, under a heading of
#: its own, the rules they run under. The default ceiling is one of those.
CLIMBED_SET = "Set B. Post interview"

#: The ladder columns that name a rung, read by heading rather than by
#: position. The row carries how far the climb goes beside the order it goes
#: in, and a parser taking every id after the format would count a depth
#: written in backticks as one more rung. `Then` repeats on purpose.
RUNGS = ("Enters on", "Then")

#: The two columns that say how far a format climbs, and which way a turn
#: breaks when the material is arguably enough and arguably not.
CEILING, PRESUMED = "Ceiling", "Presumed"

#: The presumptions a row can carry, shallowest first. The order is the
#: point and not a listing convenience: a presumption is not a second
#: opinion about a format, it follows the ceiling, and a test reads this
#: tuple as the order the rows have to come in.
PRESUMPTIONS = ("short", "deep")

#: Small numbers, because the bundle spells them and a table counts them. A
#: test comparing the two has to cross that, and doing it here is cheaper
#: than writing a digit into prose that says `Six is the ceiling`.
WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}

#: The ceiling before a format is settled, read off the rule that states it
#: rather than repeated here. The break happens after the first or second
#: answer, so every interview runs its opening turns under this number.
DEFAULT = re.compile(r"\*\*(\w+) is the ceiling until the format is settled")

#: How many rungs the set says it has, in the sentence that opens it. The
#: `#` column is the count; this is somebody writing it out again above.
COUNTED = re.compile(r"^(\w+) rungs, and two doors into the first one", re.M)

#: The same ceiling, restated where a model and a reader meet it: the skill
#: body the engine sends, and the front page somebody arrives on. Both spell
#: it out, neither is read by any module, and a number written in three
#: files is three numbers unless something holds them to each other.
RESTATED = (
    ("skills/linkedin-post/SKILL.md",
     re.compile(r"^- (\w+) is the ceiling until the format sets its own", re.M)),
    ("README.md", re.compile(r"(\w+) turns at the outside")),
)

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


def _table(body: str = "") -> tuple:
    """The ladder table as (header cells, format rows).

    The header is the row opening on `Format`, and a format row is one
    opening on a bare id, which is how the separator, the prose and the rule
    under the table all stay out of it. Takes a body so the parser can be
    tested on a table somebody wrote for the test rather than only on the one
    in the file.
    """
    if not body:
        body = sections(INTENTS.read_text(encoding="utf-8"))[LADDER]
    header, rows = [], []
    for line in body.splitlines():
        row = cells(line)
        if not row:
            continue
        if not header:
            if row[0] == "Format":
                header = row
        elif CELL.match(row[0]):
            rows.append(row)
    return header, rows


def _under(header: list, row: list, name: str) -> list:
    """The cells under every column with this heading, in table order."""
    return [row[at] for at, cell in enumerate(header)
            if cell == name and at < len(row)]


def ladder(body: str = "") -> dict:
    """The per format ladder: {format: (rung, ...)}, entry cell to last.

    Read by column heading. The row says how far the climb goes as well as
    what order it goes in, so a parser taking every id on it would count a
    depth written in backticks as one more rung and the map would still look
    green.
    """
    header, rows = _table(body)
    found = {}
    for row in rows:
        climbed = [CELL.match(cell) for name in RUNGS
                   for cell in _under(header, row, name)]
        found[CELL.match(row[0]).group(1)] = tuple(
            match.group(1) for match in climbed if match)
    return found


def depth(body: str = "") -> dict:
    """How far each format climbs and which way it leans, as
    {format: (ceiling, presumed)}, both verbatim.

    A column the row stops short of comes back empty rather than absent: a
    half filled row is something to fail on, not something to raise on.
    """
    header, rows = _table(body)
    found = {}
    for row in rows:
        said = [_under(header, row, name) for name in (CEILING, PRESUMED)]
        found[CELL.match(row[0]).group(1)] = tuple(
            cell[0] if cell else "" for cell in said)
    return found


def set_b_rows() -> list:
    """The rows of the set B table, each opening on its `#` and naming one
    rung. The rule bullets below the table are not rows and the separator
    does not open on a digit, so neither reaches here."""
    body = sections(INTENTS.read_text(encoding="utf-8"))[CLIMBED_SET]
    return [row for line in body.splitlines()
            for row in [cells(line)]
            if len(row) > 1 and row[0].isdigit() and CELL.match(row[1])]


def rungs() -> int:
    """How many rungs the post interview has, counted off the `#` column and
    not off the ids: rung 1 has two doors and taking one closes the other, so
    seven intents are six rungs."""
    return len({row[0] for row in set_b_rows()})


def counted() -> int:
    """How many rungs the prose above the table says there are. A fourth
    copy of the same number, and the one inside the file everything else
    here is anchored to."""
    body = sections(INTENTS.read_text(encoding="utf-8"))[CLIMBED_SET]
    said = COUNTED.search(body)
    return WORDS.get(said.group(1).lower(), 0) if said else 0


def default_ceiling(body: str = "") -> int:
    """The ceiling an interview runs under before a format is settled, read
    off the rule that states it. No assertion below names the number, which
    is what would make this file the second copy it exists to catch; the
    rules body is the argument only so the parser can be tested on one."""
    if not body:
        body = sections(INTENTS.read_text(encoding="utf-8"))[CLIMBED_SET]
    said = DEFAULT.search(body)
    return WORDS[said.group(1).lower()] if said else 0


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

    def test_a_column_that_is_not_a_rung_is_not_read_as_one(self):
        """The ladder row carries how far the climb goes beside the order it
        goes in, and both are cells on the one row. A parser taking every id
        after the format would read a depth as a further rung, and the map
        would still look green."""
        table = ("| Format | Enters on | Then | Ceiling | Presumed |\n"
                 "|---|---|---|---|---|\n"
                 "| `the-story` | `scene` | `number` | `six` | `deep` |")
        self.assertEqual(ladder(table), {"the-story": ("scene", "number")})
        # Backticked here because that is the hazard, and verbatim on the way
        # out because reading a depth is not the same job as reading an id:
        # what the real table may put in that cell is its own test.
        self.assertEqual(depth(table), {"the-story": ("`six`", "`deep`")})

    def test_a_row_that_stops_short_reads_empty_rather_than_raising(self):
        """So a half filled row fails the test that says a climb states both,
        and says which half is missing, instead of coming out as an index
        error from a parser."""
        table = ("| Format | Enters on | Ceiling | Presumed |\n"
                 "|---|---|---|---|\n"
                 "| `the-story` | `scene` |")
        self.assertEqual(depth(table), {"the-story": ("", "")})

    def test_the_default_ceiling_is_read_and_not_assumed(self):
        """Both branches, on a rule written here rather than on the real
        one: a parser falling back to a number of its own would prove the
        agreement it is asked to check, and the real file is read by
        `test_it_is_the_whole_ladder`, which names no number either."""
        self.assertEqual(
            default_ceiling("- **Four is the ceiling until the format is "
                            "settled** and never a target."), 4)
        self.assertEqual(default_ceiling("- the ceiling is four."), 0)

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
        for name, climb in ladder().items():
            with self.subTest(format=name):
                self.assertTrue(climb, "a format with an empty climb")
                unknown = [rung for rung in climb if rung not in known]
                self.assertEqual(unknown, [], "a rung no intent declares")

    def test_the_story_climbs_in_the_order_the_ladder_was_written_in(self):
        """The one order that was measured before it was written down."""
        self.assertEqual(ladder()["the-story"],
                         ("scene", "friction", "number", "position"))

    def test_set_b_is_one_list_and_not_two(self):
        """The set is read twice, down the rows and by the `#` column, and
        the prose above the table talks about `the list`. If the two ever
        disagree there is no such thing as the listing order, and a sentence
        about it is true or false depending on which one the reader took.

        Read as the column never going backwards, which is the whole of the
        agreement and is all of it that is defined: rung 1 has two doors,
        the file says taking one closes the other, and nothing orders them
        against each other. Sorting would have invented that order and
        failed on a swap that means nothing.
        """
        numbered = [int(row[0]) for row in set_b_rows()]
        self.assertEqual(numbered, sorted(numbered),
                         "the `#` column runs against the rows")

    def test_the_list_takes_number_first_and_the_story_takes_friction(self):
        """The exact pair the prose above the table names. Asserting only
        that the two sequences differ is a wider net with a hole in it:
        somebody reordering `position` instead leaves them unequal, this
        green, and the sentence about `friction` and `number` false. The
        renumbering half is the test above; this is the reorder half.
        """
        listed = intents(CLIMBED)
        climb = ladder()["the-story"]
        self.assertLess(listed.index("number"), listed.index("friction"),
                        "the list no longer takes `number` first")
        self.assertLess(climb.index("friction"), climb.index("number"),
                        "the story no longer takes `friction` first")

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


class TestTheDefaultCeiling(unittest.TestCase):
    """The number an interview runs under before it has a format, which is
    every interview for its first turn or two."""

    def test_the_set_counts_its_own_rungs_right(self):
        """The sentence opening set B says how many rungs it has, and the
        `#` column is the rungs. Somebody adding a seventh moves the column
        and the ceilings that answer to it, and that sentence stays where it
        was, saying six."""
        self.assertEqual(counted(), rungs())

    def test_the_doors_are_two_and_they_are_into_the_first_rung(self):
        """The same sentence says six rungs *and two doors into the first
        one*, and counting the rungs holds only the first half. A tie moved
        anywhere else down the column leaves six distinct rungs, passes
        every count, and leaves that sentence describing a table it no
        longer matches.
        """
        numbers = [int(row[0]) for row in set_b_rows()]
        twice = sorted(n for n in set(numbers) if numbers.count(n) > 1)
        self.assertEqual(twice, [min(numbers)], "the doors are not rung 1")
        self.assertEqual(numbers.count(min(numbers)), 2, "not two doors")

    def test_it_is_the_whole_ladder(self):
        """Six is not a round number somebody liked. It is every rung there
        is, which is what lets an interview that has not settled a format
        run under it without prejudging one."""
        self.assertEqual(default_ceiling(), rungs())

    def test_it_is_the_same_number_everywhere_it_is_stated(self):
        """The reference is pinned to the rungs, so moving it means moving
        them. The skill is what the engine actually sends and the README is
        what a reader arrives on, and neither would follow: they would go on
        stating a ceiling the ladder no longer has, and every test here
        would stay green while the model read the old number."""
        for name, pattern in RESTATED:
            with self.subTest(file=name):
                said = pattern.search(
                    (REPO / name).read_text(encoding="utf-8"))
                self.assertIsNotNone(said, "the ceiling is not stated here")
                self.assertEqual(WORDS.get(said.group(1).lower()),
                                 default_ceiling())


class TestHowFarEachFormatClimbs(unittest.TestCase):
    """The ceiling is not one number for every format, and the row that says
    what a format climbs is where it says how far.

    A stance arrives with its thesis already said and its climb ends at the
    objection; a story is still being told at the sixth rung. One length run
    over both either closes a story early or keeps asking a stance for
    material its format never had a rung for, which is the second way an
    interview talks somebody into inventing something.
    """

    def test_a_climb_states_both_how_far_and_which_way_it_leans(self):
        for name, (ceiling, presumed) in depth().items():
            with self.subTest(format=name):
                self.assertTrue(ceiling, "a climb with no ceiling")
                self.assertTrue(presumed, "a ceiling with no presumption")

    def test_the_ceiling_is_a_count_of_rungs(self):
        for name, (ceiling, _) in depth().items():
            with self.subTest(format=name):
                self.assertRegex(ceiling, r"\A[0-9]+\Z")

    def test_the_presumption_is_one_of_the_two(self):
        for name, (_, presumed) in depth().items():
            with self.subTest(format=name):
                self.assertIn(presumed, PRESUMPTIONS)

    def test_each_presumption_is_explained_under_the_table(self):
        """One word in a cell decides which way a turn breaks, and the word
        alone does not say that. A presumption nobody defined is a cell a
        model reads as decoration."""
        body = sections(INTENTS.read_text(encoding="utf-8"))[LADDER]
        for word in PRESUMPTIONS:
            with self.subTest(presumed=word):
                self.assertIn(f"`{word}`", body)

    def test_the_story_climbs_the_whole_ladder(self):
        """Said twice in prose and held nowhere: the six rungs above are the
        story's, and the story is what does not stop before the end of them.
        Everything else about that number is a comparison, so a story
        quietly dropped to five would leave two sentences wrong and the only
        red in the repo would be a dollar figure on a cost estimate.
        """
        self.assertEqual(int(depth()["the-story"][0]), rungs())

    def test_the_stance_stops_where_its_row_stops(self):
        """The other half of the same sentence, and the half that had only
        `TURNS` beside it: a stance nudged to five moves the span, somebody
        follows the red to `TURNS` and moves that instead, and two files go
        on saying a stance ends where its row does.
        """
        self.assertEqual(int(depth()["the-stance"][0]),
                         len(ladder()["the-stance"]))

    def test_a_stance_stops_before_a_story(self):
        """Half of it in one line, and the reason the ceiling column exists.
        The tiers Alchie offers halve between the two formats, and our own
        stance row ends where the story keeps climbing."""
        ceilings = {name: int(pair[0]) for name, pair in depth().items()}
        self.assertLess(ceilings["the-stance"], ceilings["the-story"])

    def test_the_shallower_climb_is_the_one_presumed_short(self):
        """The other half, and the one with nothing else watching it. The
        presumption is not free of the ceiling: a format that stops earlier
        is the one that leans towards stopping, and a pair swapped between
        two rows reads as sound as this one. Written the wrong way round it
        would keep asking a stance for material its format has no rung for,
        which is the whole of what B3 came out of.
        """
        low, high = PRESUMPTIONS
        at = {name: [int(ceiling) for ceiling, presumed in depth().values()
                     if presumed == name] for name in PRESUMPTIONS}
        self.assertTrue(at[low] and at[high], "every row leans the same way")
        # Strictly, so two formats stopping at the same rung cannot lean
        # opposite ways: the presumption follows the ceiling, and a tie
        # leaning both ways would mean it does not.
        self.assertLess(max(at[low]), min(at[high]),
                        f"a climb presumed {high} stops no later than one "
                        f"presumed {low}")

    def test_no_climb_stops_short_of_its_own_row(self):
        """A row naming four rungs and stopping at three is a ladder that
        cannot be climbed, and the interview would meet the ceiling with a
        rung still written beside it."""
        for name, climb in ladder().items():
            with self.subTest(format=name):
                self.assertGreaterEqual(int(depth()[name][0]), len(climb))

    def test_no_climb_asks_for_a_rung_that_does_not_exist(self):
        """A ceiling is a count of rungs, and there are six of them. Seven
        would be a turn with no intent behind it, which is the question a
        form asks and this does not."""
        for name, (ceiling, _) in depth().items():
            with self.subTest(format=name):
                self.assertLessEqual(int(ceiling), rungs())


if __name__ == "__main__":
    unittest.main(verbosity=2)
