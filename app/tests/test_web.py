"""Tests for the cold screens, against the Nadia Feriel example instance.

Needs fastapi and httpx, so run through the project environment:
    cd app && uv run --extra test python -m unittest discover -s tests
"""

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

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-web-")
        self.root = Path(self.tmp) / "instance"
        shutil.copytree(REPO / "examples", self.root)
        (self.root / "README.md").unlink(missing_ok=True)
        self.client = TestClient(create_app(self.root, lang=self.lang),
                                 base_url="http://127.0.0.1:8747")

    def tearDown(self):
        shutil.rmtree(self.tmp)


class TestOneBadFileDoesNotTakeTheAppDown(WebCase):
    """Every screen renders the conformance report, so a file nobody can read
    decides whether one row is wrong or the whole app is gone."""

    SCREENS = ("/", "/profile", "/ideas", "/posts", "/corpus", "/interview")

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
        self.assertEqual(page.text.count('class="badge mono"'), 9)
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
