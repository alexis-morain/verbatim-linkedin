"""Tests for the editing screens: the profile, the two companion documents,
the page, and the angle bank.

The rule they all hold is one rule: a form carries a digest of what was on the
screen, and a mismatch writes nothing. The rest is what a person sees when a
file is not there, will not read, or says something the contract refuses.

    cd app && uv run --quiet python -m unittest discover -s tests
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from fastapi.testclient import TestClient  # noqa: E402
from markupsafe import escape  # noqa: E402

from verbatim_app import interview  # noqa: E402
from verbatim_app.instance import Instance  # noqa: E402
from verbatim_app.web import create_app  # noqa: E402


def shown(sentence: str) -> str:
    """A pack sentence as the page carries it, apostrophes escaped."""
    return str(escape(sentence))


class WebCase(unittest.TestCase):
    lang = None
    environ = {"ANTHROPIC_API_KEY": "sk-test"}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-edit-web-")
        self.root = Path(self.tmp) / "instance"
        shutil.copytree(REPO / "examples", self.root)
        shutil.rmtree(self.root / "interviews", ignore_errors=True)
        (self.root / "README.md").unlink(missing_ok=True)
        self.instance = Instance(self.root)
        self.app = create_app(self.root, lang=self.lang,
                              environ=dict(self.environ))
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8747")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def strings(self):
        return self.app.state.t

    def section(self, name, heading):
        return [s for s in self.instance.sections(name)
                if s.heading == heading][0]


class TestTheScreensRender(WebCase):
    SCREENS = ("/profile", "/voice", "/pillars", "/page", "/ideas", "/settings")

    def test_every_new_screen_answers_on_the_example_instance(self):
        for path in self.SCREENS:
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_the_rail_reaches_them(self):
        page = self.client.get("/").text
        for path in self.SCREENS:
            self.assertIn(f'href="{path}"', page)

    def test_a_profile_section_carries_its_own_digest(self):
        page = self.client.get("/profile").text
        section = self.section("profile.md", "Core conviction")
        self.assertIn(f'value="{section.digest}"', page)
        self.assertIn('action="/profile/section"', page)

    def test_the_status_block_is_a_form_and_not_a_textarea(self):
        """It moved to the settings screen, and it is still a form there. The
        two language axes are about the installation rather than about the
        person, and what this refuses either way is a textarea holding a whole
        profile as the way to change one of them."""
        page = self.client.get("/settings").text
        self.assertIn('action="/profile/status"', page)
        self.assertIn('name="interface_language"', page)
        self.assertNotIn('name="content"', page)

    def test_the_profile_screen_shows_the_status_and_points_at_it(self):
        page = self.client.get("/profile").text
        self.assertIn(shown(self.strings()("profile.status_hint")), page)
        self.assertIn(shown(self.strings()("profile.language_elsewhere")), page)
        # One writer, and it is not this screen any more.
        self.assertNotIn('action="/profile/status"', page)

    def test_the_whole_file_is_still_reachable(self):
        page = self.client.get("/profile").text
        self.assertIn('action="/profile"', page)
        self.assertIn('name="content"', page)
        self.assertIn('data-label="Copy the markdown"', page)

    def test_the_other_editors_have_the_whole_file_too(self):
        # The duplicate heading notice sends the person to the whole file
        # below, on every screen that can show the notice.
        for screen, name in (("/voice", "voice.md"), ("/pillars", "pillars.md")):
            page = self.client.get(screen).text
            self.assertIn(f'action="{screen}"', page)
            self.assertIn('rows="34"', page)
            reply = self.client.post(screen, data={"content": "# New\n\n## One\n\nx\n"})
            self.assertEqual(reply.status_code, 200)
            self.assertEqual((self.root / name).read_text(encoding="utf-8"),
                             "# New\n\n## One\n\nx\n")

    def test_a_forged_section_name_is_refused_on_the_screen(self):
        before = (self.root / "ideas.md").read_text(encoding="utf-8")
        reply = self.client.post("/ideas/add", data={
            "section": "Evil\n\n## Used\n\n2020-01-01 | P9 | forged | posts/z.md",
            "pillar": "1", "label": "TRUST", "text": "x"}, follow_redirects=False)
        self.assertEqual(reply.headers["location"], "/ideas?problem=bad-angle")
        self.assertEqual((self.root / "ideas.md").read_text(encoding="utf-8"), before)

    def test_the_voice_screen_says_what_belongs_in_the_file(self):
        page = self.client.get("/voice").text
        self.assertIn(shown(self.strings()("voice.hint")), page)
        self.assertIn('action="/voice/section"', page)

    def test_a_file_that_is_not_there_says_so_out_of_the_pack(self):
        # linkedin-page.md is optional, and its absence is not a gap.
        self.assertIn(shown(self.strings()("page.missing")),
                      self.client.get("/page").text)
        (self.root / "voice.md").unlink()
        self.assertIn(shown(self.strings()("voice.missing")),
                      self.client.get("/voice").text)

    def test_the_page_is_rendered_and_offered_raw(self):
        (self.root / "linkedin-page.md").write_text(
            "---\nupdated: 2026-08-30\n---\n\n## Headline\n\nCFO in the room.\n",
            encoding="utf-8")
        page = self.client.get("/page").text
        self.assertIn("CFO in the room.", page)
        self.assertIn('class="raw"', page)
        self.assertNotIn('action="/page', page)


class TestSavingOneSection(WebCase):
    def test_a_section_is_written_and_updated_moves(self):
        section = self.section("profile.md", "What I fight")
        before = self.instance.read("profile.md")
        reply = self.client.post("/profile/section", data={
            "heading": section.heading, "shown": section.digest,
            "content": "The board deck that forecasts nothing."})
        self.assertEqual(reply.status_code, 200)
        after = self.instance.read("profile.md")
        self.assertIn("The board deck that forecasts nothing.", after)
        self.assertNotIn(section.body, after)
        self.assertNotEqual(self.instance.status().updated, "2026-08-20")
        self.assertIn("- filled: yes", after)
        self.assertIn("- source: interview", after)
        # The neighbours are where they were. The byte for byte case is in
        # test_instance.py, on a file whose Status line does not move.
        self.assertIn(self.section("profile.md", "Core conviction").body,
                      before)

    def test_a_stale_digest_writes_nothing_and_the_screen_says_so(self):
        before = self.instance.read("profile.md")
        reply = self.client.post("/profile/section", data={
            "heading": "Core conviction", "shown": "0" * 16,
            "content": "Something nobody read."})
        self.assertEqual(reply.status_code, 200)
        self.assertIn(shown(self.strings()("profile.section_changed")),
                      reply.text)
        self.assertEqual(self.instance.read("profile.md"), before)

    def test_a_companion_file_moves_nothing_in_the_profile(self):
        before = self.instance.read("profile.md")
        section = self.instance.sections("pillars.md")[0]
        reply = self.client.post("/pillars/section", data={
            "heading": section.heading, "shown": section.digest,
            "content": "Two of six, and why."})
        self.assertEqual(reply.status_code, 200)
        self.assertIn("Two of six, and why.", self.instance.read("pillars.md"))
        self.assertEqual(self.instance.read("profile.md"), before)

    def test_the_status_block_has_one_writer_and_it_is_its_own_form(self):
        section = self.section("profile.md", "Status")
        reply = self.client.post("/profile/section", data={
            "heading": "Status", "shown": section.digest, "content": "- x: y"})
        self.assertEqual(reply.status_code, 404)
        self.assertIn("- filled: yes", self.instance.read("profile.md"))

    def test_a_heading_this_file_does_not_have_is_a_stale_form(self):
        reply = self.client.post("/voice/section",
                                 data={"heading": "Nowhere", "shown": "x",
                                       "content": "y"})
        self.assertEqual(reply.status_code, 404)

    def test_an_unvalidated_section_is_marked(self):
        section = self.section("profile.md", "Core conviction")
        self.client.post("/profile/section", data={
            "heading": section.heading, "shown": section.digest,
            "content": "<what you hold to be true>"})
        page = self.client.get("/profile").text
        self.assertIn(shown(self.strings()("profile.unvalidated")), page)
        self.assertIn(shown(self.strings()("profile.unvalidated_hint")), page)

    def test_a_heading_the_file_carries_twice_gets_no_form(self):
        self.instance.write("voice.md",
                            "# Voice\n\n## Traits\n\na\n\n## Traits\n\nb\n")
        page = self.client.get("/voice").text
        self.assertIn(shown(self.strings()("profile.duplicate")), page)
        self.assertNotIn('action="/voice/section"', page)


class TestTheStatusForm(WebCase):
    def test_the_two_languages_are_saved(self):
        reply = self.client.post("/profile/status",
                                 data={"interface_language": "fr",
                                       "output_language_default": "en"})
        self.assertEqual(reply.status_code, 200)
        status = self.instance.status()
        self.assertEqual(status.interface_language, "fr")
        self.assertEqual(status.source, "interview")

    def test_a_sentence_where_a_code_goes_writes_nothing(self):
        before = self.instance.read("profile.md")
        reply = self.client.post("/profile/status",
                                 data={"interface_language": "en français",
                                       "output_language_default": "en"})
        self.assertEqual(reply.status_code, 200)
        self.assertIn(shown(self.strings()("profile.bad_language")), reply.text)
        self.assertEqual(self.instance.read("profile.md"), before)


class TestTheAngleBank(WebCase):
    def texts(self):
        return [angle.text for angle in self.instance.ideas().angles]

    def test_an_angle_is_added_edited_and_removed_from_the_screen(self):
        section = "Pillar 3. Decisions in public"
        self.client.post("/ideas/add", data={
            "section": section, "pillar": "3", "label": "TRUST",
            "text": "The mandate I priced wrong twice."})
        self.assertIn("The mandate I priced wrong twice.", self.texts())
        self.client.post("/ideas/edit", data={
            "old": "The mandate I priced wrong twice.", "pillar": "3",
            "label": "ACTION", "text": "The two mandates I priced wrong."})
        self.assertIn("The two mandates I priced wrong.", self.texts())
        self.client.post("/ideas/remove",
                         data={"text": "The two mandates I priced wrong."})
        self.assertNotIn("The two mandates I priced wrong.", self.texts())

    def test_an_angle_the_contract_refuses_says_why(self):
        before = self.instance.read("ideas.md")
        reply = self.client.post("/ideas/add", data={
            "section": "Pillar 1. The argument, not the arithmetic",
            "pillar": "4", "label": "TRUST", "text": "Off the map."})
        self.assertIn(shown(self.strings()("ideas.bad_angle")), reply.text)
        self.assertEqual(self.instance.read("ideas.md"), before)

    def test_an_angle_somebody_else_removed_says_that_instead(self):
        reply = self.client.post("/ideas/remove",
                                 data={"text": "not in the bank"})
        self.assertIn(shown(self.strings()("ideas.angle_gone")), reply.text)

    def test_the_add_form_offers_the_sections_the_file_has(self):
        page = self.client.get("/ideas").text
        self.assertIn('action="/ideas/add"', page)
        self.assertIn('value="Pillar 2. What I actually do in the room"', page)

    def test_writing_one_opens_an_interview_and_writes_nothing(self):
        before = self.instance.read("ideas.md")
        angle = self.instance.ideas().angles[0]
        page = self.client.get("/ideas").text
        self.assertIn(shown(self.strings()("ideas.write_this")), page)
        reply = self.client.post("/interview",
                                 data={"seed": angle.text},
                                 follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertIn("seed=", reply.headers["location"])
        self.assertEqual(self.instance.read("ideas.md"), before)


class TestASeededInterview(WebCase):
    def test_the_box_opens_on_the_angle_and_nothing_else_does(self):
        angle = self.instance.ideas().angles[0]
        landing = self.client.post("/interview", data={"seed": angle.text},
                                   follow_redirects=False).headers["location"]
        page = self.client.get(landing).text
        self.assertIn(shown(angle.text) + "</textarea>", page)

    def test_a_conversation_already_under_way_is_not_seeded(self):
        angle = self.instance.ideas().angles[0]
        landing = self.client.post("/interview", data={"seed": angle.text},
                                   follow_redirects=False).headers["location"]
        interview_id = landing.split("?")[0].rsplit("/", 1)[-1]
        conversation = interview.load(self.root, interview_id)
        interview.say(conversation, "Something I already typed.")
        interview.save(self.root, conversation)
        self.assertNotIn(shown(angle.text) + "</textarea>",
                         self.client.get(landing).text)


class TestAFileThatWillNotRead(WebCase):
    """A profile saved in another encoding is one file, not the whole app."""

    SCREENS = ("/", "/profile", "/voice", "/pillars", "/page", "/ideas",
               "/posts", "/corpus", "/interview")

    def cripple(self, name):
        (self.root / name).write_bytes("Une idée.\n".encode("latin-1"))

    def test_every_screen_still_renders(self):
        self.cripple("profile.md")
        for path in self.SCREENS:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertIn(shown(self.strings()("profile.unreadable")),
                      self.client.get("/profile").text)

    def test_no_form_is_offered_over_it(self):
        self.cripple("voice.md")
        page = self.client.get("/voice").text
        self.assertNotIn('action="/voice/section"', page)
        self.assertIn(shown(self.strings()("profile.unreadable")), page)

    def test_a_write_against_it_writes_nothing(self):
        self.cripple("profile.md")
        before = (self.root / "profile.md").read_bytes()
        for path, data in (("/profile/section",
                            {"heading": "What I fight", "shown": "x",
                            "content": "y"}),
                           ("/profile/status",
                            {"interface_language": "fr",
                             "output_language_default": "fr"}),
                           # The whole file form, from a stale tab: the one
                           # write that used to go through.
                           ("/profile", {"content": "WIPED"})):
            reply = self.client.post(path, data=data)
            self.assertEqual(reply.status_code, 200, path)
        self.assertEqual((self.root / "profile.md").read_bytes(), before)

    def test_an_unreadable_bank_refuses_a_write_without_a_traceback(self):
        self.cripple("ideas.md")
        before = (self.root / "ideas.md").read_bytes()
        reply = self.client.post("/ideas/add", data={
            "section": "Pillar 1", "pillar": "1", "label": "TRUST",
            "text": "Anything."})
        self.assertEqual(reply.status_code, 200)
        self.assertEqual((self.root / "ideas.md").read_bytes(), before)


class TestAFileNobodyMayOpen(WebCase):
    def test_the_screens_hold(self):
        path = self.root / "voice.md"
        os.chmod(path, 0o000)
        try:
            for screen in ("/", "/profile", "/voice", "/pillars", "/ideas"):
                self.assertEqual(self.client.get(screen).status_code, 200,
                                 screen)
        finally:
            os.chmod(path, 0o644)


class TestFrenchPack(WebCase):
    lang = "fr"

    def test_the_editing_screens_speak_french(self):
        self.assertIn(shown(self.strings()("profile.status_hint")),
                      self.client.get("/profile").text)
        self.assertIn("Piliers", self.client.get("/pillars").text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestTheSettingsScreen(WebCase):
    """What this installation is set to, and who it came from.

    The one thing this screen must never grow is a field for the key. It says
    where the key goes; taking it would put a secret in a form post, in a
    browser's history, and in an app whose whole boundary is that the machine
    owns the key and the instance owns the person.
    """

    def test_both_language_axes_are_lists_of_the_packs_that_exist(self):
        page = self.client.get("/settings").text
        for axis in ("interface_language", "output_language_default"):
            self.assertIn(f'<select id="{axis}" name="{axis}">', page)
        for code in ("en", "fr"):
            self.assertIn(f'<option value="{code}"', page)
        # The contract is not a language. A translator copies it; nobody is
        # interviewed in it.
        self.assertNotIn('value="_template"', page)

    def test_the_key_is_never_a_field_on_this_screen(self):
        page = self.client.get("/settings").text
        self.assertNotIn('type="password"', page)
        self.assertNotIn('name="api_key"', page)
        self.assertNotIn("sk-test", page)

    def test_saving_from_here_comes_back_here(self):
        reply = self.client.post("/profile/status",
                                 data={"interface_language": "fr",
                                       "output_language_default": "en",
                                       "back": "/settings"},
                                 follow_redirects=False)
        self.assertEqual(reply.headers["location"], "/settings?saved=1")
        self.assertEqual(self.instance.status().interface_language, "fr")

    def test_a_back_nobody_offered_lands_on_the_profile(self):
        """The field is posted, so it is somebody else's to write. An echoed
        path is an open redirect, and this app is one a browser is already
        trusting with a local origin."""
        reply = self.client.post("/profile/status",
                                 data={"interface_language": "fr",
                                       "output_language_default": "en",
                                       "back": "https://example.invalid/"},
                                 follow_redirects=False)
        self.assertEqual(reply.headers["location"], "/profile?saved=1")

    def test_a_refused_language_comes_back_to_the_screen_it_left(self):
        reply = self.client.post("/profile/status",
                                 data={"interface_language": "not a code",
                                       "output_language_default": "en",
                                       "back": "/settings"},
                                 follow_redirects=False)
        self.assertEqual(reply.headers["location"],
                         "/settings?problem=bad-language")

    def test_a_language_set_with_no_pack_is_still_offered(self):
        """Saving this form must not quietly change what somebody chose, and
        a select that dropped the value would do exactly that."""
        self.instance.update_status(interface_language="pt-BR",
                                    output_language_default="en",
                                    today="2026-09-04")
        page = self.client.get("/settings").text
        self.assertIn('<option value="pt-BR" selected>', page)
        self.assertIn(shown(self.strings()("settings.language_unknown",
                                           detail="pt-BR")), page)

    def test_where_the_key_goes_is_said_in_the_words_of_this_launcher(self):
        page = self.client.get("/settings").text
        self.assertIn(shown(self.strings()("settings.key_shell")), page)
        self.assertNotIn(shown(self.strings()("settings.key_macos")), page)

    def test_the_macos_launcher_says_so_and_the_screen_follows(self):
        app = create_app(self.root, lang=self.lang,
                         environ=dict(self.environ, VERBATIM_LAUNCHER="macos"))
        page = TestClient(app, base_url="http://127.0.0.1:8747") \
            .get("/settings").text
        self.assertIn(shown(self.strings()("settings.key_macos")), page)
        self.assertNotIn(shown(self.strings()("settings.key_shell")), page)

    def test_the_local_model_fix_survives_a_refused_configuration(self):
        """The `OLLAMA_CONTEXT_LENGTH` line used to hang off the engine's
        block size, which is zero whenever the configuration was refused
        outright. The loudest refusal here is somebody pointing at an Ollama
        that is not on this machine, and that is exactly the reader this
        paragraph exists for: their window is the silent failure."""
        (self.root / ".env").write_text(
            "VERBATIM_BASE_URL=https://ollama.example.invalid/v1\n",
            encoding="utf-8")
        page = self.client.get("/settings").text
        # The panel above it is a refusal, so there is no block size to gate on.
        self.assertNotIn(shown(self.strings()("interview.context")), page)
        self.assertIn("OLLAMA_CONTEXT_LENGTH=16384", page)
        self.assertIn(shown(self.strings()("settings.local_context")), page)

    def test_the_copy_block_never_spells_a_default_of_its_own(self):
        """The one block on this screen somebody is told to trust. A second
        spelling of the engine's default hands them yesterday's model the day
        `providers.DEFAULT_MODEL` moves."""
        from verbatim_app.providers import DEFAULT_MODEL, DEFAULT_PROVIDER
        page = self.client.get("/settings").text
        self.assertIn(f"export VERBATIM_PROVIDER={DEFAULT_PROVIDER}", page)
        self.assertIn(f"export VERBATIM_MODEL={DEFAULT_MODEL[DEFAULT_PROVIDER]}",
                      page)
        template = (REPO / "app" / "verbatim_app" / "templates"
                    / "settings.html").read_text(encoding="utf-8")
        for spelled in (DEFAULT_PROVIDER, DEFAULT_MODEL[DEFAULT_PROVIDER]):
            self.assertNotIn(spelled, template)

    def test_a_root_with_no_locales_comes_back_empty_rather_than_raising(self):
        """The walk used to be `root.iterdir()` with nothing in front of it,
        so a root with no `locales/` raised where it now returns nothing.

        Empty is the right answer and the screen turns it into a sentence
        saying the bundle is broken. Only the walk is exercised here: this
        cannot be driven through the screen, because `bundle_root` refuses to
        resolve a directory that has no `locales/` at all, so the branch
        exists for a root handed in from elsewhere."""
        from verbatim_app.i18n import pack_dirs
        self.assertEqual(pack_dirs(self.tmp), ())
        self.assertTrue(pack_dirs())

    def test_the_copy_block_names_the_key_this_provider_would_be_read_from(self):
        """Found by running it, not by testing it: the block said
        ANTHROPIC_API_KEY on an instance configured for openai, which is a
        line that does nothing when pasted. The tests all ran on the default
        provider, so none of them could see it."""
        (self.root / ".env").write_text("VERBATIM_PROVIDER=openai\n",
                                        encoding="utf-8")
        page = self.client.get("/settings").text
        self.assertIn("export OPENAI_API_KEY=...", page)
        self.assertNotIn("ANTHROPIC_API_KEY=...", page)

    def test_the_default_provider_still_names_its_own_key(self):
        page = self.client.get("/settings").text
        self.assertIn("export ANTHROPIC_API_KEY=...", page)

    def test_the_licence_and_the_place_to_report_are_on_it(self):
        page = self.client.get("/settings").text
        self.assertIn("MIT", page)
        self.assertIn("github.com/alexis-morain/verbatim-linkedin/issues", page)
        self.assertIn(self.app.version, page)
