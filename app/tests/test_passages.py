"""Tests for verbatim_app.passages, a post cut into the blocks a reader sees.

This is `sections.py` for prose. A profile is addressed by its `## ` headings
and a post has none, so the unit is the block between blank lines: what a
reader scrolls past, and what somebody points at when they say this bit is
too vague.

The span is the whole point. A revision addressed to one block rewrites those
characters and leaves every other byte of the post where it was, which is a
guarantee by construction rather than a diff checked afterwards.

Runs with the standard library only:  python3 app/tests/test_passages.py
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app import passages  # noqa: E402
from verbatim_app.shown import shown  # noqa: E402

POST = """Quatre mois à vendre aux agences.

Onze conversations, deux propositions, rien de signé.

J'ai arrêté."""


class TestCuttingAPost(unittest.TestCase):
    def test_the_blocks_are_what_a_reader_scrolls(self):
        found = passages.passages_of(POST)
        self.assertEqual([p.text for p in found],
                         ["Quatre mois à vendre aux agences.",
                          "Onze conversations, deux propositions, rien de signé.",
                          "J'ai arrêté."])
        self.assertEqual([p.index for p in found], [0, 1, 2])

    def test_a_span_lands_on_its_own_characters(self):
        for passage in passages.passages_of(POST):
            self.assertEqual(POST[passage.start:passage.end], passage.text)

    def test_a_run_of_blank_lines_is_one_break(self):
        found = passages.passages_of("Un.\n\n\n\n   \n\nDeux.")
        self.assertEqual([p.text for p in found], ["Un.", "Deux."])
        self.assertEqual(found[1].text, "Deux.")

    def test_a_line_of_spaces_separates_like_a_blank_one(self):
        found = passages.passages_of("Un.\n   \nDeux.")
        self.assertEqual([p.text for p in found], ["Un.", "Deux."])

    def test_a_single_block_is_one_passage(self):
        self.assertEqual(len(passages.passages_of("Une seule ligne.")), 1)

    def test_a_block_of_several_lines_stays_one_passage(self):
        found = passages.passages_of("Une ligne\net sa suite.\n\nUne autre.")
        self.assertEqual(found[0].text, "Une ligne\net sa suite.")

    def test_nothing_is_no_passage(self):
        for empty in ("", "   ", "\n\n", "\n \n\t\n"):
            self.assertEqual(passages.passages_of(empty), [])

    def test_leading_and_trailing_blank_lines_shift_nothing(self):
        body = "\n\nUn.\n\nDeux.\n\n"
        found = passages.passages_of(body)
        self.assertEqual([p.text for p in found], ["Un.", "Deux."])
        for passage in found:
            self.assertEqual(body[passage.start:passage.end], passage.text)

    def test_the_digest_is_over_the_block_alone(self):
        found = passages.passages_of(POST)
        self.assertEqual(found[0].digest, shown(found[0].text))

    def test_a_post_that_came_off_another_machine_still_cuts(self):
        # CRLF. Without it the whole post is one block, the picker never
        # appears, and nothing says why.
        found = passages.passages_of("Un.\r\n\r\nDeux.\r\n\r\nTrois.")
        self.assertEqual([p.text for p in found], ["Un.", "Deux.", "Trois."])

    def test_a_crlf_span_lands_on_its_own_characters(self):
        body = "Un.\r\n\r\nDeux."
        for passage in passages.passages_of(body):
            self.assertEqual(body[passage.start:passage.end], passage.text)

    def test_a_single_newline_is_not_a_break(self):
        # A wrapped line is one paragraph, in both line ending styles.
        for body in ("Une ligne\net sa suite.", "Une ligne\r\net sa suite."):
            self.assertEqual(len(passages.passages_of(body)), 1)


class TestAddressingOne(unittest.TestCase):
    def test_the_index_says_which_and_the_digest_says_it_is_current(self):
        passage = passages.passage_at(POST, 1, shown(
            "Onze conversations, deux propositions, rien de signé."))
        self.assertEqual(passage.index, 1)

    def test_a_digest_that_no_longer_matches_is_refused(self):
        with self.assertRaises(passages.PassageGone):
            passages.passage_at(POST, 1, shown("what the screen used to show"))

    def test_an_index_past_the_end_is_refused(self):
        with self.assertRaises(passages.PassageGone):
            passages.passage_at(POST, 9, shown("Quatre mois à vendre aux agences."))

    def test_a_negative_index_is_refused(self):
        with self.assertRaises(passages.PassageGone):
            passages.passage_at(POST, -1, shown("J'ai arrêté."))

    def test_two_identical_blocks_are_still_addressable_by_index(self):
        # The digest cannot separate them; the index can. Refusing both would
        # make a post unrevisable over a repeated line.
        body = "Pareil.\n\nAutre.\n\nPareil."
        self.assertEqual(passages.passage_at(body, 2, shown("Pareil.")).start,
                         body.rindex("Pareil."))


class TestRewritingOne(unittest.TestCase):
    def test_every_other_byte_stays_where_it_was(self):
        passage = passages.passages_of(POST)[1]
        after = passages.replace_passage(POST, passage, "Onze conversations.")
        self.assertEqual(after, POST.replace(
            "Onze conversations, deux propositions, rien de signé.",
            "Onze conversations."))
        self.assertTrue(after.startswith("Quatre mois"))
        self.assertTrue(after.endswith("J'ai arrêté."))

    def test_the_replacement_is_trimmed_rather_than_padding_the_post(self):
        passage = passages.passages_of(POST)[0]
        after = passages.replace_passage(POST, passage, "\n\n  Court.  \n\n")
        self.assertTrue(after.startswith("Court.\n\n"))

    def test_a_replacement_may_itself_be_several_blocks(self):
        # Splitting one paragraph in two is a legitimate rewrite, and the
        # span does not care how many blocks land in it.
        passage = passages.passages_of(POST)[0]
        after = passages.replace_passage(POST, passage, "Un.\n\nDeux.")
        self.assertEqual(len(passages.passages_of(after)), 4)

    def test_a_span_that_no_longer_holds_its_text_is_refused(self):
        """The offsets are only true of the body they were read from.

        A model is allowed to call a tool twice in one message, and the
        second call arrives holding the first call's offsets. Splicing those
        into the body the first one rewrote lands in the middle of two other
        blocks: characters of one are eaten and the next is cut mid-word.
        The span carries its own text, so the check costs a comparison.
        """
        passage = passages.passages_of(POST)[1]
        after = passages.replace_passage(POST, passage, "Onze.")
        with self.assertRaises(passages.PassageGone):
            passages.replace_passage(after, passage, "Encore autre chose.")

    def test_a_stale_span_is_refused_when_the_rewrite_only_added_to_it(self):
        """The shape a comparison at the offsets cannot catch.

        An additive revision, "put the real number in", "expand this", comes
        back as the original block plus a sentence. The bytes at the stale
        span are then still exactly the original text, so anything checking
        content there says yes, and the second call welds its own text onto
        the first call's tail. What the span has to be checked for is being
        the same block, which is what its digest answers.
        """
        passage = passages.passages_of(POST)[1]
        after = passages.replace_passage(
            POST, passage, passage.text + " Douze clients en trois semaines.")
        with self.assertRaises(passages.PassageGone):
            passages.replace_passage(after, passage, "Autre chose.")

    def test_a_rewrite_that_split_the_block_in_two_closes_it(self):
        """The variant every indirect check misses.

        A first rewrite answers "put the real number in" with the original
        block, a blank line, and the added sentence. The block is now two,
        and the first of them is byte-identical to the original: its digest
        matches, its index matches, and a second call splices into it,
        leaving the added sentence orphaned below somebody else's paragraph.
        Nothing about the block itself says anything happened. What says it
        is the post.
        """
        passage = passages.passages_of(POST)[1]
        split = passages.replace_passage(
            POST, passage, passage.text + "\n\nDouze en trois semaines.")
        with self.assertRaises(passages.PassageGone):
            passages.replace_passage(split, passage, "Autre chose.")

    def test_a_body_this_passage_was_never_read_from_is_refused(self):
        # Identity of the post, not a proof about the block. Everything that
        # tried to infer "has a rewrite landed" from the block itself missed
        # a case, twice.
        passage = passages.passages_of(POST)[0]
        with self.assertRaises(passages.PassageGone):
            passages.replace_passage(POST + "\n\nUne ligne de plus.",
                                     passage, "Court.")

    def test_the_same_body_is_the_same_body(self):
        # No false refusal on the ordinary single call, and none on a
        # rewrite that changes nothing.
        passage = passages.passages_of(POST)[1]
        same = passages.replace_passage(POST, passage, passage.text)
        self.assertEqual(same, POST)
        self.assertEqual(passages.replace_passage(same, passage, "Onze."),
                         passages.replace_passage(POST, passage, "Onze."))

    def test_a_stale_span_is_refused_even_when_it_still_fits(self):
        # The offsets land inside the shorter body, so nothing would raise
        # on its own. What refuses is the text at them not being the text.
        passage = passages.passages_of(POST)[0]
        shorter = "Court.\n\nOnze conversations, deux propositions, rien.\n\nFin."
        with self.assertRaises(passages.PassageGone):
            passages.replace_passage(shorter, passage, "Autre chose.")

    def test_an_empty_rewrite_is_refused_rather_than_deleting_the_block(self):
        # Taking a passage out is a decision, and it is not this one. A model
        # answering with nothing must not silently shorten somebody's post.
        passage = passages.passages_of(POST)[0]
        for empty in ("", "   ", "\n\n"):
            with self.assertRaises(passages.PassageGone):
                passages.replace_passage(POST, passage, empty)


class TestWhatMovedBetweenTwoVersions(unittest.TestCase):
    """Which blocks are not the blocks of the version before.

    Read off the same cut the rest of this file is about, and by digest, so
    the answer is about the text a reader sees rather than about offsets
    that mean nothing across two bodies.
    """

    def test_only_the_rewritten_block_is_marked(self):
        after = passages.replace_passage(
            POST, passages.passages_of(POST)[1], "Onze conversations. Rien.")
        self.assertEqual(passages.changed(POST, after), {1})

    def test_a_post_rewritten_whole_marks_every_block(self):
        after = "Tout autre.\n\nEt encore autre.\n\nFin autre."
        self.assertEqual(passages.changed(POST, after), {0, 1, 2})

    def test_an_added_block_is_marked_and_its_neighbours_are_not(self):
        after = POST + "\n\nEt puis j'ai recommence."
        self.assertEqual(passages.changed(POST, after), {3})

    def test_a_removed_block_marks_nothing_that_stayed(self):
        # Nothing of what is left changed, so nothing of what is left is
        # marked. A deletion is visible by the post being shorter, and
        # painting its neighbours would say they moved when they did not.
        after = "Quatre mois \u00e0 vendre aux agences.\n\nJ'ai arr\u00eat\u00e9."
        self.assertEqual(passages.changed(POST, after), set())

    def test_a_reorder_is_a_change_and_something_carries_the_mark(self):
        # Two blocks swapped: every character of the post is where it was
        # and the post is not the same post. Which of the two carries the
        # mark is the matcher's to say; that neither does would be the
        # screen calling a real edit no edit at all.
        before = "Quatre mois \u00e0 vendre aux agences.\n\nJ'ai arr\u00eat\u00e9."
        after = "J'ai arr\u00eat\u00e9.\n\nQuatre mois \u00e0 vendre aux agences."
        self.assertTrue(passages.changed(before, after))

    def test_nothing_to_compare_against_marks_nothing(self):
        # A first draft is not news. Every block of it would be marked by any
        # rule that answers this from the post alone.
        self.assertEqual(passages.changed("", POST), set())

    def test_two_blocks_that_read_alike_are_told_apart_by_position(self):
        before = "Pareil.\n\nPareil.\n\nDifferent."
        after = "Pareil.\n\nPareil.\n\nAutre chose."
        self.assertEqual(passages.changed(before, after), {2})


class TestWhichBlockALineBelongsTo(unittest.TestCase):
    """The bridge between the two ways this post is cut.

    A screen paints the post line by line, `anchors.lines` does the cutting,
    and a version marker is about blocks. One list, in the order of
    `splitlines`, so an index in one is an index in the other.
    """

    def test_every_line_is_placed_and_the_blank_ones_are_not(self):
        self.assertEqual(passages.line_blocks(POST),
                         [0, None, 1, None, 2])

    def test_a_block_of_several_lines_places_all_of_them(self):
        post = "Une ligne.\nEt sa suite.\n\nUn autre bloc."
        self.assertEqual(passages.line_blocks(post), [0, 0, None, 1])

    def test_the_list_is_as_long_as_the_post_has_lines(self):
        for post in (POST, "", "Seul.", "A\n\n\n\nB", "A\r\n\r\nB"):
            self.assertEqual(len(passages.line_blocks(post)),
                             len(post.splitlines()), post)

    def test_a_line_placed_in_a_block_is_inside_that_block(self):
        post = "Une ligne.\nEt sa suite.\n\nUn autre bloc."
        found = passages.passages_of(post)
        for line, index in zip(post.splitlines(),
                               passages.line_blocks(post)):
            if index is not None:
                self.assertIn(line.strip(), found[index].text)

if __name__ == "__main__":
    unittest.main(verbosity=2)
