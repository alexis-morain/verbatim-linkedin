"""Tests for finding the bundle, in a checkout and in an installed package.

The app reads `SKILL.md`, `locales/`, `skills/`, `references/` and the two
`lib/` scripts at run time. In a checkout they sit two levels above the
package. Installed from PyPI they do not sit anywhere near it, so the wheel
carries a copy and `bundle_root` finds that instead. This file is what stops
a new engine directory from being read in development and missing from every
installation.

    cd app && uv run python -m unittest discover -s tests
"""

import os
import shutil
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app.i18n import BundleError, bundle_root  # noqa: E402

PYPROJECT = REPO / "app" / "pyproject.toml"

#: Everything the engine reaches for at run time, relative to the bundle
#: root. `SKILL.md` is the router and the sentinel `bundle_root` recognises
#: the directory by; `lib/` is named file by file because the tests beside
#: those two scripts are not part of an installation.
NEEDED = ("SKILL.md", "locales", "skills", "references",
          "lib/lint.py", "lib/publish.py")


class TestWhereTheBundleIs(unittest.TestCase):
    def setUp(self):
        # Resolved: on macOS the temp root is a symlink, and `bundle_root`
        # answers with a real path.
        self.tmp = Path(tempfile.mkdtemp(prefix="verbatim-bundle-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.previous = os.environ.pop("VERBATIM_BUNDLE", None)
        if self.previous is not None:
            self.addCleanup(os.environ.__setitem__, "VERBATIM_BUNDLE",
                            self.previous)

    def a_bundle(self, root: Path) -> Path:
        (root / "locales").mkdir(parents=True)
        (root / "SKILL.md").write_text("router\n", encoding="utf-8")
        return root

    def test_a_checkout_is_found_two_levels_up(self):
        self.assertEqual(bundle_root(), REPO)

    def test_the_override_wins_over_everything(self):
        other = self.a_bundle(self.tmp / "elsewhere")
        os.environ["VERBATIM_BUNDLE"] = str(other)
        self.assertEqual(bundle_root(), other)

    def test_an_override_naming_no_bundle_falls_through_rather_than_dying(self):
        # Somebody's stale export. The checkout is still right there, and
        # refusing to start over a variable that names nothing would be
        # refusing to work in a tree that is complete.
        os.environ["VERBATIM_BUNDLE"] = str(self.tmp / "gone")
        self.assertEqual(bundle_root(), REPO)

    def test_the_copy_inside_the_package_is_found_when_there_is_no_checkout(self):
        # What an installation looks like: the package sits in site-packages
        # and nothing two levels up is a bundle.
        package = self.tmp / "site-packages" / "verbatim_app"
        package.mkdir(parents=True)
        self.a_bundle(package / "_bundle")
        self.assertEqual(bundle_root(package=package), package / "_bundle")

    def test_a_checkout_beats_the_packaged_copy(self):
        # An editable install has both. The tree somebody is editing is the
        # one they mean, and a snapshot that shadowed it would answer with
        # yesterday's language pack and say nothing about it.
        root = self.a_bundle(self.tmp / "checkout")
        package = root / "app" / "verbatim_app"
        package.mkdir(parents=True)
        self.a_bundle(package / "_bundle")
        self.assertEqual(bundle_root(package=package), root)

    def test_no_bundle_anywhere_says_which_variable_fixes_it(self):
        package = self.tmp / "nowhere" / "verbatim_app"
        package.mkdir(parents=True)
        with self.assertRaises(BundleError) as caught:
            bundle_root(package=package)
        self.assertIn("VERBATIM_BUNDLE", str(caught.exception))


class TestTheWheelCarriesTheWholeBundle(unittest.TestCase):
    """An installation has no checkout to fall back on, so anything the
    engine reads and the wheel does not carry is a hole nobody sees until
    somebody who is not the maintainer runs it."""

    def force_include(self) -> dict:
        with PYPROJECT.open("rb") as handle:
            data = tomllib.load(handle)
        return (data["tool"]["hatch"]["build"]["targets"]["wheel"]
                    ["force-include"])

    def test_every_directory_the_engine_reads_is_carried(self):
        mapped = self.force_include()
        for needed in NEEDED:
            self.assertIn(f"../{needed}", mapped, needed)
            self.assertEqual(mapped[f"../{needed}"],
                             f"verbatim_app/_bundle/{needed}")

    def test_the_sources_it_names_are_actually_there(self):
        for source in self.force_include():
            self.assertTrue((REPO / "app" / source).exists(), source)

    def test_the_tests_beside_the_lib_scripts_are_not_shipped(self):
        # lib/ holds four files and two of them are tests. Mapping the
        # directory would ship them, which is not fatal and is not the deal.
        self.assertNotIn("../lib", self.force_include())

    def test_the_version_is_the_one_the_package_reports(self):
        with PYPROJECT.open("rb") as handle:
            declared = tomllib.load(handle)["project"]["version"]
        from verbatim_app import __version__
        self.assertEqual(declared, __version__)


if __name__ == "__main__":
    unittest.main(verbosity=2)
