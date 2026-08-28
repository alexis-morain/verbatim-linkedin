"""Tests for the anchoring shape and the literal check over it.

references/anchoring.md is the contract. The machine verifies that a quote
is in the transcript, never that a claim is true, and typography is the only
forgiveness in the comparison.

    python3 app/tests/test_anchors.py
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app.anchors import (  # noqa: E402
    Anchor, contains, split_output, uncovered, verify,
)

DRAFT = ("I sold my first audit before writing a single line of code.\n\n"
         "The client signed for the result, not for the tool.")

TRANSCRIPT = ("Alors en fait j'ai vendu l'audit avant même d'écrire le "
              "script. Le client s'en fichait de l'outil, il voulait le "
              "résultat.")

BLOCK = (DRAFT + "\n\nANCHORS\n"
         "POST: The client signed for the result, not for the tool.\n"
         "SAID: il voulait le résultat\n")


class TestSplitOutput(unittest.TestCase):
    def test_no_block_means_the_whole_text_is_the_draft(self):
        out = split_output(DRAFT)
        self.assertEqual(out.draft, DRAFT)
        self.assertEqual(out.anchors, ())
        self.assertEqual(out.problems, ())

    def test_the_block_is_split_off_and_parsed(self):
        out = split_output(BLOCK)
        self.assertEqual(out.draft, DRAFT)
        self.assertEqual(out.anchors, (Anchor(
            fragment="The client signed for the result, not for the tool.",
            quote="il voulait le résultat"),))
        self.assertEqual(out.problems, ())

    def test_list_markers_and_case_are_tolerated(self):
        out = split_output(DRAFT + "\n\nANCHORS\n"
                           "- POST: The client signed for the result, not for the tool.\n"
                           "  said: il voulait le résultat\n")
        self.assertEqual(len(out.anchors), 1)
        self.assertEqual(out.anchors[0].quote, "il voulait le résultat")

    def test_surrounding_quotes_are_shed(self):
        out = split_output(DRAFT + "\n\nANCHORS\n"
                           'POST: "The client signed for the result, not for the tool."\n'
                           "SAID: « il voulait le résultat »\n")
        self.assertEqual(out.anchors[0].fragment,
                         "The client signed for the result, not for the tool.")
        self.assertEqual(out.anchors[0].quote, "il voulait le résultat")

    def test_the_word_anchors_inside_a_sentence_is_not_the_marker(self):
        text = "This post is about ANCHORS in cooking.\n\nDone."
        out = split_output(text)
        self.assertEqual(out.draft, text)

    def test_the_last_marker_line_wins(self):
        text = ("ANCHORS\n\nA draft that opens on the word.\n\nANCHORS\n"
                "POST: A draft that opens on the word.\n"
                "SAID: le premier mot du brouillon\n")
        out = split_output(text)
        self.assertEqual(len(out.anchors), 1)
        self.assertIn("A draft that opens", out.draft)

    def test_a_decorated_marker_still_opens_the_block(self):
        # The regression: a model writing '## ANCHORS' or 'ANCHORS:' lost
        # the whole block into the draft, with zero anchors and zero
        # problems. Silence was exactly what this parser promised not to do.
        for marker in ("## ANCHORS", "ANCHORS:", "anchors", "**ANCHORS**"):
            out = split_output(DRAFT + f"\n\n{marker}\n"
                               "POST: The client signed for the result\n"
                               "SAID: il voulait le résultat\n")
            self.assertEqual(len(out.anchors), 1, marker)
            self.assertEqual(out.draft, DRAFT, marker)

    def test_an_unreadable_marker_leaves_loud_strays_not_silence(self):
        out = split_output(DRAFT + "\n\nANCHOR\n"
                           "POST: The client signed for the result\n"
                           "SAID: il voulait le résultat\n")
        self.assertEqual(out.anchors, ())
        self.assertEqual(len(out.problems), 2)
        self.assertTrue(all("outside the anchors block" in p
                            for p in out.problems))

    def test_a_decorated_word_alone_in_the_draft_stays_in_the_draft(self):
        # The regression: the tolerant marker ate everything after a bold
        # or lowercase 'anchors' standing in the prose, and reported the
        # model's own closing sentence as a malformed entry.
        text = "Everything hangs on one word.\n\n**anchors**\n\nThat is it."
        out = split_output(text)
        self.assertEqual(out.draft, text)
        self.assertEqual(out.anchors, ())
        self.assertEqual(out.problems, ())

    def test_a_colon_inside_the_bold_stars_still_opens_the_block(self):
        out = split_output(DRAFT + "\n\n**ANCHORS:**\n"
                           "POST: The client signed for the result\n"
                           "SAID: il voulait le résultat\n")
        self.assertEqual(len(out.anchors), 1)
        self.assertEqual(out.draft, DRAFT)

    def test_prose_lines_opening_on_post_or_said_are_not_strays(self):
        # The regression: the stray detector reused the block's tolerant
        # entry pattern and flagged ordinary prose. Outside a block the
        # seam is read strictly, capitals and all.
        text = "Post: my three rules.\nSaid: nothing, ever."
        out = split_output(text)
        self.assertEqual(out.problems, ())
        self.assertEqual(out.draft, text)

    def test_a_degenerate_entry_is_reported_never_counted(self):
        # One letter is found in any draft and any transcript; an anchor
        # that cannot miss is an alarm that cannot ring.
        out = split_output(DRAFT + "\n\nANCHORS\n"
                           "POST: a\nSAID: il voulait le résultat\n"
                           "POST: The client signed for the result\nSAID: .\n")
        self.assertEqual(out.anchors, ())
        self.assertEqual(sum("too short" in p for p in out.problems), 2)

    def test_prose_entries_below_a_decorated_word_do_not_make_it_a_marker(self):
        # The regression: the decorated marker gate read entries with the
        # tolerant in-block pattern, so a prose 'Post:' line below a bold
        # word cost the draft its tail.
        text = ("Everything hangs on one word.\n\n**anchors**\n\n"
                "Post: my three rules.\n\nThat is it.")
        out = split_output(text)
        self.assertEqual(out.draft, text)
        self.assertEqual(out.anchors, ())
        self.assertEqual(out.problems, ())

    def test_a_decorated_marker_with_unreadable_entries_is_loud_not_eaten(self):
        # Neither silence nor a split: the draft keeps every line and the
        # reader is told the marker shaped line left residue behind it.
        text = ("Draft here ok friend.\n\n## ANCHORS\n\n"
                "POST - my claim here\nSAID - sa citation ici")
        out = split_output(text)
        self.assertEqual(out.draft, text)
        self.assertEqual(out.anchors, ())
        self.assertEqual(len(out.problems), 1)
        self.assertIn("## ANCHORS", out.problems[0])

    def test_numbered_stranded_entries_are_still_reported(self):
        out = split_output("A draft line.\n\nANCHOR\n"
                           "1. POST: The client signed for the result\n"
                           "2. SAID: il voulait le résultat\n")
        self.assertEqual(len(out.problems), 2)

    def test_one_rejected_post_makes_one_problem_not_two(self):
        out = split_output(DRAFT + "\n\nANCHORS\n"
                           "POST: non\nSAID: il voulait le résultat\n")
        self.assertEqual(out.anchors, ())
        self.assertEqual(len(out.problems), 1)
        self.assertIn("too short", out.problems[0])

    def test_entries_stranded_before_the_real_block_are_reported(self):
        text = (DRAFT + "\n\nANCHORS\nPOST: stranded\nSAID: perdu\n"
                "\nANCHORS\n"
                "POST: The client signed for the result\n"
                "SAID: il voulait le résultat\n")
        out = split_output(text)
        self.assertEqual(len(out.anchors), 1)
        self.assertTrue(any("stranded" in p for p in out.problems))

    def test_a_said_without_a_post_is_a_problem(self):
        out = split_output(DRAFT + "\n\nANCHORS\nSAID: il voulait le résultat\n")
        self.assertEqual(out.anchors, ())
        self.assertTrue(any("SAID" in p for p in out.problems))

    def test_a_post_without_a_said_is_a_problem(self):
        out = split_output(DRAFT + "\n\nANCHORS\nPOST: The client signed\n")
        self.assertEqual(out.anchors, ())
        self.assertTrue(any("POST" in p for p in out.problems))

    def test_two_posts_in_a_row_keep_the_paired_one_and_report_the_other(self):
        out = split_output(DRAFT + "\n\nANCHORS\n"
                           "POST: The client signed\n"
                           "POST: not for the tool\n"
                           "SAID: il voulait le résultat\n")
        self.assertEqual(len(out.anchors), 1)
        self.assertEqual(out.anchors[0].fragment, "not for the tool")
        self.assertEqual(len(out.problems), 1)

    def test_an_unreadable_line_in_the_block_is_a_problem(self):
        out = split_output(BLOCK + "some prose in the middle\n")
        self.assertEqual(len(out.anchors), 1)
        self.assertTrue(any("some prose" in p for p in out.problems))

    def test_an_empty_block_is_no_anchors_and_no_problem(self):
        out = split_output(DRAFT + "\n\nANCHORS\n")
        self.assertEqual(out.anchors, ())
        self.assertEqual(out.problems, ())


class TestContains(unittest.TestCase):
    def test_typography_is_forgiven(self):
        self.assertTrue(contains(TRANSCRIPT, "j’ai vendu l’audit"))
        self.assertTrue(contains(TRANSCRIPT, "LE CLIENT s'en fichait"))
        self.assertTrue(contains(TRANSCRIPT,
                                 "il voulait\nle résultat"))
        self.assertTrue(contains(TRANSCRIPT, "il voulait le résultat"))

    def test_words_are_not_forgiven(self):
        self.assertFalse(contains(TRANSCRIPT, "j'ai vendu le produit"))
        self.assertFalse(contains(TRANSCRIPT, "il voulait un résultat"))

    def test_an_empty_needle_matches_nothing(self):
        self.assertFalse(contains(TRANSCRIPT, ""))
        self.assertFalse(contains(TRANSCRIPT, "   "))


class TestVerify(unittest.TestCase):
    def test_a_backed_claim_is_anchored(self):
        verdicts = verify(DRAFT, split_output(BLOCK).anchors, TRANSCRIPT)
        self.assertEqual([v.status for v in verdicts], ["anchored"])
        self.assertTrue(verdicts[0].in_draft)
        self.assertTrue(verdicts[0].in_transcript)

    def test_an_invented_quote_is_fabricated(self):
        anchors = (Anchor(fragment="The client signed for the result",
                          quote="j'ai automatisé toute la chaîne"),)
        verdicts = verify(DRAFT, anchors, TRANSCRIPT)
        self.assertEqual(verdicts[0].status, "fabricated")

    def test_a_fragment_absent_from_the_draft_is_dangling(self):
        anchors = (Anchor(fragment="A sentence the draft never says",
                          quote="il voulait le résultat"),)
        verdicts = verify(DRAFT, anchors, TRANSCRIPT)
        self.assertEqual(verdicts[0].status, "dangling")

    def test_dangling_wins_when_both_sides_fail(self):
        anchors = (Anchor(fragment="A sentence the draft never says",
                          quote="une phrase jamais dite"),)
        verdicts = verify(DRAFT, anchors, TRANSCRIPT)
        self.assertEqual(verdicts[0].status, "dangling")
        self.assertFalse(verdicts[0].in_transcript)


class TestUncovered(unittest.TestCase):
    """The third alarm state: claims of the draft no anchor touches."""

    def test_the_sentence_without_an_anchor_is_named(self):
        left_out = uncovered(DRAFT, split_output(BLOCK).anchors)
        self.assertEqual(left_out, ["I sold my first audit before writing "
                                    "a single line of code."])

    def test_a_partial_fragment_covers_its_sentence(self):
        anchors = (Anchor(fragment="not for the tool",
                          quote="il voulait le résultat"),)
        left_out = uncovered(DRAFT, anchors)
        self.assertNotIn("The client signed for the result, not for the "
                         "tool.", left_out)

    def test_a_dangling_fragment_covers_nothing(self):
        anchors = (Anchor(fragment="A sentence the draft never says",
                          quote="il voulait le résultat"),)
        self.assertEqual(len(uncovered(DRAFT, anchors)), 2)

    def test_no_anchors_means_every_sentence_is_uncovered(self):
        self.assertEqual(len(uncovered(DRAFT, ())), 2)

    def test_a_degenerate_fragment_covers_and_anchors_nothing(self):
        anchors = (Anchor(fragment="e", quote="a"),)
        self.assertEqual(len(uncovered(DRAFT, anchors)), 2)
        verdicts = verify(DRAFT, anchors, TRANSCRIPT)
        self.assertEqual(verdicts[0].status, "dangling")
        self.assertFalse(verdicts[0].in_transcript)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
