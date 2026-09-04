"""Tests for the distribution metadata, which is the whole project page.

Nothing has ever been published, so the first upload writes the page that
everybody who has never read this repository will read. A version on PyPI
cannot be reused: a page that ships wrong is fixed by publishing 2.4.1, not
by editing it. The three fields that make that page are read by nothing in a
checkout, so an empty one is invisible right up to the moment it is
permanent, which is why they are held here.

The long description is the README one level up, and `readme =
"../README.md"` does not build: hatchling refuses a readme path outside the
project directory, which is the one place `force-include` is allowed to
reach. The bundle travels up, the metadata cannot. So the file arrives as
text through the metadata hook in `app/hatch_build.py`, and its relative
links are made absolute on the way: PyPI keeps a relative target verbatim
and serves the page from its own host, where there is no `docs/` under it.

check.sh builds the wheel and reads the METADATA that comes out. This file
reads what goes in.

    cd app && uv run python -m unittest discover -s tests
"""

import re
import sys
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from hatch_build import absolute_links  # noqa: E402

PYPROJECT = REPO / "app" / "pyproject.toml"
README = REPO / "README.md"
REPOSITORY = "https://github.com/alexis-morain/verbatim-linkedin"

#: Every markdown target in a text, found by a deliberately simpler
#: expression than the one under test: a guard written out of the thing it
#: guards proves that the thing agrees with itself and nothing more.
TARGET = re.compile(r"\]\(([^)]*)\)")
#: A target that is already somewhere: a scheme, a protocol relative URL, or
#: a fragment of the page it sits on.
ELSEWHERE = re.compile(r"^(\w+:|//|#)")


def relative(markdown: str) -> list:
    """Every target that only resolves against a checkout."""
    return [t for t in TARGET.findall(markdown) if not ELSEWHERE.match(t)]


def project() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


class TestTheLinksArriveSomewhere(unittest.TestCase):
    """This README is written to be read on GitHub, where `docs/smoke.md`
    means what it says. The same markdown on PyPI is served from a host with
    no `docs/` under it, so a relative target that survives the build is a
    dead link, and the four images are dead pictures under the title."""

    def test_an_image_points_at_the_file_itself(self):
        # Not at the page around it: raw, because an `img` whose `src` is a
        # GitHub blob page renders as an HTML document, which is nothing.
        made = absolute_links("![shot](docs/screenshots/overview.png)",
                              REPOSITORY)
        self.assertEqual(
            made,
            "![shot](https://raw.githubusercontent.com/alexis-morain/"
            "verbatim-linkedin/main/docs/screenshots/overview.png)")

    def test_a_file_points_at_its_blob(self):
        self.assertEqual(
            absolute_links("[LICENSE](LICENSE)", REPOSITORY),
            f"[LICENSE]({REPOSITORY}/blob/main/LICENSE)")

    def test_a_directory_points_at_its_tree(self):
        # GitHub spells a directory `tree` and a file `blob`, and this README
        # links five directories. The trailing slash is the whole rule, which
        # is enough for a repository that writes them that way.
        self.assertEqual(
            absolute_links("[examples](examples/)", REPOSITORY),
            f"[examples]({REPOSITORY}/tree/main/examples/)")

    def test_a_link_that_is_already_somewhere_is_left_alone(self):
        for target in ("https://postiz.com", "http://127.0.0.1:8747",
                       "#engine-and-profile", "mailto:alexis@morain.fr"):
            with self.subTest(target=target):
                one = f"[label]({target})"
                self.assertEqual(absolute_links(one, REPOSITORY), one)

    def test_the_label_is_not_touched(self):
        # Labels here hold backticks, colons and commas. The rewriting reads
        # the target and copies the rest.
        one = "[`linkedin-setup`, the first one](skills/linkedin-setup/)"
        self.assertIn("[`linkedin-setup`, the first one]",
                      absolute_links(one, REPOSITORY))

    def test_nothing_relative_survives_the_real_readme(self):
        # The regression guard. A link written in a shape the rewriting does
        # not know is a dead link on a page that cannot be republished.
        made = absolute_links(README.read_text(encoding="utf-8"), REPOSITORY)
        self.assertEqual(relative(made), [])

    def test_the_readme_has_relative_links_to_begin_with(self):
        # Otherwise the test above passes on a file that changed shape, and
        # says the rewriting works when nothing asked it to do anything.
        self.assertTrue(relative(README.read_text(encoding="utf-8")))

    def test_the_prose_is_the_same_prose(self):
        source = README.read_text(encoding="utf-8")
        made = absolute_links(source, REPOSITORY)
        self.assertEqual(len(source.splitlines()), len(made.splitlines()))
        self.assertIn("**The LinkedIn post skill that interviews you first.**",
                      made)

    def test_a_repository_that_is_not_github_is_refused(self):
        # Three URL shapes are derived from this one string. Guessing them
        # from a host the rewriting does not know would publish a page of
        # links to somewhere that does not exist.
        with self.assertRaises(ValueError):
            absolute_links("[a](b)", "https://gitlab.com/someone/something")


class TestTheProjectPageIsFilledIn(unittest.TestCase):
    def test_the_readme_arrives_through_the_hook(self):
        data = project()
        self.assertIn("readme", data["project"]["dynamic"])
        self.assertIn("custom",
                      data["tool"]["hatch"]["metadata"]["hooks"])

    def test_the_urls_name_the_repository(self):
        urls = project()["project"]["urls"]
        for key in ("Homepage", "Source", "Issues", "Changelog"):
            self.assertIn(key, urls)
            self.assertTrue(urls[key].startswith(REPOSITORY), key)

    def test_the_urls_table_holds_urls_and_nothing_else(self):
        # A table opened in the middle of `[project]` takes every bare key
        # written after it. Putting this one above `dependencies` moved the
        # seven runtime requirements into it, and the wheel that came out
        # declared none: an install with no fastapi in it, from metadata
        # that cannot be republished under the same version. Found here
        # because the suite above passed while it was true.
        urls = project()["project"]["urls"]
        self.assertEqual(sorted(urls),
                         ["Changelog", "Homepage", "Issues", "Source"])

    def test_the_dependencies_survived_the_tables_around_them(self):
        data = project()["project"]
        names = [d.split(">")[0] for d in data["dependencies"]]
        self.assertEqual(sorted(names),
                         ["fastapi", "httpx", "jinja2", "markdown-it-py",
                          "python-multipart", "pyyaml", "uvicorn"])
        self.assertEqual(data["scripts"]["verbatim"], "verbatim_app.cli:main")

    def test_the_repository_is_written_down_once(self):
        # The hook reads it out of the project file rather than holding a
        # second copy, which is the same rule the rest of this repository
        # keeps: one answer, one place.
        source = (REPO / "app" / "hatch_build.py").read_text(encoding="utf-8")
        self.assertNotIn("alexis-morain", source)

    def test_the_classifiers_cover_every_python_it_claims(self):
        data = project()["project"]
        self.assertEqual(data["requires-python"], ">=3.11")
        claimed = {c.rsplit(" :: ", 1)[1] for c in data["classifiers"]
                   if c.startswith("Programming Language :: Python :: ")}
        self.assertEqual(claimed, {"3", "3.11", "3.12", "3.13"})

    def test_the_licence_is_said_the_same_way_twice(self):
        data = project()["project"]
        self.assertEqual(data["license"]["text"], "MIT")
        self.assertIn("License :: OSI Approved :: MIT License",
                      data["classifiers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
