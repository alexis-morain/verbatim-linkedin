"""Tests for verbatim_app.sufficiency, how much material is on the table.

`interview-intents.md` already replaces a question counter with a sufficiency
test: the engine names what is missing every turn, in one line. That sentence
is the honest half and the unreadable half. This is the number beside it.

What it counts is facts, not turns, and it counts them in the person's own
words and nowhere else. Both halves matter and the second one is the rule:
a sheet line, a profile line and anything a tool returned are not things the
author said, and a gauge that credited them would be scoring the engine's
own work back to them.

Runs with the standard library only:  python3 app/tests/test_sufficiency.py
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app import sufficiency  # noqa: E402


class TestWhatCountsAsAFact(unittest.TestCase):
    def test_nothing_said_is_nothing_counted(self):
        for empty in ("", "   ", "\n\n"):
            reading = sufficiency.of(empty)
            self.assertEqual(reading.facts, 0)
            self.assertEqual(reading.ratio, 0)

    def test_a_figure_is_a_fact(self):
        reading = sufficiency.of("J'ai signe 12 clients.")
        self.assertEqual(reading.figures, 1)
        self.assertEqual(reading.named, 0)

    def test_a_figure_written_with_separators_is_one_figure(self):
        for written in ("6 800 euros", "6 800 euros", "0,04 de taux",
                        "2.037 caracteres"):
            self.assertEqual(sufficiency.of(written).figures, 1, written)

    def test_a_named_instance_is_a_fact(self):
        reading = sufficiency.of("On a bosse avec Doctolib pendant l'ete.")
        self.assertEqual(reading.named, 1)
        self.assertEqual(reading.figures, 0)

    def test_the_first_word_of_a_sentence_is_not_a_name(self):
        # Every sentence starts capitalised. A gauge that counted those would
        # score the number of sentences, which is the turn counter this
        # exists to replace.
        reading = sufficiency.of("Quatre mois. Puis rien. Ensuite tout.")
        self.assertEqual(reading.named, 0)

    def test_a_new_line_starts_a_sentence_too(self):
        reading = sufficiency.of("Quatre mois\nPuis rien\nEnsuite tout")
        self.assertEqual(reading.named, 0)

    def test_the_same_fact_twice_is_one_fact(self):
        # Density, not repetition. Somebody who says 12 in four sentences has
        # given one number, and a gauge that paid for each mention would pay
        # most for the person who repeats themselves.
        reading = sufficiency.of(
            "J'ai signe 12 clients. Les 12 en 3 semaines. Douze, oui, 12.")
        self.assertEqual(reading.figures, 2)  # 12 and 3, once each

    def test_a_number_written_out_in_letters_is_not_counted(self):
        # A limit, written down rather than discovered. "douze clients" is
        # as concrete as "12 clients" and this does not see it. The sentence
        # the engine writes each turn is what says what is missing; this
        # only ever undercounts, which is the direction to be wrong in.
        self.assertEqual(sufficiency.of("J'ai signe douze clients.").facts, 0)

    def test_a_name_in_two_cases_is_one_name(self):
        reading = sufficiency.of("On a vu Malt. Puis encore MALT ensuite.")
        self.assertEqual(reading.named, 1)

    def test_a_single_letter_is_not_a_name(self):
        # "I" is the author, and a letter is not an instance anybody can
        # point at.
        self.assertEqual(sufficiency.of("Then I left. And I came back.").named,
                         0)

    def test_a_dense_answer_scores_more_than_a_long_one(self):
        dense = sufficiency.of(
            "En 2024 j'ai signe 12 clients chez Malt, 3 chez Doctolib, "
            "pour 6 800 euros.")
        long_and_empty = sufficiency.of(
            "je pense vraiment que c'est important de bien faire les choses "
            "et de rester dans une demarche de qualite parce que sinon on "
            "perd le sens de ce qu'on fait au quotidien dans son travail")
        self.assertGreater(dense.ratio, long_and_empty.ratio)
        self.assertEqual(long_and_empty.ratio, 0)


class TestTheNumber(unittest.TestCase):
    def test_the_ratio_is_a_reading_of_the_count(self):
        reading = sufficiency.of("12 clients chez Malt")
        self.assertEqual(reading.facts, 2)
        self.assertEqual(
            reading.ratio, round(100 * 2 / sufficiency.ENOUGH))

    def test_it_never_goes_past_a_hundred(self):
        said = " ".join(f"{n} chez Nom{n}." for n in range(1, 40))
        self.assertEqual(sufficiency.of(said).ratio, 100)

    def test_enough_is_reached_at_the_threshold_and_not_before(self):
        under = " ".join(f"Il y a {n}." for n in range(1, sufficiency.ENOUGH))
        at = " ".join(f"Il y a {n}." for n in range(1, sufficiency.ENOUGH + 1))
        self.assertFalse(sufficiency.of(under).enough)
        self.assertTrue(sufficiency.of(at).enough)


if __name__ == "__main__":
    unittest.main(verbosity=2)
