"""Tests for the publishing screen, the one cold screen that can leave.

The fixture is examples/, the Nadia Feriel persona, copied to a temp
directory. The environment the tier is read from is injected, so a
maintainer's own LINKEDIN_PUBLISH cannot decide what these prove, and the
only tier that opens anything here is `command`, pointed at a shell builtin.

Needs fastapi and httpx:
    cd app && uv run python -m unittest discover -s tests
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from fastapi.testclient import TestClient  # noqa: E402

from verbatim_app.archive import NOTES_MARKER  # noqa: E402
from verbatim_app.instance import Instance  # noqa: E402
from verbatim_app.routes import publish as screen  # noqa: E402
from verbatim_app.tools import ToolUnfinished  # noqa: E402
from verbatim_app.web import create_app  # noqa: E402

NAME = "2026-08-29-with-notes.md"

#: A post file in the shape `archive.compose` writes: front matter, the post,
#: the seam, then the session notes. The notes hold every anchor pair and the
#: interview sentence behind it, which is why what goes to a tier is cut here.
FILE = f"""---
date: 2026-08-29
pillar: 3
format: the-stance
label: TRUST
hook: |
  Eleven conversations, two proposals, nothing signed.
chars: 62
state: draft
published_ref: ""
measured:
inbound_connections:
inbound_dms:
meeting_mentions:
note: ""
---

Eleven conversations, two proposals, nothing signed.

The tool: https://example.com/thing

---

{NOTES_MARKER}

- Interview: interviews/2026-08-29-agences, kept as it is.
- Anchors offered, the claim then the interview sentence backing it.
  - 'Eleven conversations' <- 'I had eleven conversations with agencies'
"""

POST = ("Eleven conversations, two proposals, nothing signed.\n\n"
        "The tool: https://example.com/thing")


class PublishCase(unittest.TestCase):
    tier = {}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-publish-web-")
        self.addCleanup(shutil.rmtree, self.tmp)
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
        (self.root / "posts" / NAME).write_text(FILE, encoding="utf-8")
        self.environ = dict(self.tier)
        self.client = TestClient(create_app(self.root, environ=self.environ),
                                 base_url="http://127.0.0.1:8747")

    def plan(self, **data):
        return self.client.post(f"/posts/{NAME}/publish/plan", data=data)

    def send(self, **data):
        return self.client.post(f"/posts/{NAME}/publish", data=data)

    def digest_from(self, page: str) -> str:
        return self.hidden(page, "shown")

    def hidden(self, page: str, field: str) -> str:
        import re
        found = re.search(rf'name="{field}" value="([0-9a-f]+)"', page)
        self.assertIsNotNone(found, f"the confirm form carries no {field}")
        return found.group(1)

    def confirm(self, page: str, **extra):
        """Confirm the plan on this page, the way the form does: the digest
        and the token that came with it."""
        data = dict(shown=self.hidden(page, "shown"),
                    token=self.hidden(page, "token"))
        data.update(extra)
        return self.send(**data)


class TestThePlanComesFirst(PublishCase):
    def test_the_screen_offers_a_plan_and_no_send_before_it(self):
        page = self.client.get(f"/posts/{NAME}").text
        self.assertIn(f"/posts/{NAME}/publish/plan", page)
        self.assertNotIn(f'action="/posts/{NAME}/publish"', page)

    def test_the_plan_names_the_tier_and_the_target(self):
        page = self.plan().text
        self.assertIn("tier", page)
        self.assertIn("copy", page)

    def test_the_plan_measures_the_post_and_not_the_session_notes(self):
        # The notes are three times the post here. A length computed over the
        # file body would be the wrong number in front of the one decision
        # this screen exists for.
        page = self.plan().text
        self.assertIn(f"{len(POST)} characters", page)
        # The file body is nearly three times that. The screen renders it in
        # full above, under a heading that says it is the file; what a tier is
        # measured against is the post, and the two numbers must not be the
        # same one.
        body = Instance(self.root).post_body(NAME).strip()
        self.assertGreater(len(body), 2 * len(POST))
        self.assertNotIn(f"{len(body)} characters", page)

    def test_the_disclosure_question_reaches_the_screen(self):
        # The post carries a link, so the plan asks. The wording of any
        # disclosure lives in the market pack; the plan only asks.
        self.assertIn("disclose", self.plan().text)

    def test_the_confirm_form_appears_only_after_a_plan(self):
        self.assertIn(f'action="/posts/{NAME}/publish"', self.plan().text)

    def test_a_post_that_does_not_read_is_not_offered_to_a_tier(self):
        broken = "2026-01-01-bytes.md"
        (self.root / "posts" / broken).write_bytes(
            b"---\ndate: 2026-01-01\n---\n\n\xff\xfe body\n")
        page = self.client.get(f"/posts/{broken}").text
        self.assertNotIn(f"/posts/{broken}/publish/plan", page)


class TestNothingIsSentWithoutReadingThePlan(PublishCase):
    tier = {"LINKEDIN_PUBLISH": "command",
            "LINKEDIN_PUBLISH_CMD": "cat > sent.txt && echo ref-42"}

    def sent_file(self):
        return (self.root / "sent.txt")

    def test_a_send_with_no_digest_at_all_sends_nothing(self):
        page = self.send()
        self.assertEqual(page.status_code, 200)
        self.assertFalse(self.sent_file().exists())

    def test_a_token_from_a_forged_field_sends_nothing(self):
        page = self.plan().text
        self.confirm(page, token="0" * 16)
        self.assertFalse(self.sent_file().exists())

    def test_a_valid_digest_with_no_token_sends_nothing(self):
        shown = self.digest_from(self.plan().text)
        self.send(shown=shown)
        self.assertFalse(self.sent_file().exists())

    def test_a_digest_from_another_target_sends_nothing_and_says_so(self):
        # The named accident of this project: three test posts on the wrong
        # page. The plan is read against one channel and the click lands on
        # another, because the environment moved between the two.
        page_before = self.plan().text
        self.environ["LINKEDIN_PUBLISH_CMD"] = "cat > moved.txt"
        page = self.confirm(page_before)
        self.assertFalse((self.root / "moved.txt").exists())
        self.assertFalse(self.sent_file().exists())
        self.assertIn("moved.txt", page.text)  # the plan as it stands now

    def test_a_body_edited_under_the_plan_sends_nothing(self):
        page = self.plan().text
        (self.root / "posts" / NAME).write_text(
            FILE.replace("nothing signed", "nothing signed at all"),
            encoding="utf-8")
        self.confirm(page)
        self.assertFalse(self.sent_file().exists())

    def test_the_matching_digest_sends_the_post_and_only_the_post(self):
        page = self.confirm(self.plan().text)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(self.sent_file().read_text(encoding="utf-8"), POST)
        self.assertIn("ref-42", page.text)

    def test_a_scheduled_time_that_is_not_one_reaches_no_tier(self):
        page = self.plan(when="tomorrow-ish")
        self.assertFalse(self.sent_file().exists())
        self.assertIn("not a time", page.text.lower())

    def test_a_time_that_looks_like_a_flag_reaches_no_tier(self):
        self.plan(when="--confirm")
        self.assertFalse(self.sent_file().exists())

    def test_a_time_may_name_its_own_offset(self):
        # A naked time says nothing about which clock it is in, and the tier
        # reading it may well pick UTC. Saying so is allowed; guessing it here
        # would be a post an hour out, silently.
        page = self.plan(when="2026-09-01T07:30+02:00").text
        self.assertIn("2026-09-01T07:30+02:00", page)
        self.assertNotIn("not a time", page.lower())


class TestOnePlanIsConfirmedOnce(PublishCase):
    """The digest says what is sent, never how many times. A double click and
    a reloaded POST are the two ways one plan becomes two posts."""

    tier = {"LINKEDIN_PUBLISH": "command",
            "LINKEDIN_PUBLISH_CMD": "cat >> sent.txt"}

    def times_sent(self) -> int:
        path = self.root / "sent.txt"
        if not path.exists():
            return 0
        return path.read_text(encoding="utf-8").count("Eleven conversations")

    def test_the_same_plan_confirmed_twice_publishes_once(self):
        page = self.plan().text
        self.confirm(page)
        again = self.confirm(page)
        self.assertEqual(self.times_sent(), 1)
        self.assertIn("already confirmed", again.text)

    def test_a_send_beside_a_running_one_publishes_nothing(self):
        page = self.plan().text
        held = screen.lock_for(self.client.app, NAME)
        self.assertTrue(held.acquire(blocking=False))
        try:
            refused = self.confirm(page)
        finally:
            held.release()
        self.assertEqual(self.times_sent(), 0)
        self.assertIn("already running", refused.text)

    def test_a_token_drawn_for_another_post_confirms_nothing(self):
        other = "2026-08-25-agency-segment.md"
        stolen = self.hidden(
            self.client.post(f"/posts/{other}/publish/plan", data={}).text,
            "token")
        page = self.plan().text
        self.confirm(page, token=stolen)
        self.assertEqual(self.times_sent(), 0)

    def test_two_outstanding_plans_publish_once(self):
        # No attacker in this one. Somebody draws the plan, reads it, draws it
        # again because they wanted another look at the target line, publishes,
        # then uses the back button. Or has the post open in two tabs. The two
        # plans are identical, so the digest cannot tell them apart, and the
        # per plan token gave the duplicate back until drawing one retired the
        # one before it. Found in review, twice around.
        first = self.plan().text
        second = self.plan().text
        self.assertEqual(self.digest_from(second), self.digest_from(first))
        self.confirm(second)
        stale = self.confirm(first)
        self.assertEqual(self.times_sent(), 1)
        self.assertIn("already confirmed", stale.text)

    def test_the_older_plan_is_dead_even_before_the_newer_one_is_used(self):
        first = self.plan().text
        self.plan()
        self.confirm(first)
        self.assertEqual(self.times_sent(), 0)

    def test_a_fresh_plan_after_a_send_still_works(self):
        # The guard is against confirming one plan twice, not against
        # publishing a post twice on purpose. Drawing a new plan is the
        # deliberate act that the reload is not, and it has to actually work:
        # the digest alone cannot tell them apart, since redrawing the same
        # plan over the same post produces the same digest every time.
        first = self.plan().text
        self.confirm(first)
        second = self.plan().text
        self.assertEqual(self.digest_from(second), self.digest_from(first))
        self.assertNotEqual(self.hidden(second, "token"),
                            self.hidden(first, "token"))
        self.confirm(second)
        self.assertEqual(self.times_sent(), 2)


class TestAFailedSendDoesNotLockThePostOut(PublishCase):
    """A refusal is a state somebody recovers from. The first version of the
    replay guard burnt the digest, and since redrawing produces the same
    digest, one ordinary failure made the post unpublishable for the life of
    the process. Found in review."""

    tier = {"LINKEDIN_PUBLISH": "command",
            "LINKEDIN_PUBLISH_CMD": "test -f ok.flag && cat >> sent.txt"}

    def test_a_transient_failure_is_recovered_by_drawing_the_plan_again(self):
        failed = self.confirm(self.plan().text)
        self.assertFalse((self.root / "sent.txt").exists())
        self.assertIn("check the channel", failed.text)  # it was dispatched
        (self.root / "ok.flag").write_text("", encoding="utf-8")
        self.confirm(self.plan().text)
        self.assertIn("Eleven conversations",
                      (self.root / "sent.txt").read_text(encoding="utf-8"))


class TestATierThatWasNeverReachedIsAPlainRefusal(PublishCase):
    """Nothing was dispatched, so the sentence that says nothing was sent is
    true, and it is a different sentence from the one above."""

    tier = {"LINKEDIN_PUBLISH": "command", "LINKEDIN_PUBLISH_CMD": "cat"}

    def test_a_post_the_platform_would_refuse_never_reaches_the_tier(self):
        (self.root / "posts" / NAME).write_text(
            FILE.replace("The tool: https://example.com/thing",
                         "x" * 3200), encoding="utf-8")
        page = self.plan()
        self.assertIn("Nothing was sent", page.text)
        self.assertNotIn("check the channel", page.text)
        self.assertIn("3000", page.text)


class TestADispatchedFailureIsNotAQuietRefusal(PublishCase):
    """The one refusal that must not say nothing was sent. Two ways in and
    they are the same fact: the subprocess was killed, or `publish.py` reached
    the tier and the tier failed."""

    tier = {"LINKEDIN_PUBLISH": "command",
            "LINKEDIN_PUBLISH_CMD": "cat > sent.txt; exit 7"}

    def test_a_tier_that_failed_after_taking_the_post_says_it_may_be_out(self):
        # The realistic shape: the command posted and then failed on
        # something afterwards. Driven through the real publish.py, so this
        # covers the exit code seam rather than a patched function.
        page = self.confirm(self.plan().text).text
        self.assertIn("may be out", page)
        self.assertNotIn("Nothing was sent", page)
        # And it did take the post, which is the whole point.
        self.assertIn("Eleven conversations",
                      (self.root / "sent.txt").read_text(encoding="utf-8"))

    def test_a_killed_subprocess_lands_on_the_same_screen(self):
        def killed(*args, **kwargs):
            raise ToolUnfinished("publish.py did not answer within 180 "
                                 "seconds and was killed")
        previous = screen.publish_send
        screen.publish_send = killed
        try:
            page = self.confirm(self.plan().text).text
        finally:
            screen.publish_send = previous
        self.assertIn("may be out", page)
        self.assertNotIn("Nothing was sent", page)
        self.assertIn("was killed", page)


class TestTheSchedulerNeverGetsRawText(PublishCase):
    tier = {"LINKEDIN_PUBLISH": "postiz",
            "POSTIZ_INTEGRATION_ID": "chan-123",
            "POSTIZ_INTEGRATION_NAME": "Personal profile"}

    def test_the_plan_shows_which_channel_by_name(self):
        page = self.plan().text
        self.assertIn("chan-123", page)
        self.assertIn("Personal profile", page)

    def test_the_payload_is_html_with_the_separators(self):
        page = self.confirm(self.plan(when="2026-09-01T07:30").text,
                            when="2026-09-01T07:30").text
        self.assertIn("&lt;p&gt;", page)      # rendered into the screen
        self.assertIn("&lt;p&gt;&lt;/p&gt;", page)
        self.assertIn("2026-09-01T07:30", page)

    def test_a_channel_with_no_name_is_a_warning_in_the_plan(self):
        self.environ.pop("POSTIZ_INTEGRATION_NAME")
        self.assertIn("POSTIZ_INTEGRATION_NAME", self.plan().text)


class TestATierThatIsNotUsable(PublishCase):
    tier = {"LINKEDIN_PUBLISH": "postiz"}

    def test_the_scripts_own_words_reach_the_screen_framed_as_the_engine(self):
        page = self.plan()
        self.assertEqual(page.status_code, 200)
        self.assertIn("POSTIZ_INTEGRATION_ID", page.text)


class TestTheStateIsThePersonsStatement(PublishCase):
    def test_the_state_and_the_reference_are_written(self):
        reply = self.client.post(
            f"/posts/{NAME}/state",
            data={"state": "published",
                  "published_ref": "https://linkedin.example/p/9"})
        self.assertEqual(reply.status_code, 200)
        post = [p for p in Instance(self.root).posts()
                if p.filename == NAME][0]
        self.assertEqual(post.state, "published")
        self.assertEqual(post.published_ref, "https://linkedin.example/p/9")

    def test_a_state_outside_the_three_writes_nothing(self):
        before = (self.root / "posts" / NAME).read_text(encoding="utf-8")
        page = self.client.post(f"/posts/{NAME}/state",
                                data={"state": "live", "published_ref": ""})
        self.assertEqual(page.status_code, 200)
        self.assertEqual((self.root / "posts" / NAME).read_text(
            encoding="utf-8"), before)

    def test_nothing_is_written_over_a_file_that_does_not_read(self):
        broken = "2026-01-01-bytes.md"
        original = b"---\ndate: 2026-01-01\n---\n\n\xff\xfe body\n"
        (self.root / "posts" / broken).write_bytes(original)
        self.client.post(f"/posts/{broken}/state",
                         data={"state": "published", "published_ref": ""})
        self.assertEqual((self.root / "posts" / broken).read_bytes(), original)


class TestNoGetPublishes(PublishCase):
    tier = {"LINKEDIN_PUBLISH": "command",
            "LINKEDIN_PUBLISH_CMD": "cat > sent.txt"}

    def test_every_publishing_route_refuses_a_get(self):
        for path in (f"/posts/{NAME}/publish/plan", f"/posts/{NAME}/publish",
                     f"/posts/{NAME}/state"):
            self.assertEqual(self.client.get(path).status_code, 405, path)
        self.assertFalse((self.root / "sent.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
