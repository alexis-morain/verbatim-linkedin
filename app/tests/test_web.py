"""Tests for the cold screens, against the Nadia Feriel example instance.

Needs fastapi and httpx, so run through the project environment:
    cd app && uv run --extra test python -m unittest discover -s tests
"""

import html as html_module
from datetime import date
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from fastapi.testclient import TestClient  # noqa: E402

from verbatim_app.instance import Instance  # noqa: E402
from verbatim_app.web import create_app  # noqa: E402


class WebCase(unittest.TestCase):
    lang = None
    #: The day every screen is drawn on. Pinned, so what is due at J+7 in the
    #: fixture is the same list on every machine on every day.
    today = date(2026, 9, 2)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-web-")
        self.root = Path(self.tmp) / "instance"
        shutil.copytree(REPO / "examples", self.root)
        # examples/ is a real instance and people point the app at it, which
        # leaves an interviews/ directory behind. It is gitignored, so it is
        # invisible in a diff and permanent on that machine: without this the
        # fixture inherits somebody's conversation and three tests go red with
        # nothing in the failure naming the cause. Found by a reviewer whose
        # checkout had one.
        shutil.rmtree(self.root / "interviews", ignore_errors=True)
        (self.root / "README.md").unlink(missing_ok=True)
        self.client = TestClient(create_app(self.root, lang=self.lang,
                                            today=lambda: self.today),
                                 base_url="http://127.0.0.1:8747")

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestOneBadFileDoesNotTakeTheAppDown(WebCase):
    """Every screen renders the conformance report, so a file nobody can read
    decides whether one row is wrong or the whole app is gone."""

    # The post detail is in here because it was not, and a screen that
    # reads a second file to paint one row went out 500ing over a heading
    # somebody had renamed. Every screen in this tuple survives a file it
    # cannot read; a screen outside it has nobody saying so.
    SCREENS = ("/", "/profile", "/ideas", "/posts", "/measure", "/corpus",
               "/interview", "/posts/2026-08-18-board-pack-hours.md")

    def all_screens_render(self):
        for path in self.SCREENS:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_a_post_whose_front_matter_is_not_yaml(self):
        (self.root / "posts" / "2026-01-01-broken.md").write_text(
            "---\ndate: [unclosed\nhook: |\n  x\n---\n\nbody\n",
            encoding="utf-8")
        self.all_screens_render()
        self.assertIn("2026-01-01-broken.md", self.client.get("/").text)

    def test_a_post_holding_bytes_that_are_not_text(self):
        (self.root / "posts" / "2026-01-01-bytes.md").write_bytes(
            b"---\ndate: 2026-01-01\n---\n\n\xff\xfe body\n")
        self.all_screens_render()

    def test_a_post_nobody_may_open(self):
        import os
        path = self.root / "posts" / "2026-08-25-agency-segment.md"
        os.chmod(path, 0o000)
        try:
            self.all_screens_render()
        finally:
            os.chmod(path, 0o644)

    def test_a_corpus_file_saved_in_another_encoding(self):
        # What corpus/ is for: older writing exported from another tool. The
        # index links every name it globs, so the link has to land somewhere.
        (self.root / "corpus" / "old.md").write_bytes(
            "Une idée, écrite en 2024.\n".encode("latin-1"))
        self.all_screens_render()
        page = self.client.get("/corpus/old.md")
        self.assertEqual(page.status_code, 200)
        self.assertIn("will not come back as text", page.text)

    def test_a_corpus_file_nobody_may_open(self):
        import os
        path = self.root / "corpus" / "2026-07-02-eleven-slides.md"
        os.chmod(path, 0o000)
        try:
            self.all_screens_render()
            self.assertEqual(self.client.get(f"/corpus/{path.name}").status_code,
                             200)
        finally:
            os.chmod(path, 0o644)

    def test_a_post_that_does_not_read_still_has_a_screen(self):
        name = "2026-01-01-bytes.md"
        (self.root / "posts" / name).write_bytes(
            b"---\ndate: 2026-01-01\n---\n\n\xff\xfe body\n")
        page = self.client.get(f"/posts/{name}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("will not come back as text", page.text)

    def test_the_measurement_is_not_written_over_a_file_that_does_not_read(self):
        name = "2026-01-01-bytes.md"
        path = self.root / "posts" / name
        original = b"---\ndate: 2026-01-01\n---\n\n\xff\xfe body\n"
        path.write_bytes(original)
        reply = self.client.post(f"/posts/{name}/measure",
                                 data={"inbound_dms": "3"})
        self.assertEqual(reply.status_code, 200)  # after the 303
        self.assertEqual(path.read_bytes(), original)
        self.assertNotIn("Saved", reply.text)

    def test_a_missing_file_is_still_a_404(self):
        # The two states want different screens: one is a file to create, the
        # other is a file to repair.
        self.assertEqual(self.client.get("/corpus/nope.md").status_code, 404)
        self.assertEqual(self.client.get("/posts/nope.md").status_code, 404)

    def test_a_profile_holding_bytes_that_are_not_text(self):
        (self.root / "profile.md").write_bytes(b"# Profile\n\n\xff\xfe\n")
        self.all_screens_render()
        page = self.client.get("/").text
        self.assertIn("is there and cannot be read", page)
        # The report is a superset, never a replacement: the unreadable file
        # does not swallow what was already known about it.
        self.assertIn("does not parse", page)


class TestTheLanguagePacks(unittest.TestCase):
    """A placeholder is part of the key's contract, not part of its prose.

    `Strings.__call__` swallows a format error and returns the text as it is,
    which is the right call at runtime and the wrong one to find out about in
    front of somebody: the screen then shows a literal brace. This is where a
    renamed placeholder gets caught instead.
    """

    def packs(self):
        from verbatim_app.i18n import _load_pack
        return _load_pack("en"), _load_pack("fr")

    def placeholders(self, text):
        return set(re.findall(r"\{(\w+)\}", text)) if isinstance(text, str) else set()

    def test_every_translated_string_keeps_the_placeholders_it_is_given(self):
        base, other = self.packs()
        for key, english in base.items():
            if key not in other:
                continue
            self.assertEqual(self.placeholders(english),
                             self.placeholders(other[key]),
                             f"placeholders differ for {key}")

    def test_the_french_pack_is_complete(self):
        base, other = self.packs()
        missing = sorted(set(base) - set(other) - {"language", "native_reviewed"})
        self.assertEqual(missing, [])


class TestScreens(WebCase):
    def test_overview_shows_status_and_next_session(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("2026-09-03", page.text)
        self.assertIn("Overview", page.text)

    def test_conformant_instance_shows_no_gap_banner(self):
        page = self.client.get("/")
        self.assertNotIn("does not pass conformance", page.text)

    def test_profile_screen_carries_the_file_verbatim(self):
        page = self.client.get("/profile")
        self.assertIn("Fractional CFO work", page.text)

    def test_saving_the_profile_writes_the_file(self):
        text = Instance(self.root).read("profile.md") + "\nOne more line.\n"
        reply = self.client.post("/profile", data={"content": text})
        self.assertEqual(reply.status_code, 200)  # after the 303 redirect
        self.assertEqual(Instance(self.root).read("profile.md"), text)
        self.assertIn("Saved.", reply.text)

    def test_ideas_screen_lists_the_bank(self):
        page = self.client.get("/ideas")
        self.assertEqual(page.text.count('class="badge mono"'), 5)
        self.assertIn("VISIBILITY", page.text)
        self.assertIn("Used", page.text)

    def test_posts_screen_lists_both_posts(self):
        page = self.client.get("/posts")
        self.assertIn("2026-08-25", page.text)
        self.assertIn("2026-08-18", page.text)
        self.assertIn("not yet", page.text)

    def test_post_detail_shows_the_body(self):
        page = self.client.get("/posts/2026-08-25-agency-segment.md")
        self.assertIn("I spent four months selling to agencies", page.text)

    def test_post_detail_shows_both_axes(self):
        # A format is a shape, a label is an effect on the reader, and
        # references/formats.md keeps them apart. A screen showing one of
        # them quietly makes them the same choice. Both are read through the
        # pack, like the measure screen reads them: a raw TRUST beside a
        # translated format is the language leak with one foot in the door.
        page = self.client.get("/posts/2026-08-18-board-pack-hours.md")
        self.assertIn("The breakdown", page.text)
        self.assertIn("Trust", page.text)
        self.assertNotIn("TRUST", page.text)

    def test_post_detail_describes_the_post_on_disk(self):
        # One triple over one text. The signature share is a share of the
        # count beside it, not of the count the front matter remembers.
        page = self.client.get("/posts/2026-08-18-board-pack-hours.md")
        self.assertIn("2 paragraphs, 138 characters", page.text)
        self.assertNotIn("1487", page.text)

    def test_a_profile_with_no_signature_block_still_paints_a_post(self):
        # The one file this screen reads besides the post. `signature()`
        # raises on a renamed heading by design, and every other screen
        # survives that state.
        path = self.root / "profile.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "## Signature block", "## Sign-off"), encoding="utf-8")
        page = self.client.get("/posts/2026-08-18-board-pack-hours.md")
        self.assertEqual(page.status_code, 200)
        self.assertIn("2 paragraphs", page.text)

    def test_unknown_post_is_404(self):
        self.assertEqual(self.client.get("/posts/nope.md").status_code, 404)

    def test_measurement_form_writes_the_front_matter(self):
        reply = self.client.post(
            "/posts/2026-08-25-agency-segment.md/measure",
            data={"measured": "2026-09-01", "inbound_connections": "2",
                  "inbound_dms": "0", "meeting_mentions": "1",
                  "note": "Came up in a founder call."},
        )
        self.assertEqual(reply.status_code, 200)
        post = [p for p in Instance(self.root).posts()
                if p.filename == "2026-08-25-agency-segment.md"][0]
        self.assertEqual(post.measured, "2026-09-01")
        self.assertEqual(post.inbound_connections, 2)
        self.assertEqual(post.note, "Came up in a founder call.")

    def test_a_backslash_note_does_not_kill_the_screens(self):
        # Regression: this exact POST used to write unreadable YAML and turn
        # every screen into a 500 until the file was repaired by hand.
        reply = self.client.post(
            "/posts/2026-08-18-board-pack-hours.md/measure",
            data={"measured": "2026-09-01", "inbound_connections": "0",
                  "inbound_dms": "0", "meeting_mentions": "0",
                  "note": "screenshot saved to C:\\Users\\alex\\post.png"},
        )
        self.assertEqual(reply.status_code, 200)
        for path in ("/", "/posts", "/posts/2026-08-18-board-pack-hours.md"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_a_negative_count_is_refused(self):
        reply = self.client.post(
            "/posts/2026-08-25-agency-segment.md/measure",
            data={"measured": "", "inbound_connections": "-5",
                  "inbound_dms": "", "meeting_mentions": "", "note": ""},
        )
        self.assertEqual(reply.status_code, 422)

    def test_a_bad_count_is_refused(self):
        reply = self.client.post(
            "/posts/2026-08-25-agency-segment.md/measure",
            data={"measured": "", "inbound_connections": "many",
                  "inbound_dms": "", "meeting_mentions": "", "note": ""},
        )
        self.assertEqual(reply.status_code, 422)

    def test_corpus_screens(self):
        self.assertIn("2026-07-02-eleven-slides.md", self.client.get("/corpus").text)
        page = self.client.get("/corpus/2026-07-02-eleven-slides.md")
        self.assertEqual(page.status_code, 200)

    def test_gap_banner_appears_when_a_companion_is_missing(self):
        (self.root / "voice.md").unlink()
        page = self.client.get("/")
        self.assertIn("voice.md", page.text)
        self.assertIn("does not pass conformance", page.text)


POST_WITH_NOTES = """---
date: 2026-08-30
pillar: 2
format: the-story
label: TRUST
hook: |
  A hook.
chars: 40
state: draft
published_ref: ""
measured:
inbound_connections:
inbound_dms:
meeting_mentions:
note: ""
---

A hook.

The post itself, with a **bold** run and a ## that is not a heading.

Nadia Feriel, fractional CFO.

---

Session notes, not published:

- Interview: interviews/2026-08-30-01, kept as it is.
- Angle: The migration nobody asked for
- Anchors offered, the claim then the interview sentence backing it.
  - 'four months' <- 'I spent four months selling to agencies.'
"""


def copy_source(page: str, element_id: str):
    """The bytes the server put in the page for a copy button, read back the
    way the browser would.

    Entities undone, and one leading newline dropped, because that is what an
    HTML parser does with the first newline after a `<pre>` start tag. The
    templates write one there for it to eat. A helper that skipped this step
    would pass while the browser handed back a file short of a byte, which is
    exactly how the bug was there in the first place.
    """
    found = re.search(rf'<pre[^>]*id="{element_id}"[^>]*>(.*?)</pre>',
                      page, re.S)
    if not found:
        return None
    text = found.group(1)
    return html_module.unescape(text[1:] if text.startswith("\n") else text)


class TestADocumentIsReadAsOne(WebCase):
    """Everything an instance holds except the body of a post is markdown,
    and reading markdown by hand is the thing this app exists to stop. The
    file itself stays on the screen underneath, because a renderer that is
    the only way in hides whatever it has no shape for."""

    def test_the_profile_is_rendered(self):
        page = self.client.get("/profile").text
        self.assertIn("<h2>Status</h2>", page)
        # profile.md has a table in it, which the commonmark preset has no
        # rule for. This is why the preset is `default`.
        self.assertIn("<table>", page)

    def test_the_profile_file_is_still_there_to_edit(self):
        page = self.client.get("/profile").text
        self.assertIn("<textarea", page)
        self.assertIn("## Status", html_module.unescape(page))

    def test_a_corpus_file_is_rendered(self):
        page = self.client.get("/corpus/2026-07-02-eleven-slides.md").text
        self.assertIn("<h1>", page)

    def test_a_corpus_file_keeps_its_own_bytes_on_the_screen(self):
        page = self.client.get("/corpus/2026-07-02-eleven-slides.md").text
        self.assertIn("<details", page)
        raw = copy_source(page, "document-markdown")
        self.assertEqual(
            raw, Instance(self.root).corpus_text("2026-07-02-eleven-slides.md"))

    def test_a_file_that_opens_on_a_blank_line_keeps_it(self):
        """The byte an HTML parser eats. Every payload is written with a
        newline of its own for it to take instead."""
        text = "\n\nOpened on two blank lines.\n"
        (self.root / "corpus" / "blank.md").write_text(text, encoding="utf-8")
        page = self.client.get("/corpus/blank.md").text
        self.assertEqual(copy_source(page, "document-markdown"), text)

    def test_a_file_that_does_not_read_is_not_rendered_at_all(self):
        (self.root / "corpus" / "old.md").write_bytes(
            "Une idée, écrite en 2024.\n".encode("latin-1"))
        page = self.client.get("/corpus/old.md").text
        self.assertIn("will not come back as text", page)
        self.assertIsNone(copy_source(page, "document-markdown"))


class TestNothingInAFileBecomesMarkupOnAScreen(WebCase):
    """The boundary this slice creates. corpus/ takes exports from other
    tools and profile.md takes whatever somebody pasted; both now reach a
    browser as HTML."""

    def test_a_script_tag_in_the_profile_is_shown_not_run(self):
        Instance(self.root).write(
            "profile.md",
            "## Status\n\n- filled: yes\n\n<script>alert(1)</script>\n")
        page = self.client.get("/profile").text
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_an_image_in_a_corpus_file_fetches_nothing(self):
        """A one pixel GIF in an export would report every time its file is
        opened, from a screen whose own rail says nothing leaves."""
        (self.root / "corpus" / "tracked.md").write_text(
            "![](https://pixel.example/p.gif)\n", encoding="utf-8")
        page = self.client.get("/corpus/tracked.md").text
        self.assertNotIn("<img", page)
        self.assertIn("https://pixel.example/p.gif", page)


class TestThePostScreenIsTwoThings(WebCase):
    """The contract already says the file is a post and then the session
    notes. The screen stops pretending it is one block."""

    def setUp(self):
        super().setUp()
        self.name = "2026-08-30-with-notes.md"
        (self.root / "posts" / self.name).write_text(POST_WITH_NOTES,
                                                     encoding="utf-8")

    def test_the_post_is_not_rendered(self):
        """LinkedIn has no markdown, and the `copy` tier pastes these bytes
        as they stand. A heading on this screen would be a heading nowhere
        else."""
        page = self.client.get(f"/posts/{self.name}").text
        self.assertNotIn("<strong>bold</strong>", page)
        self.assertIn("**bold**", page)

    def test_the_notes_are_rendered(self):
        page = self.client.get(f"/posts/{self.name}").text
        self.assertIn("<li>", page)
        self.assertIn("The migration nobody asked for", page)

    def test_a_post_with_no_seam_shows_no_notes_section(self):
        page = self.client.get("/posts/2026-08-25-agency-segment.md").text
        self.assertIn("I spent four months selling to agencies", page)
        self.assertNotIn("Session notes", page)


class TestWhatTheCopyButtonWouldPutOnTheClipboard(WebCase):
    """The one that matters. The body of a post file carries the sheet,
    every anchor the engine claimed and the interview sentence behind each
    one, and a button that copied the file body would put all of it in a
    feed."""

    def setUp(self):
        super().setUp()
        self.name = "2026-08-30-with-notes.md"
        (self.root / "posts" / self.name).write_text(POST_WITH_NOTES,
                                                     encoding="utf-8")

    def test_it_is_exactly_what_publishing_would_send(self):
        from verbatim_app.archive import post_only
        page = self.client.get(f"/posts/{self.name}").text
        self.assertEqual(
            copy_source(page, "post-text"),
            post_only(Instance(self.root).post_body(self.name)))

    def test_it_carries_no_session_note(self):
        page = self.client.get(f"/posts/{self.name}").text
        payload = copy_source(page, "post-text")
        self.assertNotIn("Session notes", payload)
        self.assertNotIn("I spent four months selling to agencies", payload)
        self.assertNotIn("Anchors offered", payload)
        self.assertNotIn("interviews/2026-08-30-01", payload)

    def test_it_carries_the_signature(self):
        self.assertIn("Nadia Feriel, fractional CFO.",
                      copy_source(self.client.get(f"/posts/{self.name}").text,
                                  "post-text"))

    def test_a_post_that_does_not_read_offers_no_button(self):
        broken = "2026-01-01-bytes.md"
        (self.root / "posts" / broken).write_bytes(
            b"---\ndate: 2026-01-01\n---\n\n\xff\xfe body\n")
        page = self.client.get(f"/posts/{broken}").text
        self.assertIsNone(copy_source(page, "post-text"))
        self.assertNotIn("data-source", page)


class TestTheButtonsThemselvesAreNotInTheHtml(WebCase):
    """No JS, no button, and the text stays selectable. A button rendered
    server side would be a dead button on a screen with no script, and this
    app's rule is that every screen but the interview works without one."""

    def test_a_document_screen_offers_two_payloads_and_no_button(self):
        page = self.client.get("/profile").text
        self.assertIn('data-source="document-markdown"', page)
        self.assertIn('data-source="document-text"', page)
        self.assertNotIn("<button type=\"button\"", page)

    def test_the_plain_text_payload_has_no_markdown_in_it(self):
        page = self.client.get("/profile").text
        text = copy_source(page, "document-text")
        self.assertNotIn("## ", text)
        self.assertIn("Nadia Feriel", text)

    def test_a_file_with_nothing_in_it_offers_no_button(self):
        """Copying the empty string is not a thing anybody meant to do, and
        the file that is not there already has a line in the report."""
        (self.root / "profile.md").unlink()
        reply = self.client.get("/profile")
        self.assertEqual(reply.status_code, 200)
        self.assertNotIn("data-source", reply.text)
        self.assertIn("profile.md is missing", reply.text)

    def test_a_file_of_whitespace_still_shows_itself(self):
        """What goes is the button, never the file. Three spaces and a tab
        are still a fact about the instance, and this screen is the only
        place it shows."""
        (self.root / "corpus" / "ws.md").write_text("   \n\t\n  \n",
                                                    encoding="utf-8")
        page = self.client.get("/corpus/ws.md").text
        self.assertNotIn("data-source", page)
        self.assertIn("<details", page)
        self.assertEqual(copy_source(page, "document-markdown"), "   \n\t\n  \n")

    def test_a_post_with_an_empty_body_offers_no_button(self):
        """publish.py refuses an empty post. A button offering one would be
        offering something the next screen along will not take."""
        name = "2026-01-02-empty.md"
        (self.root / "posts" / name).write_text(
            "---\ndate: 2026-01-02\nhook: |\n  x\n---\n\n", encoding="utf-8")
        page = self.client.get(f"/posts/{name}").text
        self.assertNotIn("data-source", page)

    def test_the_labels_come_from_the_pack(self):
        page = self.client.get("/profile").text
        self.assertIn('data-label="Copy the markdown"', page)
        self.assertIn('data-failed=', page)


class TestFrenchPack(WebCase):
    lang = "fr"

    def test_the_interface_speaks_french(self):
        page = self.client.get("/")
        self.assertIn("Vue d&#39;ensemble", page.text.replace("Vue d'ensemble", "Vue d&#39;ensemble"))
        self.assertIn("Prochaine session", page.text)

    def test_states_are_translated(self):
        self.assertIn("publié", self.client.get("/posts").text)


class TestLoopbackDiscipline(WebCase):
    def test_cross_origin_post_is_refused(self):
        reply = self.client.post("/profile", data={"content": "stolen"},
                                 headers={"Origin": "https://evil.example"})
        self.assertEqual(reply.status_code, 403)
        self.assertIn("Fractional CFO work", Instance(self.root).read("profile.md"))

    def test_a_rebound_host_is_refused(self):
        # DNS rebinding: the browser resolves an attacker's name to 127.0.0.1
        # and sends no Origin on GET. The Host header gives it away.
        reply = self.client.get("/profile", headers={"Host": "evil.example"})
        self.assertEqual(reply.status_code, 403)
        self.assertNotIn("Fractional CFO work", reply.text)

    def test_same_origin_post_passes(self):
        text = Instance(self.root).read("profile.md")
        reply = self.client.post("/profile", data={"content": text},
                                 headers={"Origin": "http://127.0.0.1:8747"})
        self.assertEqual(reply.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
