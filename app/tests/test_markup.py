"""Tests for the one place this app turns markdown into anything else.

Needs markdown-it-py, so it runs through the project environment:
    cd app && uv run python -m unittest discover -s tests

Two halves. `render` produces HTML that goes into a page unescaped, so every
test about it is really a test about what a file from somewhere else can make
this browser do. `plain` produces text that goes on a clipboard, so every test
about it is about what survives and what is only there to tell a renderer what
to do.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app.markup import plain, render  # noqa: E402


class TestNothingFromAFileBecomesMarkup(unittest.TestCase):
    """corpus/ holds exports from other tools, and profile.md holds whatever
    somebody pasted into it. This is the injection boundary, and it being on
    loopback does not make somebody's browser a place to run what an export
    happens to contain."""

    def test_a_script_tag_is_text(self):
        out = render("<script>alert(1)</script>")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_an_event_handler_is_text(self):
        out = render("<img src=x onerror=alert(1)>")
        self.assertNotIn("<img", out)
        self.assertIn("onerror", out)  # as text, escaped around it
        self.assertIn("&lt;img", out)

    def test_an_html_block_is_text(self):
        out = render('<div onclick="steal()">\n\nhello\n\n</div>')
        self.assertNotIn("<div", out)
        self.assertIn("&lt;div", out)

    def test_html_inside_a_fence_stays_inside_it(self):
        out = render("```\n<script>alert(1)</script>\n```")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)


class TestABadDestinationNeverBecomesALink(unittest.TestCase):
    """The link destination is the half `html=False` does not cover. These
    are pinned rather than trusted: they are the reason this module uses a
    parser somebody else maintains instead of a regular expression."""

    BAD = (
        "[click](javascript:alert(1))",
        "[click](JaVaScRiPt:alert(1))",
        "[click](vbscript:alert(1))",
        "[click](data:text/html,hello)",
        "[click](file:///etc/passwd)",
        # Decoded before it is judged, which is where a hand written guard
        # that checked the raw source would let it through.
        "[click](&#106;avascript:alert(1))",
    )

    def test_none_of_them_produces_an_anchor(self):
        for case in self.BAD:
            with self.subTest(case=case):
                self.assertNotIn("<a ", render(case), case)

    def test_an_ordinary_link_is_a_link(self):
        self.assertIn('href="https://example.com"',
                      render("[ok](https://example.com)"))


class TestAnImageNeverFetchesAnything(unittest.TestCase):
    """`html=False` says nothing about this one. A markdown image is a fetch
    the moment the page paints, from a page whose own rail says nothing
    leaves this machine, and the file that carries it came from somewhere
    else. It renders as a link to its source: no request, and the address is
    still there to click."""

    def test_no_img_element_is_produced(self):
        out = render("![alt](https://pixel.example/p.gif)")
        self.assertNotIn("<img", out)

    def test_the_source_survives_as_a_link(self):
        out = render("![alt](https://pixel.example/p.gif)")
        self.assertIn('href="https://pixel.example/p.gif"', out)
        self.assertIn("alt", out)

    def test_an_image_with_no_alt_text_shows_its_address(self):
        out = render("![](https://pixel.example/p.gif)")
        self.assertIn("https://pixel.example/p.gif", out)

    def test_a_bad_image_destination_is_not_even_a_link(self):
        self.assertNotIn("<a ", render("![x](javascript:alert(1))"))

    def test_a_picture_inside_a_link_does_not_nest_two_anchors(self):
        """HTML has no anchor inside an anchor: a parser splits the pair into
        siblings, and the document's own link comes out empty and
        unclickable while the picture's address is the only thing left to
        click. The picture's address is the one that gives way."""
        out = render("[![px](https://ev.example/px.gif)](https://ev.example/p)")
        self.assertEqual(out.count("<a "), 1)
        self.assertIn('href="https://ev.example/p"', out)
        self.assertNotIn("px.gif", out)
        self.assertIn('<span class="image-link">px</span>', out)

    def test_a_bare_pixel_inside_a_link_still_shows_its_address(self):
        out = render("[![](https://ev.example/px.gif)](https://ev.example/p)")
        self.assertIn("https://ev.example/px.gif", out)
        self.assertEqual(out.count("<a "), 1)

    def test_the_link_depth_does_not_leak_between_renders(self):
        """Counted in the per render env, so a document that ends inside a
        link cannot turn the next document's images into spans."""
        render("[![a](https://e.example/a.png)](https://e.example/p)")
        self.assertIn("<a ", render("![b](https://e.example/b.png)"))

    def test_an_autolink_inside_link_text_does_not_nest_two_anchors(self):
        """The sibling of the case above, and the one a guard written for
        images alone walks straight past. `[a](b)` inside link text is
        refused by the parser, but an autolink is not, so this is the way in.
        The damage is the same and worse: the outer link splits, the words
        after the inner one fall out of both, and the address a reader lands
        on is the third party one from inside the document."""
        out = render("[see <https://inner.example/t> here](https://outer.example/p)")
        self.assertEqual(out.count("<a "), 1)
        self.assertIn('href="https://outer.example/p"', out)
        self.assertNotIn('href="https://inner.example/t"', out)
        # nothing is lost: an autolink's text is its address
        self.assertIn("https://inner.example/t", out)
        self.assertIn("here", out)

    def test_a_mail_autolink_inside_link_text_is_the_same_case(self):
        out = render("[write <mailto:a@e.example> now](https://outer.example/p)")
        self.assertEqual(out.count("<a "), 1)
        self.assertIn("now", out)

    def test_an_autolink_on_its_own_is_still_a_link(self):
        out = render("<https://e.example/t>")
        self.assertEqual(out.count("<a "), 1)
        self.assertIn('href="https://e.example/t"', out)

    def test_a_link_after_a_nested_one_is_still_a_link(self):
        out = render("[a <https://in.example/x> b](https://out.example/p)\n\n"
                     "[then](https://later.example/q)")
        self.assertEqual(out.count("<a "), 2)
        self.assertIn('href="https://later.example/q"', out)

    def test_an_image_after_a_link_in_one_document_is_still_a_link(self):
        out = render("[t](https://e.example/p) and ![b](https://e.example/b.png)")
        self.assertEqual(out.count("<a "), 2)
        self.assertIn('href="https://e.example/b.png"', out)


class TestWhatADocumentActuallyContains(unittest.TestCase):
    """The shapes the instance files really use. The table is here because
    profile.md has one, and the commonmark preset does not."""

    def test_a_table(self):
        out = render("| File | Holds |\n|---|---|\n| `voice.md` | Style. |")
        self.assertIn("<table>", out)
        self.assertIn("<td>", out)

    def test_headings_lists_and_emphasis(self):
        out = render("## Pillars\n\n- one\n- **two**\n")
        self.assertIn("<h2>Pillars</h2>", out)
        self.assertIn("<li>one</li>", out)
        self.assertIn("<strong>two</strong>", out)

    def test_a_fenced_block(self):
        self.assertIn("<pre>", render("```\nNadia Feriel, CFO.\n```"))


class TestRenderIsSafeToPlaceWithoutTheSafeFilter(unittest.TestCase):
    """A template that writes `| safe` is a template somebody copies to a
    place where the value is not safe. The function carries the guarantee
    instead, so no screen in this app ever has to."""

    def test_it_returns_markup(self):
        from markupsafe import Markup
        self.assertIsInstance(render("hello"), Markup)

    def test_empty_input_is_empty_output(self):
        self.assertEqual(render(""), "")
        self.assertEqual(render("   \n\n "), "")


class TestPlainKeepsTheWordsAndDropsTheInstructions(unittest.TestCase):
    """What goes on a clipboard for a field that has no formatting, which is
    what linkedin-page.md is written for. Every word the document holds
    survives; the characters that exist only to tell a renderer what to do do
    not."""

    def test_a_heading_loses_its_hashes(self):
        self.assertEqual(plain("## Pillars"), "Pillars")

    def test_emphasis_and_code_lose_their_markers(self):
        self.assertEqual(plain("Some **bold** and `code`."),
                         "Some bold and code.")

    def test_a_bullet_survives_because_it_is_the_item_boundary(self):
        self.assertEqual(plain("- one\n- two"), "- one\n- two")

    def test_an_ordered_list_keeps_its_numbers(self):
        self.assertEqual(plain("1. one\n2. two"), "1. one\n2. two")

    def test_a_nested_list_is_indented(self):
        self.assertEqual(plain("- one\n  - deeper"), "- one\n  - deeper")

    def test_a_second_paragraph_of_one_item_stays_under_it(self):
        """Otherwise the bullet stops being the item boundary it is kept for:
        two items read as three."""
        self.assertEqual(plain("- one\n\n  and more\n- two"),
                         "- one\n  and more\n- two")

    def test_a_block_inside_an_item_stays_under_it(self):
        self.assertEqual(plain("- one\n  ```\n  code\n  ```"),
                         "- one\n  code")

    def test_an_ordered_item_hangs_by_the_width_of_its_own_number(self):
        self.assertEqual(plain("1. one\n\n   and more"),
                         "1. one\n   and more")

    def test_a_link_keeps_its_text_and_its_address(self):
        self.assertEqual(plain("[LinkedIn](https://example.com/x)"),
                         "LinkedIn (https://example.com/x)")

    def test_a_link_whose_text_is_its_address_is_not_written_twice(self):
        self.assertEqual(plain("<https://example.com/x>"),
                         "https://example.com/x")

    def test_an_image_keeps_its_alt_text_and_its_address(self):
        self.assertEqual(plain("![a chart](https://example.com/c.png)"),
                         "a chart (https://example.com/c.png)")

    def test_a_quote_loses_its_angle_bracket(self):
        self.assertEqual(plain("> quoted"), "quoted")

    def test_a_fence_keeps_its_content_verbatim(self):
        self.assertEqual(plain("```\nNadia Feriel, CFO.\nTwo lines.\n```"),
                         "Nadia Feriel, CFO.\nTwo lines.")

    def test_a_table_keeps_every_cell(self):
        out = plain("| File | Holds |\n|---|---|\n| voice.md | Style. |")
        self.assertEqual(out, "File | Holds\nvoice.md | Style.")

    def test_a_table_inside_an_item_stays_inside_it(self):
        """Otherwise the table is hoisted out ahead of the list it belonged
        to and the item is left as a bare bullet, which is this function
        writing a marker for content that is no longer under it."""
        self.assertEqual(
            plain("- | a | b |\n  |---|---|\n  | 1 | 2 |\n- two"),
            "- a | b\n  1 | 2\n- two")

    def test_an_ordered_item_holding_a_table_keeps_its_number(self):
        self.assertEqual(
            plain("1. | a |\n   |---|\n   | 1 |\n2. two"),
            "1. a\n   1\n2. two")

    def test_no_line_ever_ends_in_whitespace(self):
        """An empty fence inside an item used to spend the bullet on nothing
        and leave the line ending in a space."""
        for source in ("1. ```\n  x\n  ```", "- ```\n  ```", "- one\n-\n- two",
                       "# h\n\n- \n- two"):
            for line in plain(source).splitlines():
                self.assertEqual(line, line.rstrip(), repr(source))

    def test_an_empty_item_is_still_a_bullet(self):
        self.assertEqual(plain("- one\n-\n- two"), "- one\n-\n- two")

    def test_a_quote_inside_an_item_does_not_split_it(self):
        self.assertEqual(plain("- one\n\n  > quoted\n- two"),
                         "- one\n  quoted\n- two")

    def test_blocks_are_separated_by_one_blank_line(self):
        self.assertEqual(plain("# Title\n\nA paragraph.\n\n- one\n- two"),
                         "Title\n\nA paragraph.\n\n- one\n- two")

    def test_a_soft_break_keeps_the_line_the_author_wrote(self):
        self.assertEqual(plain("one\ntwo"), "one\ntwo")

    def test_nothing_arrives_html_escaped(self):
        """The half a strip-the-tags implementation gets wrong. This text
        goes on a clipboard, not into a page."""
        self.assertEqual(plain("a & b < c > d"), "a & b < c > d")
        self.assertEqual(plain("Rock & Roll"), "Rock & Roll")

    def test_empty_input_is_empty_output(self):
        self.assertEqual(plain(""), "")
        self.assertEqual(plain("   \n\n "), "")


class TestPlainAndRenderReadTheSameDocument(unittest.TestCase):
    """One parser, two outputs. Two parsers would be two readings of the same
    file, and the one nobody looks at is the one that would be wrong."""

    def test_a_destination_neither_of_them_accepts_stays_the_source_text(self):
        """Refused by the parser, so neither output invents a link out of it.
        What is left is what somebody typed, which is the honest answer."""
        source = "[x](javascript:alert(1))"
        self.assertNotIn("<a ", render(source))
        self.assertEqual(plain(source), source)

    def test_the_example_profile_survives_both(self):
        text = (REPO / "examples" / "profile.md").read_text(encoding="utf-8")
        self.assertIn("<h2>", render(text))
        self.assertNotIn("##", plain(text))
        # The signature block is fenced in that file, and it is the one piece
        # of it somebody actually pastes somewhere.
        self.assertIn("Nadia Feriel", plain(text))


if __name__ == "__main__":
    unittest.main()
