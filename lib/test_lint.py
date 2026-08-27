"""Tests for lint.py. Run: python3 lib/test_lint.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lint  # noqa: E402

FR = lint.load_pack("fr")
EN = lint.load_pack("en")


def ids(findings):
    return sorted({f.category for f in findings})


class TestNormalisation(unittest.TestCase):
    def test_strips_accents_and_case(self):
        self.assertEqual(lint.flatten("ÉCOSYSTÈME"), "ecosysteme")

    def test_normalises_curly_apostrophe(self):
        self.assertIn("n'hesitez", lint.flatten("N’hésitez pas"))

    def test_collapses_whitespace(self):
        self.assertEqual(lint.flatten("tirer\nparti  de"), "tirer parti de")


class TestTerms(unittest.TestCase):
    def test_matches_on_word_boundary(self):
        f = lint.run("un outil robuste", FR)
        self.assertIn("hollow-jargon", ids(f))

    def test_does_not_match_inside_a_longer_word(self):
        f = lint.run("la robustesse du systeme", FR)
        self.assertNotIn("hollow-jargon", ids(f))

    def test_accent_insensitive(self):
        f = lint.run("un ecosysteme growth", FR)
        self.assertIn("hollow-jargon", ids(f))

    def test_multiword_term_across_a_line_break(self):
        f = lint.run("il faut tirer\nparti de ca", FR)
        self.assertIn("grandiose-verbs", ids(f))

    def test_reports_the_term_that_hit(self):
        f = lint.run("une approche holistique", FR)
        self.assertEqual(f[0].evidence, "holistique")


class TestPatterns(unittest.TestCase):
    def test_french_negative_parallelism(self):
        f = lint.run(
            "Ce n'est pas un probleme de volume, c'est un probleme de ciblage.", FR
        )
        self.assertIn("negative-parallelism", ids(f))

    def test_english_negative_parallelism(self):
        f = lint.run("It's not a volume problem, it's a targeting problem.", EN)
        self.assertIn("negative-parallelism", ids(f))

    def test_de_plus_only_at_the_start_of_a_sentence(self):
        self.assertIn(
            "schoolbook-transitions", ids(lint.run("De plus, c'est cher.", FR))
        )
        self.assertNotIn(
            "schoolbook-transitions", ids(lint.run("Il suit le profil, rien de plus.", FR))
        )

    def test_leverage_as_a_verb_only(self):
        self.assertIn("grandiose-verbs", ids(lint.run("leverage your network", EN)))
        self.assertNotIn(
            "grandiose-verbs", ids(lint.run("debt leverage stayed flat", EN))
        )


class TestTypography(unittest.TestCase):
    def test_em_dash_is_hard(self):
        f = [x for x in lint.run("un mot — puis un autre", FR) if x.hard]
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].category, "typography")

    def test_en_dash_is_not_flagged(self):
        self.assertEqual(lint.run("pages 10–12", FR), [])

    def test_emoji_is_hard(self):
        f = [x for x in lint.run("bravo \U0001f680", FR) if x.hard]
        self.assertEqual(len(f), 1)

    def test_missing_nbsp_in_french(self):
        self.assertIn("typography", ids(lint.run("le resultat : 10", FR)))

    def test_nbsp_present_is_clean(self):
        self.assertEqual(lint.run("le resultat : 10", FR), [])

    def test_english_pack_does_not_ask_for_nbsp(self):
        self.assertEqual(lint.run("the result: 10", EN), [])

    def test_straight_quotes_flagged_in_french_only(self):
        self.assertIn("typography", ids(lint.run('il a dit "oui" hier', FR)))
        self.assertEqual(lint.run('he said "yes" yesterday', EN), [])


class TestOutput(unittest.TestCase):
    def test_clean_text_has_no_findings(self):
        self.assertEqual(lint.run("On est passes de 0,1 a 0,007 par contact.", FR), [])

    def test_sorted_by_weight_descending(self):
        f = lint.run("Plongeons dans le sujet. De plus, c'est robuste.", FR)
        weights = [x.weight for x in f]
        self.assertEqual(weights, sorted(weights, reverse=True))

    def test_hard_findings_set_the_exit_code(self):
        self.assertEqual(lint.exit_code(lint.run("un mot — la", FR)), 1)
        self.assertEqual(lint.exit_code(lint.run("de plus, c'est vrai", FR)), 0)


class TestPacks(unittest.TestCase):
    def test_every_shipped_pack_passes_self_test(self):
        for code in lint.available_packs():
            with self.subTest(pack=code):
                self.assertEqual(lint.self_test(lint.load_pack(code)), [])

    def test_template_is_not_a_usable_pack(self):
        self.assertNotIn("_template", lint.available_packs())

    def test_unknown_pack_raises(self):
        with self.assertRaises(lint.PackError):
            lint.load_pack("zz")

    def test_native_review_flag_is_exposed(self):
        self.assertTrue(FR["native_reviewed"])
        self.assertFalse(EN["native_reviewed"])


class TestFallbackParser(unittest.TestCase):
    """The bundle must work without PyYAML installed.

    The fallback reader only handles the subset a pack is allowed to use. It
    is only trustworthy if it agrees with the real parser on every shipped
    pack, which is what this checks.
    """

    def setUp(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML not installed, nothing to compare against")

    def test_agrees_with_pyyaml_on_every_pack(self):
        import yaml
        names = lint.available_packs() + ["_template"]
        for code in names:
            path = os.path.join(lint.LOCALES, code, "lint.yml")
            with self.subTest(pack=code):
                text = open(path, encoding="utf-8").read()
                self.assertEqual(lint._parse_simple_yaml(text), yaml.safe_load(text))

    def test_refuses_what_it_cannot_read(self):
        with self.assertRaises(lint.PackError):
            lint._parse_simple_yaml("categories:\n  a: {inline: mapping}\n  b\n")


class TestSelfTestCatchesBadPacks(unittest.TestCase):
    def _pack(self, **over):
        import copy
        p = copy.deepcopy(FR)
        p.update(over)
        return p

    def test_missing_category(self):
        p = self._pack()
        del p["categories"]["fake-hooks"]
        self.assertIn("missing category fake-hooks", self_test_text(p))

    def test_unknown_category(self):
        p = self._pack()
        p["categories"]["vibes"] = {"weight": 1, "hard": False}
        self.assertIn("unknown category vibes", " ".join(lint.self_test(p)))

    def test_weight_out_of_range(self):
        p = self._pack()
        p["categories"]["fake-hooks"]["weight"] = 9
        self.assertIn("weight", self_test_text(p))

    def test_broken_pattern(self):
        p = self._pack()
        p["categories"]["fake-hooks"]["patterns"] = ["([unclosed"]
        self.assertIn("bad pattern", self_test_text(p))

    def test_unknown_typography_rule(self):
        p = self._pack()
        p["categories"]["typography"]["rules"]["kerning"] = "forbid"
        self.assertIn("unknown rule kerning", self_test_text(p))

    def test_claiming_a_native_review_without_a_name(self):
        p = self._pack(native_reviewed=True, reviewed_by="")
        self.assertIn("reviewed_by is empty", self_test_text(p))


def self_test_text(pack):
    return " | ".join(lint.self_test(pack))


if __name__ == "__main__":
    unittest.main(verbosity=2)
