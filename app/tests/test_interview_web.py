"""Tests for the interview screen: the first one that talks to a model.

No key and no socket. Every turn here is a recorded provider stream handed to
the app through the same seam the loop already had, which is the reason that
seam exists.

    cd app && uv run --quiet python -m unittest discover -s tests
"""

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402
from markupsafe import escape  # noqa: E402

from test_agent import Replay, asks, says  # noqa: E402

from verbatim_app import interview  # noqa: E402
from verbatim_app.passages import passages_of, replace_passage
from verbatim_app.shown import shown as digest_of  # noqa: E402
from verbatim_app.web import create_app  # noqa: E402

CONFIGURED = {"ANTHROPIC_API_KEY": "sk-test"}

#: Codes an SSE frame carries. They get an `error_` sentence, not a
#: `refused_` one, and TestEveryCodeHasASentence covers them separately.
FRAME_CODES = {"turn-running", "closed", "gone", "engine-failed",
               "bundle-broken", "sheet-approved", "sheet-not-approved",
               "nothing-to-revise", "passage-gone"}


def frames(text: str) -> list:
    """The SSE payloads of a response body, in order."""
    return [json.loads(line[len("data: "):])
            for line in text.splitlines() if line.startswith("data: ")]


def kinds(text: str) -> list:
    return [frame["kind"] for frame in frames(text)]


def shown(sentence: str) -> str:
    """A pack sentence as the page actually carries it.

    Jinja escapes on the way out, so a sentence holding an apostrophe is not
    the string in the markup. Asserting the escaped form keeps the pack the
    source: picking an apostrophe free fragment by hand works until somebody
    rewrites the sentence, and then the test passes on the wrong screen.
    """
    return str(escape(sentence))


def spoken(text: str) -> str:
    return "".join(frame["text"] for frame in frames(text)
                   if frame["kind"] == "text")


class Bare:
    """Just enough of a Request for the turn generator, which only ever reaches
    for application state. Driving that generator directly is the only way to
    watch a turn from inside while it is still running."""

    def __init__(self, app):
        self.app = app


class WebCase(unittest.TestCase):
    environ = CONFIGURED
    scripts = ()
    lang = "en"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-interview-web-")
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
        self.transport = Replay(*self.scripts)
        self.app = create_app(self.root, lang=self.lang,
                              environ=dict(self.environ),
                              transport=self.transport)
        self.client = TestClient(self.app, base_url="http://127.0.0.1:8747")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def open_interview(self):
        reply = self.client.post("/interview", follow_redirects=False)
        return reply.headers["location"].rsplit("/", 1)[-1]

    def turn(self, interview_id, text=""):
        return self.client.post(f"/interview/{interview_id}/turn",
                                data={"text": text})


class TestTheHub(WebCase):
    def test_the_screen_names_the_model_that_would_answer(self):
        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn("claude-opus-5", page.text)
        self.assertIn("api.anthropic.com", page.text)

    def test_a_priced_model_shows_its_rate_before_anything_is_spent(self):
        page = self.client.get("/interview")
        self.assertIn("5.00", page.text)
        self.assertIn("25.00", page.text)

    def test_an_interview_can_be_started(self):
        self.assertIn('action="/interview"', self.client.get("/interview").text)

    def test_the_hub_gives_an_order_of_magnitude_before_the_first_turn(self):
        # Four to six turns of the block alone, at the input rate, counted at
        # the one ratio the engine states on the same screen. Low and high,
        # two decimals, and the sentence that says it is not a quote.
        page = self.client.get("/interview").text
        self.assertIn("roughly", page)
        found = re.search(r"roughly ([0-9]+\.[0-9]{2}) to ([0-9]+\.[0-9]{2}) USD",
                          page)
        self.assertIsNotNone(found, page)
        low, high = float(found.group(1)), float(found.group(2))
        self.assertLess(low, high)
        # Six turns over four, give or take the rounding of two figures that
        # are both under a dollar on this block.
        self.assertAlmostEqual(high, low * 1.5, delta=0.02)
        self.assertIn("4 characters per token", page)


class TestAnUnpricedModel(WebCase):
    environ = {"VERBATIM_PROVIDER": "openai", "VERBATIM_MODEL": "qwen2.5:14b",
               "VERBATIM_BASE_URL": "http://127.0.0.1:11434/v1"}

    def test_tokens_are_promised_and_no_price_is_invented(self):
        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn("qwen2.5:14b", page.text)
        self.assertIn("no price", page.text.lower())
        # And no estimate either: a range over a rate nobody has is the
        # invented figure, twice.
        self.assertNotIn("roughly", page.text)

    def test_a_local_endpoint_needs_no_key(self):
        # is_loopback, so key-missing is not a problem here and the screen
        # offers to start.
        self.assertIn('action="/interview"', self.client.get("/interview").text)


class TestNothingConfigured(WebCase):
    environ = {}

    def test_the_screen_says_what_to_do_instead_of_crashing(self):
        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn("key-missing", page.text)
        self.assertIn("ANTHROPIC_API_KEY", page.text)

    def test_no_interview_can_be_started_without_a_model(self):
        self.assertNotIn('action="/interview"', self.client.get("/interview").text)
        reply = self.client.post("/interview", follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(reply.headers["location"], "/interview")
        self.assertEqual(interview.listing(self.root), [])

    def test_the_other_screens_still_work(self):
        self.assertEqual(self.client.get("/").status_code, 200)


class TestASecretInTheInstance(WebCase):
    def test_the_interview_refuses_and_names_the_line_to_move(self):
        (self.root / ".env").write_text(
            "VERBATIM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-oops\n",
            encoding="utf-8")
        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn("ANTHROPIC_API_KEY", page.text)
        self.assertNotIn("sk-oops", page.text)
        self.assertNotIn('action="/interview"', page.text)


class TestStartingAndDiscarding(WebCase):
    def test_starting_creates_the_directory_and_lands_on_it(self):
        reply = self.client.post("/interview", follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        interview_id = reply.headers["location"].rsplit("/", 1)[-1]
        here = self.root / interview.DIRECTORY / interview_id
        self.assertTrue((here / interview.CONVERSATION).is_file())
        self.assertTrue((here / interview.TRANSCRIPT).is_file())

    def test_the_conversation_records_both_language_axes(self):
        conversation = interview.load(self.root, self.open_interview())
        self.assertEqual(conversation.interface_language, "en")
        self.assertEqual(conversation.output_language, "en")
        self.assertEqual(conversation.skill, interview.STEP_SKILL)

    def test_an_open_interview_is_listed_on_the_hub(self):
        interview_id = self.open_interview()
        self.assertIn(interview_id, self.client.get("/interview").text)

    def test_an_unknown_interview_is_404(self):
        self.assertEqual(self.client.get("/interview/2020-01-01-0000").status_code, 404)

    def test_an_id_that_is_not_a_timestamp_addresses_nothing(self):
        for bad in ("nope", "%2e%2e%2f%2e%2e%2fprofile.md", ".hidden"):
            self.assertEqual(self.client.get(f"/interview/{bad}").status_code,
                             404, bad)

    def test_discarding_removes_the_directory(self):
        interview_id = self.open_interview()
        reply = self.client.post(f"/interview/{interview_id}/discard",
                                 follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertFalse((self.root / interview.DIRECTORY / interview_id).exists())


class TestOneTurn(WebCase):
    scripts = (says("Which agency, and when?"),)

    def test_the_answer_streams_as_it_arrives(self):
        reply = self.turn(self.open_interview(), "Four months on agencies.")
        self.assertEqual(reply.status_code, 200)
        self.assertTrue(reply.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(spoken(reply.text), "Which agency, and when?")
        self.assertIn("stop", kinds(reply.text))

    def test_both_sides_land_on_disk(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.said(), "Four months on agencies.")
        self.assertEqual(conversation.engine_turns(), ["Which agency, and when?"])

    def test_the_transcript_is_readable_right_after(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        text = (self.root / interview.DIRECTORY / interview_id
                / interview.TRANSCRIPT).read_text(encoding="utf-8")
        self.assertLess(text.index("Four months on agencies."),
                        text.index("Which agency, and when?"))

    def test_the_running_total_is_reported_and_priced(self):
        reply = self.turn(self.open_interview(), "Four months on agencies.")
        usage = [f for f in frames(reply.text) if f["kind"] == "usage"][-1]
        self.assertEqual(usage["input_tokens"], 100)
        self.assertEqual(usage["output_tokens"], 10)
        self.assertAlmostEqual(usage["price"], (100 * 5.0 + 10 * 25.0) / 1e6)

    def test_the_total_is_kept_with_the_conversation(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.usage.input_tokens, 100)
        self.assertEqual(conversation.usage.output_tokens, 10)

    def test_the_system_block_is_rebuilt_from_the_bundle_every_turn(self):
        self.turn(self.open_interview(), "Four months on agencies.")
        system = self.transport.calls[0]["payload"]["system"]
        self.assertIn("One question at a time", str(system))

    def test_an_empty_first_answer_is_refused(self):
        reply = self.turn(self.open_interview(), "   ")
        self.assertEqual(reply.status_code, 422)


class TestAnUnpricedTurn(WebCase):
    # A model the price table has never verified. The provider stays the one
    # these recordings are written for: what is under test is the price, not
    # the parser.
    environ = {"ANTHROPIC_API_KEY": "sk-test", "VERBATIM_MODEL": "llama-3.3-70b"}
    scripts = (says("Which agency?"),)

    def test_tokens_are_reported_and_the_price_is_null_not_zero(self):
        reply = self.turn(self.open_interview(), "Four months on agencies.")
        usage = [f for f in frames(reply.text) if f["kind"] == "usage"][-1]
        self.assertGreater(usage["input_tokens"], 0)
        self.assertIsNone(usage["price"])


class TestToolTraffic(WebCase):
    scripts = (asks(("toolu_01", "read_instance", {"path": "voice.md"})),
               says("Which agency, and when?"))

    def test_the_call_and_its_result_are_shown_not_hidden(self):
        reply = self.turn(self.open_interview(), "Four months on agencies.")
        self.assertIn("tool_call", kinds(reply.text))
        self.assertIn("tool_result", kinds(reply.text))
        call = [f for f in frames(reply.text) if f["kind"] == "tool_call"][0]
        self.assertEqual(call["name"], "read_instance")
        self.assertEqual(call["arguments"], {"path": "voice.md"})

    def test_the_result_carries_what_the_tool_answered(self):
        reply = self.turn(self.open_interview(), "Four months on agencies.")
        result = [f for f in frames(reply.text) if f["kind"] == "tool_result"][0]
        self.assertFalse(result["is_error"])
        self.assertIn("Traits observed in the corpus", result["result"])

    def test_tool_traffic_stays_out_of_the_transcript(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        text = (self.root / interview.DIRECTORY / interview_id
                / interview.TRANSCRIPT).read_text(encoding="utf-8")
        self.assertNotIn("read_instance", text)
        self.assertEqual(interview.load(self.root, interview_id).said(),
                         "Four months on agencies.")


class TestTheDiskLeadsTheScreen(WebCase):
    """The decision of this slice, tested where it happens.

    Through a client this cannot be tested: by the time a test breaks out of
    the response body the whole loop has already run, so its assertions hold
    over a finished turn and prove nothing about an interrupted one. This
    drives the route's own generator instead and looks at the disk between two
    frames, which is exactly the moment a browser closes.
    """

    scripts = (asks(("toolu_01", "read_instance", {"path": "voice.md"}),
                    ("toolu_02", "read_instance", {"path": "nope.md"})),
               says("Which agency, and when?"))

    def stream(self, interview_id, text):
        from verbatim_app.routes import interview as screen
        request = Bare(self.app)
        return screen._run(request, screen._engine(request), interview_id, text,
                           screen.lock_for(self.app, interview_id))

    def blocks(self, conversation, kind):
        return [block for message in conversation.messages
                for block in message["content"] if block.get("type") == kind]

    def assert_conversation_is_sendable(self, conversation, where):
        asked = [block["id"] for block in self.blocks(conversation, "tool_use")]
        answered = [block["tool_use_id"]
                    for block in self.blocks(conversation, "tool_result")]
        self.assertEqual(asked, answered, f"dangling call after {where}")
        roles = [message["role"] for message in conversation.messages]
        for one, two in zip(roles, roles[1:]):
            self.assertNotEqual(one, two, f"two {one} in a row after {where}")
        for message in conversation.messages:
            self.assertTrue(message["content"], f"empty message after {where}")

    def test_the_disk_is_current_at_every_single_frame(self):
        interview_id = self.open_interview()
        frames = self.stream(interview_id, "Four months on agencies.")
        seen = 0
        for raw in frames:
            frame = json.loads(raw[len("data: "):])
            seen += 1
            # Read before the generator is ever resumed: this is the state a
            # browser closing right now would leave behind.
            conversation = interview.load(self.root, interview_id)
            self.assert_conversation_is_sendable(conversation, frame["kind"])
            if frame["kind"] == "tool_call":
                self.assertIn(frame["id"],
                              [b["id"] for b in self.blocks(conversation, "tool_use")],
                              "the call reached the screen before the disk")
                self.assertIn(frame["id"],
                              [b["tool_use_id"]
                               for b in self.blocks(conversation, "tool_result")])
            if frame["kind"] == "tool_result":
                answers = {b["tool_use_id"]: b["content"]
                           for b in self.blocks(conversation, "tool_result")}
                self.assertEqual(answers[frame["id"]], frame["result"],
                                 "the result reached the screen before the disk")
            if frame["kind"] == "stop":
                self.assertEqual(conversation.engine_turns()[-1],
                                 "Which agency, and when?")
        self.assertGreater(seen, 5)

    def test_stopping_between_two_frames_leaves_the_words_and_the_call(self):
        interview_id = self.open_interview()
        frames = self.stream(interview_id, "Four months on agencies.")
        for raw in frames:
            if '"tool_call"' in raw:
                break
        conversation = interview.load(self.root, interview_id)
        frames.close()

        self.assert_conversation_is_sendable(conversation, "the walk away")
        self.assertEqual(conversation.said(), "Four months on agencies.")
        self.assertEqual([b["id"] for b in self.blocks(conversation, "tool_use")],
                         ["toolu_01", "toolu_02"])

    def test_what_was_typed_reaches_disk_before_the_provider_is_called(self):
        interview_id = self.open_interview()
        seen = {}

        def watching(url, headers, payload):
            seen["said"] = interview.load(self.root, interview_id).said()
            return iter(says("Which agency?"))

        self.app.state.transport = watching
        self.turn(interview_id, "Four months on agencies.")
        self.assertEqual(seen["said"], "Four months on agencies.")


class TestTheAcceptedFrame(WebCase):
    """The one frame that says the words are on disk.

    The screen holds what was typed until it arrives, so a refusal decided
    before anything was written does not throw away somebody's answer, and a
    failure after it does not make them type it twice.
    """

    scripts = (says("Which agency?"),)

    def first_kinds(self, reply):
        return kinds(reply.text)[:1]

    def test_it_arrives_before_anything_else(self):
        reply = self.turn(self.open_interview(), "Four months.")
        self.assertEqual(self.first_kinds(reply), ["accepted"])

    def test_the_words_are_on_disk_before_it_is_sent(self):
        # The ordering is the whole point: a browser that commits and clears
        # its box on a frame emitted before the save would lose them from both
        # places the moment the save failed.
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        request = Bare(self.app)
        stream = screen._run(request, screen._engine(request), interview_id,
                             "Four months on agencies.",
                             screen.lock_for(self.app, interview_id))
        first = json.loads(next(stream)[len("data: "):])
        self.assertEqual(first["kind"], "accepted")
        self.assertEqual(interview.load(self.root, interview_id).said(),
                         "Four months on agencies.")
        stream.close()

    def test_it_arrives_before_the_provider_is_reached(self):
        seen = {}

        def watching(url, headers, payload):
            seen["called"] = True
            return iter(says("Which agency?"))

        self.app.state.transport = watching
        interview_id = self.open_interview()
        frames = []
        with self.client.stream("POST", f"/interview/{interview_id}/turn",
                                data={"text": "Four months."}) as reply:
            for line in reply.iter_lines():
                if line.startswith("data: "):
                    frames.append(json.loads(line[len("data: "):]))
                    break
        self.assertEqual(frames[0]["kind"], "accepted")

    def test_a_refusal_before_it_means_nothing_was_written(self):
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        held = screen.lock_for(self.app, interview_id)
        request = Bare(self.app)
        frames = screen._run(request, screen._engine(request), interview_id,
                             "Four months.", held)
        self.assertTrue(held.acquire(blocking=False))
        try:
            sent = [json.loads(raw[len("data: "):]) for raw in frames]
        finally:
            held.release()
        self.assertNotIn("accepted", [frame["kind"] for frame in sent])
        self.assertEqual(interview.load(self.root, interview_id).said(), "")

    def test_a_failure_after_it_means_the_words_are_kept(self):
        def broken(url, headers, payload):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

        self.app.state.transport = broken
        interview_id = self.open_interview()
        reply = self.turn(interview_id, "Four months on agencies.")
        sent = kinds(reply.text)
        self.assertEqual(sent[0], "accepted")
        self.assertIn("error", sent)
        self.assertEqual(interview.load(self.root, interview_id).said(),
                         "Four months on agencies.")


class TestATurnThatAnsweredNothing(WebCase):
    """A stream that stops without producing a single block.

    An OpenAI compatible runtime answering `finish_reason: stop` with empty
    content is the realistic case, and it leaves the person's own message last:
    the model still owes a reply, and the screen has to say so rather than fall
    silent.
    """

    #: end_turn, and not one content block with it.
    scripts = ([
        'data: {"type":"message_start","message":{"usage":'
        '{"input_tokens":100,"output_tokens":1}}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
        '"usage":{"output_tokens":1}}',
    ],)

    def test_the_stop_frame_says_the_model_still_owes_a_reply(self):
        interview_id = self.open_interview()
        reply = self.turn(interview_id, "Four months.")
        stop = [f for f in frames(reply.text) if f["kind"] == "stop"][0]
        self.assertTrue(stop["owing"])

    def test_the_screen_offers_to_ask_again_on_reload(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="resume"', page.text)
        self.assertNotIn('id="resume" hidden', page.text)

    def test_a_turn_that_did_answer_says_the_opposite(self):
        self.app.state.transport = Replay(says("Which agency?"))
        reply = self.turn(self.open_interview(), "Four months.")
        stop = [f for f in frames(reply.text) if f["kind"] == "stop"][0]
        self.assertFalse(stop["owing"])


class TestTheCeiling(WebCase):
    scripts = tuple(asks(("toolu_%02d" % n, "read_instance", {"path": "voice.md"}))
                    for n in range(12))

    def test_the_ceiling_frame_says_the_model_still_owes_a_reply(self):
        reply = self.turn(self.open_interview(), "Four months.")
        ceiling = [f for f in frames(reply.text) if f["kind"] == "ceiling"]
        self.assertEqual(len(ceiling), 1)
        self.assertTrue(ceiling[0]["owing"])
        self.assertEqual(ceiling[0]["turns"], 12)


class TestATurnThatFailed(WebCase):
    """The case this screen exists for. A turn that never got its answer, then
    somebody retypes: the conversation has to stay one a provider accepts."""

    def broken(self, url, headers, payload):
        raise RuntimeError("connection refused")
        yield  # pragma: no cover

    def roles(self, interview_id):
        return [message["role"]
                for message in interview.load(self.root, interview_id).messages]

    def test_retyping_after_a_failed_turn_leaves_a_sendable_conversation(self):
        self.app.state.transport = self.broken
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        self.assertEqual(self.roles(interview_id), ["user"])

        self.app.state.transport = Replay(says("Which agency?"))
        self.turn(interview_id, "Four months, actually four and a half.")
        self.assertEqual(self.roles(interview_id), ["user", "assistant"])
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(
            conversation.said(),
            "Four months on agencies.\n\nFour months, actually four and a half.")

    def test_the_provider_never_receives_two_user_messages_in_a_row(self):
        self.app.state.transport = self.broken
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        watcher = Replay(says("Which agency?"))
        self.app.state.transport = watcher
        self.turn(interview_id, "And a half.")
        sent = [message["role"]
                for message in watcher.calls[0]["payload"]["messages"]]
        for one, two in zip(sent, sent[1:]):
            self.assertNotEqual(one, two, sent)

    def test_the_screen_offers_to_ask_again(self):
        # The control is always in the page so the script can show it when a
        # turn fails, so what is under test is whether it is offered.
        interview_id = self.open_interview()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="resume" hidden', page.text)

        self.app.state.transport = self.broken
        self.turn(interview_id, "Four months.")
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="resume"', page.text)
        self.assertNotIn('id="resume" hidden', page.text)

    def test_asking_again_sends_no_new_words(self):
        self.app.state.transport = self.broken
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        self.app.state.transport = Replay(says("Which agency?"))
        reply = self.turn(interview_id, "")
        self.assertEqual(reply.status_code, 200)
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.said(), "Four months.")
        self.assertEqual(conversation.engine_turns(), ["Which agency?"])


class TestAnAnswerAfterAnInterruptedToolCall(WebCase):
    scripts = (asks(("toolu_01", "read_instance", {"path": "voice.md"})),
               says("Which agency?"))

    def test_the_words_are_kept_and_the_tool_output_is_not(self):
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        request = Bare(self.app)
        frames = screen._run(request, screen._engine(request), interview_id,
                             "Four months.", screen.lock_for(self.app, interview_id))
        for raw in frames:
            if '"tool_result"' in raw:
                break
        frames.close()

        self.turn(interview_id, "A Lyon agency, in March.")
        conversation = interview.load(self.root, interview_id)
        roles = [message["role"] for message in conversation.messages]
        for one, two in zip(roles, roles[1:]):
            self.assertNotEqual(one, two, roles)
        self.assertEqual(conversation.said(),
                         "Four months.\n\nA Lyon agency, in March.")
        self.assertNotIn("Traits observed", conversation.said())


class RefusedDirectoryCase(WebCase):
    """Something that is not a directory where the directory belongs.

    Refusing it is right; refusing it with a traceback is not, and every screen
    in this section goes through that path.
    """

    #: Set on the subclasses; the base class runs nothing of its own.
    block = None

    def setUp(self):
        if self.block is None:
            self.skipTest("base case")
        super().setUp()
        self.block()

    def test_the_hub_is_a_screen_and_not_a_five_hundred(self):
        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn("is not a directory, or cannot be created", page.text)
        self.assertNotIn('action="/interview"', page.text)

    def test_starting_one_lands_back_on_that_screen(self):
        reply = self.client.post("/interview", follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(reply.headers["location"], "/interview")

    def test_the_other_screens_are_untouched(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/posts").status_code, 200)


class TestALinkedInterviewsDirectory(RefusedDirectoryCase):
    def block(self):
        outside = Path(self.tmp) / "elsewhere"
        outside.mkdir()
        (self.root / interview.DIRECTORY).symlink_to(outside)


class TestAFileWhereTheDirectoryBelongs(RefusedDirectoryCase):
    def block(self):
        (self.root / interview.DIRECTORY).write_text("not a directory",
                                                     encoding="utf-8")


class TestAnInstanceNobodyCanWriteTo(WebCase):
    scripts = (says("Which agency?"),)

    def test_the_hub_says_so_instead_of_offering_a_button_that_fails(self):
        import os
        # The state that matters: the directory exists, so its own mkdir
        # succeeds and only the interview's own can fail.
        self.open_interview()
        home = self.root / interview.DIRECTORY
        os.chmod(home, 0o555)
        try:
            reply = self.client.post("/interview", follow_redirects=False)
            self.assertEqual(reply.status_code, 303)
            self.assertEqual(self.client.get("/interview").status_code, 200)
        finally:
            os.chmod(home, 0o755)


class TestAnEnvNobodyCanRead(WebCase):
    def test_another_encoding_is_a_screen(self):
        (self.root / ".env").write_bytes(
            "VERBATIM_MODEL=mistral-modèle\n".encode("latin-1"))
        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn("cannot be read", page.text)
        self.assertNotIn('action="/interview"', page.text)
        self.assertEqual(
            self.client.post("/interview", follow_redirects=False).status_code,
            303)

    def test_a_mode_that_came_across_wrong_is_a_screen_too(self):
        import os
        path = self.root / ".env"
        path.write_text("VERBATIM_MODEL=x\n", encoding="utf-8")
        os.chmod(path, 0o000)
        try:
            self.assertEqual(self.client.get("/interview").status_code, 200)
        finally:
            os.chmod(path, 0o644)

    def test_the_other_screens_are_untouched(self):
        (self.root / ".env").write_bytes(b"VERBATIM_MODEL=\xff\n")
        for path in ("/", "/profile", "/posts"):
            self.assertEqual(self.client.get(path).status_code, 200, path)


class TestAWronglyTypedBlockOnTheScreens(WebCase):
    def test_one_bad_block_does_not_take_the_hub_down(self):
        good = self.open_interview()
        bad = self.open_interview()
        path = self.root / interview.DIRECTORY / bad / interview.CONVERSATION
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["messages"] = [{"role": "user",
                            "content": [{"type": "text", "text": None}]}]
        path.write_text(json.dumps(raw), encoding="utf-8")

        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'href="/interview/{good}"', page.text)
        self.assertIn(f'action="/interview/{bad}/discard"', page.text)
        self.assertEqual(self.client.get(f"/interview/{bad}").status_code, 404)

    def test_a_language_code_is_data_and_not_a_pattern(self):
        profile = (self.root / "profile.md").read_text(encoding="utf-8")
        (self.root / "profile.md").write_text(
            profile.replace("interface_language: en", "interface_language: \\1"),
            encoding="utf-8")
        client = TestClient(create_app(self.root, environ=dict(self.environ),
                                       transport=self.transport),
                            base_url="http://127.0.0.1:8747")
        self.assertEqual(client.get("/interview").status_code, 200)


class TestAnInterviewNobodyCanRead(WebCase):
    """A file half written by a sync client, a mode that came across wrong.

    Refusing that one interview is right. Taking down the screen that lists
    them is not, because that screen is where the only remaining action lives.
    """

    def spoil(self, how):
        interview_id = self.open_interview()
        path = (self.root / interview.DIRECTORY / interview_id
                / interview.CONVERSATION)
        how(path)
        return interview_id

    def test_bytes_that_are_not_text_do_not_take_the_hub_down(self):
        interview_id = self.spoil(
            lambda path: path.write_bytes(b'{"version": 1, \xff\xfe}'))
        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn(interview_id, page.text)

    def test_a_file_that_cannot_be_opened_does_not_either(self):
        import os
        interview_id = self.spoil(lambda path: os.chmod(path, 0o000))
        try:
            page = self.client.get("/interview")
            self.assertEqual(page.status_code, 200)
            self.assertIn(interview_id, page.text)
        finally:
            os.chmod(self.root / interview.DIRECTORY / interview_id
                     / interview.CONVERSATION, 0o644)

    def test_a_directory_that_cannot_be_listed_is_a_screen(self):
        import os
        self.open_interview()
        home = self.root / interview.DIRECTORY
        os.chmod(home, 0o000)
        try:
            page = self.client.get("/interview")
            self.assertEqual(page.status_code, 200)
            self.assertIn("is not a directory, or cannot be created", page.text)
        finally:
            os.chmod(home, 0o755)

    def test_the_hub_is_where_it_can_be_discarded(self):
        # The interview screen reads the same file and 404s on it, so the hub
        # is the only place the action can live.
        interview_id = self.spoil(
            lambda path: path.write_text("{ not json", encoding="utf-8"))
        page = self.client.get("/interview")
        self.assertIn(f'action="/interview/{interview_id}/discard"', page.text)
        self.assertNotIn(f'href="/interview/{interview_id}"', page.text)

        reply = self.client.post(f"/interview/{interview_id}/discard",
                                 follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(interview.listing(self.root), [])

    def test_it_is_not_labelled_with_a_state_nobody_read(self):
        self.spoil(lambda path: path.write_text("{ not json", encoding="utf-8"))
        page = self.client.get("/interview")
        self.assertNotIn("state-open", page.text)

    def test_one_bad_interview_does_not_hide_the_good_ones(self):
        good = self.open_interview()
        self.spoil(lambda path: path.write_text("{ not json", encoding="utf-8"))
        page = self.client.get("/interview")
        self.assertIn(good, page.text)
        self.assertIn(f'href="/interview/{good}"', page.text)


class TestBothLanguageAxes(WebCase):
    """The project's named trap, pinned at the seam where it can happen.

    The example instance is interviewed and published in English, so a test
    against it cannot tell the two axes apart. This one interviews in French
    and publishes in English, which is the case the loader was fixed for.
    """

    scripts = (says("Quelle agence ?"), says("Et ensuite ?"))

    def setUp(self):
        super().setUp()
        profile = (self.root / "profile.md").read_text(encoding="utf-8")
        (self.root / "profile.md").write_text(
            profile.replace("interface_language: en", "interface_language: fr")
                   .replace("output_language_default: en",
                            "output_language_default: en"),
            encoding="utf-8")

    def test_each_axis_is_read_from_its_own_key(self):
        conversation = interview.load(self.root, self.open_interview())
        self.assertEqual(conversation.interface_language, "fr")
        self.assertEqual(conversation.output_language, "en")

    def test_the_interview_language_decides_the_packs_of_this_step(self):
        self.turn(self.open_interview(), "Quatre mois.")
        system = str(self.transport.calls[0]["payload"]["system"])
        self.assertIn("===== locales/fr/interview.md", system)
        self.assertNotIn("===== locales/en/interview.md", system)

    def test_a_profile_edited_mid_interview_does_not_switch_languages(self):
        # references/instance.md promises it: the axes are kept per interview.
        interview_id = self.open_interview()
        self.turn(interview_id, "Quatre mois.")
        profile = (self.root / "profile.md").read_text(encoding="utf-8")
        (self.root / "profile.md").write_text(
            profile.replace("interface_language: fr", "interface_language: en"),
            encoding="utf-8")

        self.turn(interview_id, "Une agence lyonnaise.")
        system = str(self.transport.calls[1]["payload"]["system"])
        self.assertIn("===== locales/fr/interview.md", system)
        self.assertNotIn("===== locales/en/interview.md", system)

    def test_the_publication_language_reaches_the_block_too(self):
        # A section whose citations are ambiguous resolves to both packs when
        # the axes differ. Passing one language would carry only one.
        from verbatim_app.routes import interview as screen
        conversation = interview.load(self.root, self.open_interview())
        conversation.sections = ("Hard rules",)
        block = screen._block(Bare(self.app), conversation)
        resolved = [citation.resolved for citation in block.citations]
        self.assertIn("locales/fr/market.md", resolved)
        self.assertIn("locales/en/market.md", resolved)


class TestWhatATurnCosts(WebCase):
    """A price is accumulated turn by turn at the rate that ran that turn, and
    one unpriced turn takes the whole figure away rather than dropping itself
    quietly out of it."""

    scripts = (says("Which agency?"), says("And then?"))

    def meter(self, interview_id):
        page = self.client.get(f"/interview/{interview_id}").text
        start = page.index('id="meter"')
        return page[start:page.index("</p>", start)]

    def test_a_fresh_interview_shows_no_figure_at_all(self):
        # Zero dollars is true of every model before the first turn, priced or
        # not, and it reads as a price for one that has none.
        self.assertNotIn("USD", self.meter(self.open_interview()))

    def test_the_figure_appears_once_something_is_spent(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        self.assertIn("USD", self.meter(interview_id))

    def test_an_unpriced_model_shows_tokens_and_no_figure(self):
        self.app.state.environ["VERBATIM_MODEL"] = "llama-3.3-70b"
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        meter = self.meter(interview_id)
        self.assertIn("100 tokens in", meter)
        self.assertNotIn("USD", meter)

    def test_the_running_total_adds_up(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        self.turn(interview_id, "A Lyon agency.")
        one_turn = (100 * 5.0 + 10 * 25.0) / 1e6
        self.assertAlmostEqual(interview.load(self.root, interview_id).spent,
                               2 * one_turn)

    def test_changing_the_model_does_not_re_price_the_earlier_turns(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        after_one = interview.load(self.root, interview_id).spent

        self.app.state.environ["VERBATIM_MODEL"] = "claude-haiku-4-5"
        self.turn(interview_id, "A Lyon agency.")
        conversation = interview.load(self.root, interview_id)
        cheaper = (100 * 1.0 + 10 * 5.0) / 1e6
        self.assertAlmostEqual(conversation.spent, after_one + cheaper)
        self.assertEqual(conversation.model, "claude-haiku-4-5")

    def test_one_unpriced_turn_takes_the_whole_figure_away(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        self.assertIsNotNone(interview.load(self.root, interview_id).spent)

        self.app.state.environ["VERBATIM_MODEL"] = "llama-3.3-70b"
        reply = self.turn(interview_id, "A Lyon agency.")
        self.assertIsNone(interview.load(self.root, interview_id).spent)
        usage = [f for f in frames(reply.text) if f["kind"] == "usage"][-1]
        self.assertIsNone(usage["price"])
        self.assertGreater(usage["input_tokens"], 0)

    def test_the_figure_stays_gone_once_it_is_gone(self):
        interview_id = self.open_interview()
        self.app.state.environ["VERBATIM_MODEL"] = "llama-3.3-70b"
        self.turn(interview_id, "Four months.")
        self.app.state.environ["VERBATIM_MODEL"] = "claude-opus-5"
        self.turn(interview_id, "A Lyon agency.")
        self.assertIsNone(interview.load(self.root, interview_id).spent)


class TestATurnAbandonedMidAnswer(WebCase):
    """The case this whole slice is built around, counted properly.

    The loop folds a turn's figures into `Agent.usage` only when that turn
    ends, so a turn abandoned while its answer streams would contribute
    nothing: the provider bills those tokens all the same, and a total that
    quietly drops a turn is exactly what `spent` refuses to be.
    """

    scripts = (says("Which agency, and when?"), says("And then?"))

    def walk_away(self, interview_id, text):
        from verbatim_app.routes import interview as screen
        request = Bare(self.app)
        stream = screen._run(request, screen._engine(request), interview_id,
                             text, screen.lock_for(self.app, interview_id))
        shown = None
        for raw in stream:
            frame = json.loads(raw[len("data: "):])
            if frame["kind"] == "usage":
                shown = frame
                break
        stream.close()
        return shown

    def test_the_tokens_the_screen_was_shown_are_the_tokens_on_disk(self):
        interview_id = self.open_interview()
        shown = self.walk_away(interview_id, "Four months on agencies.")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.usage.input_tokens, shown["input_tokens"])
        self.assertEqual(conversation.usage.output_tokens, shown["output_tokens"])
        self.assertGreater(conversation.usage.input_tokens, 0)

    def test_what_it_cost_is_on_disk_too(self):
        interview_id = self.open_interview()
        shown = self.walk_away(interview_id, "Four months on agencies.")
        self.assertAlmostEqual(interview.load(self.root, interview_id).spent,
                               shown["price"])
        self.assertGreater(shown["price"], 0)

    def test_the_next_turn_adds_to_it_rather_than_replacing_it(self):
        interview_id = self.open_interview()
        self.walk_away(interview_id, "Four months on agencies.")
        abandoned = interview.load(self.root, interview_id).usage
        self.turn(interview_id, "")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.usage.input_tokens,
                         abandoned.input_tokens + 100)
        self.assertEqual(conversation.usage.output_tokens,
                         abandoned.output_tokens + 10)

    def test_a_complete_turn_counts_each_figure_exactly_once(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.usage.input_tokens, 100)
        self.assertEqual(conversation.usage.output_tokens, 10)


class TestWhatAFailureIsAllowedToSay(WebCase):
    def test_only_the_exception_type_travels_to_the_screen(self):
        # An arbitrary exception message is arbitrary text, and this is the
        # same boundary tools.py spends a whole redaction pass on.
        def leaking(url, headers, payload):
            raise RuntimeError("connect to https://api.example/v1 with sk-live-secret")
            yield  # pragma: no cover

        self.app.state.transport = leaking
        reply = self.turn(self.open_interview(), "Four months.")
        failure = [f for f in frames(reply.text) if f["kind"] == "error"][0]
        self.assertEqual(failure["code"], "engine-failed")
        self.assertEqual(failure["technical"], "RuntimeError")
        self.assertNotIn("sk-live-secret", reply.text)

    def test_a_provider_echoing_a_key_back_does_not_put_it_on_the_screen(self):
        # A gateway that quotes the Authorization header into a debug body is
        # the same accident as a subprocess printing its own environment, and
        # it gets the same guard.
        from verbatim_app.agent import AgentError
        self.app.state.environ["ANTHROPIC_API_KEY"] = "sk-live-abcdefghij"

        def echoing(url, headers, payload):
            raise AgentError("400: bad header Authorization: sk-live-abcdefghij")
            yield  # pragma: no cover

        self.app.state.transport = echoing
        reply = self.turn(self.open_interview(), "Four months.")
        self.assertNotIn("sk-live-abcdefghij", reply.text)
        failure = [f for f in frames(reply.text) if f["kind"] == "error"][0]
        self.assertIn("ANTHROPIC_API_KEY", failure["technical"])
        self.assertIn("400", failure["technical"])

    def test_a_provider_error_raised_inside_the_stream_keeps_its_words(self):
        # The wire raises ProviderError on the stream's own error event, which
        # is where a rate limit or a credit balance arrives. Folding it into
        # the generic handler would throw away the one sentence that says what
        # to do next.
        from verbatim_app.providers import ProviderError

        def refusing(url, headers, payload):
            raise ProviderError("endpoint refused: rate limit, retry in 30s")
            yield  # pragma: no cover

        self.app.state.transport = refusing
        reply = self.turn(self.open_interview(), "Four months.")
        failure = [f for f in frames(reply.text) if f["kind"] == "error"][0]
        self.assertNotIn("code", failure)
        self.assertIn("rate limit", failure["technical"])

    def test_a_provider_refusing_keeps_its_own_words(self):
        from verbatim_app.agent import AgentError

        def refusing(url, headers, payload):
            raise AgentError("https://api.example answered 429: slow down")
            yield  # pragma: no cover

        self.app.state.transport = refusing
        reply = self.turn(self.open_interview(), "Four months.")
        failure = [f for f in frames(reply.text) if f["kind"] == "error"][0]
        self.assertNotIn("code", failure)
        self.assertIn("429", failure["technical"])


class TestATurnWithoutAModel(WebCase):
    environ = {}

    def test_it_is_refused_before_anything_is_written(self):
        # The interview is started with a model, then the key goes away.
        self.app.state.environ.update(CONFIGURED)
        interview_id = self.open_interview()
        self.app.state.environ.clear()

        reply = self.turn(interview_id, "Four months.")
        self.assertEqual(reply.status_code, 503)
        self.assertEqual(reply.json()["detail"], "not-configured")
        self.assertEqual(interview.load(self.root, interview_id).said(), "")


class TestARefusedTool(WebCase):
    scripts = (asks(("toolu_01", "read_instance", {"path": ".env"})),
               says("Right, not that one."))

    def test_the_frame_says_the_tool_refused(self):
        reply = self.turn(self.open_interview(), "Four months.")
        result = [f for f in frames(reply.text) if f["kind"] == "tool_result"][0]
        self.assertTrue(result["is_error"])
        self.assertIn("engine configuration", result["result"])


class TestTheTurnLock(WebCase):
    scripts = (says("Which agency?"),)

    def test_a_body_that_is_never_read_does_not_walk_off_with_the_lock(self):
        # A generator closed before it was ever advanced never runs its
        # finally, so a lock taken in the handler would be held for the life
        # of the process and that interview would answer 409 forever.
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        request = Bare(self.app)
        frames = screen._run(request, screen._engine(request), interview_id,
                             "Four months.", screen.lock_for(self.app, interview_id))
        frames.close()
        self.assertFalse(screen.lock_for(self.app, interview_id).locked())
        self.assertEqual(self.turn(interview_id, "Four months.").status_code, 200)

    def test_a_second_turn_while_one_runs_is_refused(self):
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        held = screen.lock_for(self.app, interview_id)
        self.assertTrue(held.acquire(blocking=False))
        try:
            reply = self.turn(interview_id, "Four months.")
            self.assertEqual(reply.status_code, 409)
            self.assertEqual(reply.json()["detail"], "turn-running")
            self.assertEqual(interview.load(self.root, interview_id).said(), "")
        finally:
            held.release()

    def test_the_loser_of_the_race_writes_nothing(self):
        # The handler's peek is not the decision, so the generator has to
        # refuse on its own without touching the conversation.
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        held = screen.lock_for(self.app, interview_id)
        request = Bare(self.app)
        frames = screen._run(request, screen._engine(request), interview_id,
                             "Four months.", held)
        self.assertTrue(held.acquire(blocking=False))
        try:
            sent = [json.loads(raw[len("data: "):]) for raw in frames]
        finally:
            held.release()
        self.assertEqual([f["kind"] for f in sent], ["error"])
        self.assertEqual(sent[0]["code"], "turn-running")
        self.assertEqual(interview.load(self.root, interview_id).said(), "")

    def test_discarding_forgets_the_lock(self):
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        screen.lock_for(self.app, interview_id)
        self.client.post(f"/interview/{interview_id}/discard")
        self.assertNotIn(interview_id, self.app.state.turn_locks)


class TestDiscardingMidTurn(WebCase):
    scripts = (says("Which agency?"),)

    def test_the_response_ends_on_a_frame_rather_than_a_traceback(self):
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        request = Bare(self.app)
        frames = screen._run(request, screen._engine(request), interview_id,
                             "Four months.", screen.lock_for(self.app, interview_id))
        sent = []
        for raw in frames:
            sent.append(json.loads(raw[len("data: "):]))
            if len(sent) == 1:
                shutil.rmtree(self.root / interview.DIRECTORY / interview_id)
        self.assertIn("error", [frame["kind"] for frame in sent])
        self.assertFalse(screen.lock_for(self.app, interview_id).locked())


class TestAClosedInterview(WebCase):
    scripts = (says("Which agency?"),)

    def closed(self):
        interview_id = self.open_interview()
        interview.close(self.root, interview_id, post="2026-08-28-agency.md")
        return interview_id

    def test_a_closed_interview_refuses_a_turn(self):
        interview_id = self.closed()
        reply = self.turn(interview_id, "je continue quand meme")
        self.assertEqual(reply.status_code, 409)
        self.assertEqual(reply.json()["detail"], "closed")

    def test_nothing_is_spent_and_nothing_is_written(self):
        interview_id = self.closed()
        self.turn(interview_id, "je continue quand meme")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.said(), "")
        self.assertEqual(conversation.state, interview.CLOSED)
        self.assertEqual(self.transport.calls, [])

    def test_the_generator_refuses_too_when_it_closed_under_the_race(self):
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        request = Bare(self.app)
        frames = screen._run(request, screen._engine(request), interview_id,
                             "Four months.", screen.lock_for(self.app, interview_id))
        interview.close(self.root, interview_id, post="2026-08-28-agency.md")
        sent = [json.loads(raw[len("data: "):]) for raw in frames]
        self.assertEqual([f["kind"] for f in sent], ["error"])
        self.assertEqual(sent[0]["code"], "closed")
        self.assertEqual(self.transport.calls, [])

    def test_the_screen_offers_no_form_and_says_what_it_became(self):
        page = self.client.get(f"/interview/{self.closed()}")
        self.assertNotIn('id="say"', page.text)
        self.assertIn("2026-08-28-agency.md", page.text)


class TestATruncatedStream(WebCase):
    #: The stream ends mid answer: no message_delta, so no reason at all.
    scripts = (says("Which agency")[:-1],)

    def test_a_stream_that_never_said_why_it_stopped_is_truncated(self):
        reply = self.turn(self.open_interview(), "Four months.")
        stop = [f for f in frames(reply.text) if f["kind"] == "stop"][0]
        self.assertEqual(stop["stop"], "truncated")


class TestAProviderRefusing(WebCase):
    def test_the_failure_reaches_the_screen_as_a_frame(self):
        def broken(url, headers, payload):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover
        self.app.state.transport = broken
        reply = self.turn(self.open_interview(), "Four months.")
        self.assertEqual(reply.status_code, 200)  # headers already went out
        self.assertIn("error", kinds(reply.text))

    def test_what_the_person_typed_is_not_lost(self):
        def broken(url, headers, payload):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover
        self.app.state.transport = broken
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        self.assertEqual(interview.load(self.root, interview_id).said(),
                         "Four months on agencies.")


class TestResuming(WebCase):
    scripts = (says("Which agency?"), says("And what did they say?"))

    def test_a_second_turn_continues_the_same_conversation(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        self.turn(interview_id, "A Lyon agency, in March.")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.person_turns(),
                         ["Four months.", "A Lyon agency, in March."])
        self.assertEqual(len(conversation.engine_turns()), 2)

    def test_the_total_adds_up_across_turns(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        self.turn(interview_id, "A Lyon agency, in March.")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.usage.input_tokens, 200)
        self.assertEqual(conversation.usage.output_tokens, 20)

    def test_the_whole_conversation_goes_back_to_the_provider(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        self.turn(interview_id, "A Lyon agency, in March.")
        self.assertEqual(len(self.transport.calls[1]["payload"]["messages"]), 3)

    def test_the_idea_bank_is_there_to_seed_an_answer(self):
        # The three ways in, without the app inventing a single word: the
        # angles are the person's own lines, out of ideas.md.
        page = self.client.get(f"/interview/{self.open_interview()}")
        self.assertIn("VISIBILITY", page.text)

    def test_the_screen_shows_the_conversation_so_far(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months.")
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn("Four months.", page.text)
        self.assertIn("Which agency?", page.text)


class TestOneTurnAtATime(WebCase):
    scripts = (says("Which agency?"),)

    def test_a_second_turn_while_one_runs_is_refused(self):
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        held = screen.lock_for(self.app, interview_id)
        self.assertTrue(held.acquire(blocking=False))
        try:
            reply = self.turn(interview_id, "Four months.")
            self.assertEqual(reply.status_code, 409)
        finally:
            held.release()


class TestTheGuards(WebCase):
    scripts = (says("Which agency?"),)

    def test_the_turn_is_not_something_a_get_can_do(self):
        # The whole reason this is a POST. A no-cors GET from a hostile page
        # carries no Origin, so a GET that spent the person's tokens would be
        # reachable from any tab they have open.
        interview_id = self.open_interview()
        reply = self.client.get(f"/interview/{interview_id}/turn")
        self.assertEqual(reply.status_code, 405)

    def test_a_cross_origin_post_is_refused(self):
        interview_id = self.open_interview()
        reply = self.client.post(f"/interview/{interview_id}/turn",
                                 data={"text": "hello"},
                                 headers={"origin": "https://evil.example"})
        self.assertEqual(reply.status_code, 403)

    def test_another_local_server_is_not_this_app(self):
        # A hostname comparison would accept these: same host, different
        # program. A form post from one is same-site and a navigation, so the
        # Sec-Fetch exemption does not catch it either. Only the port does.
        interview_id = self.open_interview()
        for origin in ("http://localhost:3000", "http://127.0.0.1:9999",
                       "https://127.0.0.1:8747"):
            reply = self.client.post(
                f"/interview/{interview_id}/turn", data={"text": "hello"},
                headers={"origin": origin, "sec-fetch-site": "same-site",
                         "sec-fetch-mode": "navigate"})
            self.assertEqual(reply.status_code, 403, origin)
        self.assertEqual(self.transport.calls, [])

    def test_another_local_server_cannot_delete_an_interview(self):
        interview_id = self.open_interview()
        reply = self.client.post(
            f"/interview/{interview_id}/discard",
            headers={"origin": "http://localhost:3000",
                     "sec-fetch-site": "same-site",
                     "sec-fetch-mode": "navigate"})
        self.assertEqual(reply.status_code, 403)
        self.assertTrue((self.root / interview.DIRECTORY / interview_id).is_dir())

    def test_this_app_own_origin_passes(self):
        interview_id = self.open_interview()
        reply = self.client.post(f"/interview/{interview_id}/turn",
                                 data={"text": "Four months."},
                                 headers={"origin": "http://127.0.0.1:8747"})
        self.assertEqual(reply.status_code, 200)

    def test_a_same_origin_get_without_an_origin_header_still_works(self):
        # The check that had to be made rather than assumed: browsers omit
        # Origin on same-origin GETs, so a guard requiring it would have
        # refused the app's own screens.
        page = self.client.get("/interview")
        self.assertNotIn("origin", {k.lower() for k in page.request.headers})
        self.assertEqual(page.status_code, 200)

    def test_a_cross_site_fetch_is_refused_even_without_an_origin(self):
        reply = self.client.get("/interview",
                                headers={"sec-fetch-site": "cross-site",
                                         "sec-fetch-mode": "no-cors"})
        self.assertEqual(reply.status_code, 403)

    def test_following_a_link_from_another_site_is_somebody_arriving(self):
        reply = self.client.get("/interview",
                                headers={"sec-fetch-site": "cross-site",
                                         "sec-fetch-mode": "navigate"})
        self.assertEqual(reply.status_code, 200)


class TestNothingEnglishReachesAFrenchScreen(WebCase):
    lang = "fr"
    scripts = (says("Quelle agence ?"),)

    def test_an_interview_that_is_not_there_says_so_in_the_pack(self):
        reply = self.client.post("/interview/2020-01-01-0000/turn",
                                 data={"text": "hello"})
        self.assertEqual(reply.status_code, 404)
        self.assertEqual(reply.json()["detail"], "gone")
        self.assertNotIn("Not Found", reply.text)

    def test_an_interview_discarded_under_its_own_turn_answers_with_a_code(self):
        from verbatim_app.routes import interview as screen
        interview_id = self.open_interview()
        request = Bare(self.app)
        frames = screen._run(request, screen._engine(request), interview_id,
                             "Quatre mois.", screen.lock_for(self.app, interview_id))
        sent = []
        for raw in frames:
            sent.append(json.loads(raw[len("data: "):]))
            if len(sent) == 1:
                shutil.rmtree(self.root / interview.DIRECTORY / interview_id)
        failures = [frame for frame in sent if frame["kind"] == "error"]
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].get("code"), "gone")
        # no English sentence and no absolute path travelling to a screen
        self.assertNotIn("detail", failures[0])

    def test_a_refused_instance_env_is_explained_by_the_pack(self):
        (self.root / ".env").write_text(
            "ANTHROPIC_API_KEY=sk-oops\n", encoding="utf-8")
        page = self.client.get("/interview")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Cette instance porte des identifiants", page.text)
        self.assertIn("ANTHROPIC_API_KEY", page.text)
        self.assertNotIn("sk-oops", page.text)
        self.assertNotIn("An instance is a directory people copy", page.text)

    def test_a_bad_measurement_count_is_a_code_not_a_sentence(self):
        reply = self.client.post("/posts/2026-08-25-agency-segment.md/measure",
                                 data={"inbound_dms": "abc"})
        self.assertEqual(reply.status_code, 422)
        self.assertEqual(reply.json()["detail"], "not-a-count")


class TestDiscardingSomethingAlreadyGone(WebCase):
    def test_it_lands_on_the_hub_rather_than_on_raw_json(self):
        reply = self.client.post("/interview/2020-01-01-0000/discard",
                                 follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(reply.headers["location"], "/interview")


class TestEveryCodeHasASentence(WebCase):
    """A code the pack does not name renders as the code. Every code this
    engine can produce is enumerated here, so adding one without a sentence
    fails at the seam rather than on somebody's screen."""

    CODES = ("turn-running", "closed", "not-configured", "nothing-to-send",
             "gone", "engine-failed", "bundle-broken", "sheet-approved",
             "sheet-not-approved", "nothing-to-revise", "passage-gone",
             "unknown")
    REFUSALS = ("secrets-in-instance", "credential-in-endpoint",
                "endpoint-in-clear", "endpoint-untrusted", "engine-refused",
                "interviews-not-a-directory", "env-unreadable")

    def test_the_browser_gets_a_sentence_for_every_code(self):
        from verbatim_app.routes import interview as screen
        table = json.loads(screen._frame_strings(self.app.state.t))
        for code in self.CODES:
            key = "error_" + code.replace("-", "_")
            self.assertIn(key, table, code)
            self.assertNotEqual(table[key], f"interview.{key}", code)

    def test_the_screen_has_a_sentence_for_every_refusal(self):
        strings = self.app.state.t
        for code in self.REFUSALS:
            key = "interview.refused_" + code.replace("-", "_")
            self.assertNotEqual(strings(key), key, code)

    def test_every_refusal_code_the_engine_raises_is_in_that_list(self):
        # The list is written by hand, so this is what keeps it honest.
        raised = set()
        for name in ("providers.py", "routes/interview.py"):
            source = (REPO / "app" / "verbatim_app" / name).read_text(
                encoding="utf-8")
            raised.update(re.findall(r'code="([a-z-]+)"', source))
            raised.update(re.findall(r'refusal="([a-z-]+)"', source))
        raised -= FRAME_CODES
        self.assertTrue(raised)
        self.assertEqual(raised - set(self.REFUSALS), set())

    def test_the_screen_has_a_sentence_for_every_configuration_problem(self):
        from verbatim_app.providers import Problem, Settings, problems
        strings = self.app.state.t
        found = set()
        for settings in (Settings("nope", "m", "https://x", "k"),
                         Settings("anthropic", "", "https://x", "k"),
                         Settings("anthropic", "m", "", "k"),
                         Settings("anthropic", "m", "https://x", None)):
            found.update(problem.code for problem in problems(settings))
        self.assertEqual(len(found), 4)
        for code in found:
            key = "interview.problem_" + code.replace("-", "_")
            self.assertNotEqual(strings(key), key, code)


class TestNothingConfiguredInFrench(WebCase):
    environ = {}
    lang = "fr"

    def test_a_refused_start_never_shows_engine_prose(self):
        # A plain form navigation renders the body as the whole page, so an
        # error detail written in the engine is English on a French screen.
        reply = self.client.post("/interview", follow_redirects=True)
        self.assertEqual(reply.status_code, 200)
        self.assertNotIn("no model is configured", reply.text)
        self.assertIn("Aucun modèle configuré", reply.text)


class TestEveryStopReasonHasASentence(WebCase):
    """The engine folds an unrecognised reason into a bare token. A bare token
    is the language leak in miniature, so every value a wire can emit has a
    string, and adding a sixth without one fails here."""

    def test_the_pack_names_every_reason_the_wires_can_emit(self):
        from verbatim_app.providers import AnthropicWire, OpenAIWire
        from verbatim_app.routes import interview as screen
        table = json.loads(screen._frame_strings(self.app.state.t))
        reasons = (set(AnthropicWire.STOPS.values())
                   | set(OpenAIWire.STOPS.values())
                   | {"other", "truncated"})
        for reason in reasons - {"end_turn"}:
            self.assertIn(f"stop_{reason}", table, reason)
            self.assertNotEqual(table[f"stop_{reason}"], f"interview.stop_{reason}")


class TestTheFrameStringsBlock(WebCase):
    def test_a_pack_string_cannot_end_the_script_block_early(self):
        from verbatim_app.routes import interview as screen
        strings = self.app.state.t
        strings.table["interview.thinking"] = "</script><script>alert(1)</script>"
        rendered = screen._frame_strings(strings)
        self.assertNotIn("</script", rendered)
        self.assertIn("\\u003c", rendered)
        self.assertEqual(json.loads(rendered)["thinking"],
                         "</script><script>alert(1)</script>")

    def test_the_page_carries_it_escaped(self):
        self.app.state.t.table["interview.thinking"] = "</script>oops"
        page = self.client.get(f"/interview/{self.open_interview()}")
        self.assertNotIn("</script>oops", page.text)


class TestTheStreamIsNotCached(WebCase):
    scripts = (says("Which agency?"),)

    def test_a_turn_is_never_served_from_a_cache(self):
        reply = self.turn(self.open_interview(), "Four months.")
        self.assertEqual(reply.headers["cache-control"], "no-store")


class TestInFrench(WebCase):
    scripts = (says("Quelle agence ?"),)

    def setUp(self):
        super().setUp()
        self.client = TestClient(
            create_app(self.root, lang="fr", environ=dict(self.environ),
                       transport=self.transport),
            base_url="http://127.0.0.1:8747")

    def test_the_screen_speaks_the_pack_not_the_engine(self):
        page = self.client.get("/interview")
        self.assertIn("Ce qui répondrait", page.text)
        self.assertNotIn("What would answer", page.text)

    def test_the_frame_strings_the_browser_gets_are_the_pack_too(self):
        page = self.client.get(f"/interview/{self.open_interview()}")
        self.assertIn("En attente du modèle", page.text)
        self.assertNotIn("Waiting for the model", page.text)


SHEET_ARGS = {
    "angle": "Four months lost to agency work",
    "elements": ["four months on agencies", "two clients signed since"],
    "moment": "j'ai passé quatre mois à écrire pour des agences",
    "conviction": "le canal direct est le seul qui paie",
    "first_lines": ["Quatre mois pour rien.", "J'ai arrêté les agences."],
}


class SheetCase(WebCase):
    def with_sheet(self, approved=False):
        """A sheet put on disk directly: these tests are about the guard and
        the click, not about the wire that carries a proposal."""
        interview_id = self.open_interview()
        conversation = interview.load(self.root, interview_id)
        interview.propose(conversation, dict(SHEET_ARGS))
        if approved:
            interview.approve(conversation, conversation.sheet.digest(),
                              first_line=0)
        interview.save(self.root, conversation)
        return interview_id

    def approve(self, interview_id, digest=None, first_line="0"):
        """POST the click. The digest defaults to the disk's, which is what
        a fresh page would carry; a test about staleness passes its own.

        `first_line` is which proposed opening was taken, and it defaults to
        the first one because a form that carries no choice is refused: the
        tests about that refusal pass their own.
        """
        if digest is None:
            sheet = interview.load(self.root, interview_id).sheet
            digest = sheet.digest() if sheet else ""
        return self.client.post(f"/interview/{interview_id}/sheet/approve",
                                data={"sheet": digest,
                                      "first_line": first_line},
                                follow_redirects=False)


class TestAProposalOnTheWire(SheetCase):
    """The model calls propose_sheet; the sheet reaches disk, then the frame
    that fills the panel."""

    scripts = (asks(("c1", "propose_sheet", SHEET_ARGS)),
               says("Shall we go with this sheet?"))

    def test_the_model_is_offered_the_sheet_tool(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        offered = [tool["name"]
                   for tool in self.transport.calls[0]["payload"]["tools"]]
        self.assertIn("propose_sheet", offered)

    def test_the_proposal_reaches_the_disk(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        sheet = interview.load(self.root, interview_id).sheet
        self.assertEqual(sheet.state, "proposed")
        self.assertEqual(sheet.angle, SHEET_ARGS["angle"])
        self.assertEqual(sheet.first_lines, tuple(SHEET_ARGS["first_lines"]))

    def test_the_sheet_frame_follows_the_tool_result(self):
        interview_id = self.open_interview()
        reply = self.turn(interview_id, "Four months on agencies.")
        sequence = kinds(reply.text)
        self.assertIn("sheet", sequence)
        self.assertEqual(sequence.index("sheet"),
                         sequence.index("tool_result") + 1)
        frame = [f for f in frames(reply.text) if f["kind"] == "sheet"][0]
        self.assertEqual(frame["state"], "proposed")
        self.assertEqual(frame["angle"], SHEET_ARGS["angle"])
        self.assertEqual(frame["elements"], SHEET_ARGS["elements"])
        self.assertEqual(frame["moment"], SHEET_ARGS["moment"])
        self.assertEqual(frame["conviction"], SHEET_ARGS["conviction"])
        self.assertEqual(frame["first_lines"], SHEET_ARGS["first_lines"])

    def test_the_screen_renders_the_sheet_and_the_approve_form(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "Four months on agencies.")
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn(SHEET_ARGS["angle"], page.text)
        # The apostrophe is escaped on its way into markup, so the assertion
        # holds the part of the quote that has none.
        self.assertIn("quatre mois à écrire pour des agences", page.text)
        self.assertIn(f"/interview/{interview_id}/sheet/approve", page.text)
        self.assertIn('id="say"', page.text)


class TestARefusedProposal(SheetCase):
    """A proposal the store refuses answers the model and stores nothing."""

    scripts = (asks(("c1", "propose_sheet",
                     dict(SHEET_ARGS, elements=[]))),
               says("Let me gather the elements first."))

    def test_nothing_lands_and_the_tool_says_why(self):
        interview_id = self.open_interview()
        reply = self.turn(interview_id, "Four months on agencies.")
        self.assertIsNone(interview.load(self.root, interview_id).sheet)
        sequence = kinds(reply.text)
        self.assertNotIn("sheet", sequence)
        result = [f for f in frames(reply.text)
                  if f["kind"] == "tool_result"][0]
        self.assertTrue(result["is_error"])
        self.assertIn("elements", result["result"])


class TestTheClick(SheetCase):
    """Approval is the person's click, and the only writer of `approved`."""

    def test_the_click_approves_and_comes_back_to_the_screen(self):
        interview_id = self.with_sheet()
        reply = self.approve(interview_id)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(reply.headers["location"],
                         f"/interview/{interview_id}")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.sheet.state, "approved")
        self.assertTrue(conversation.sheet.approved)
        self.assertEqual(conversation.state, "open")

    def test_a_second_click_is_the_same_decision(self):
        interview_id = self.with_sheet()
        self.approve(interview_id)
        stamped = interview.load(self.root, interview_id).sheet.approved
        self.assertEqual(self.approve(interview_id).status_code, 303)
        self.assertEqual(interview.load(self.root, interview_id).sheet.approved,
                         stamped)

    def test_a_click_with_no_sheet_changes_nothing(self):
        interview_id = self.open_interview()
        self.assertEqual(self.approve(interview_id).status_code, 303)
        self.assertIsNone(interview.load(self.root, interview_id).sheet)

    def test_a_click_on_a_discarded_interview_goes_to_the_hub(self):
        interview_id = self.with_sheet()
        self.client.post(f"/interview/{interview_id}/discard")
        reply = self.approve(interview_id, digest="")
        self.assertEqual(reply.headers["location"], "/interview")

    def test_the_click_loses_to_a_running_turn_and_loses_nothing(self):
        # An approval written beside a running turn would be overwritten by
        # that turn's next save: an approval lost in silence. Losing the lock
        # instead leaves the sheet proposed, the screen says a turn is
        # running, and the click can happen again.
        from verbatim_app.routes import interview as screen
        interview_id = self.with_sheet()
        lock = screen.lock_for(self.app, interview_id)
        self.assertTrue(lock.acquire(blocking=False))
        try:
            reply = self.approve(interview_id)
        finally:
            lock.release()
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(reply.headers["location"],
                         f"/interview/{interview_id}?notice=turn-running")
        self.assertEqual(interview.load(self.root, interview_id).sheet.state,
                         "proposed")
        told = self.client.get(
            f"/interview/{interview_id}?notice=turn-running")
        self.assertIn("already has a turn running", told.text)


class TestTheSignatureNamesWhatWasRead(SheetCase):
    """The refuted finding of the first review round: the click used to
    approve whatever sheet was on disk, not the sheet the person read. A
    replacement can land between the screen being drawn and the click, and
    the party writing replacements is the model, the very party the sheet
    guards against."""

    def test_a_stale_click_approves_nothing_and_says_why(self):
        interview_id = self.with_sheet()
        stale = interview.load(self.root, interview_id).sheet.digest()
        conversation = interview.load(self.root, interview_id)
        interview.propose(conversation,
                          dict(SHEET_ARGS, angle="A different angle"))
        interview.save(self.root, conversation)
        reply = self.approve(interview_id, digest=stale)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(reply.headers["location"],
                         f"/interview/{interview_id}?notice=sheet-changed")
        after = interview.load(self.root, interview_id).sheet
        self.assertEqual(after.state, "proposed")
        self.assertEqual(after.angle, "A different angle")

    def test_a_click_with_no_digest_approves_nothing(self):
        interview_id = self.with_sheet()
        reply = self.client.post(
            f"/interview/{interview_id}/sheet/approve",
            follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(interview.load(self.root, interview_id).sheet.state,
                         "proposed")

    def test_the_page_carries_the_digest_it_shows(self):
        interview_id = self.with_sheet()
        digest = interview.load(self.root, interview_id).sheet.digest()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn(f'id="sheet-digest" value="{digest}"', page.text)

    def test_the_sheet_frame_carries_its_digest(self):
        # The script moves this value into the form when it fills the panel,
        # so the live path signs what is displayed too.
        conversation = interview.Conversation(
            id="2026-08-28-1500", skill="linkedin-post", sections=(),
            interface_language="en", output_language="en",
            provider="anthropic", model="m", started="", updated="")
        sheet = interview.propose(conversation, dict(SHEET_ARGS))
        from verbatim_app.routes.interview import _sheet_fields
        self.assertEqual(_sheet_fields(sheet)["digest"], sheet.digest())

    def test_the_notice_shows_the_sentence_and_only_for_known_codes(self):
        interview_id = self.with_sheet()
        told = self.client.get(
            f"/interview/{interview_id}?notice=sheet-changed")
        self.assertIn("nothing was approved", told.text)
        quiet = self.client.get(
            f"/interview/{interview_id}?notice=<script>x</script>")
        self.assertNotIn("nothing was approved", quiet.text)
        self.assertNotIn("<script>x</script>", quiet.text)

    def test_a_replacement_with_identical_content_still_signs(self):
        # Content is the identity: the same five fields proposed again are
        # the same decision, whatever the timestamps say.
        interview_id = self.with_sheet()
        stale = interview.load(self.root, interview_id).sheet.digest()
        conversation = interview.load(self.root, interview_id)
        interview.propose(conversation, dict(SHEET_ARGS))
        interview.save(self.root, conversation)
        self.approve(interview_id, digest=stale)
        self.assertEqual(interview.load(self.root, interview_id).sheet.state,
                         "approved")


class TestAnApprovedSheetEndsTheQuestions(SheetCase):
    """The skill's rule made mechanical: no interview turn runs past an
    approved sheet. The interview stays open, because closed means it became
    a post."""

    def test_the_turn_is_refused(self):
        interview_id = self.with_sheet(approved=True)
        reply = self.turn(interview_id, "One more thing.")
        self.assertEqual(reply.status_code, 409)
        self.assertEqual(reply.json()["detail"], "sheet-approved")

    def test_the_generator_rechecks_under_the_lock(self):
        # The handler's refusal reads a copy only as fresh as losing the race
        # left it, so the turn itself decides again, like `closed` does.
        from verbatim_app.routes import interview as screen
        interview_id = self.with_sheet(approved=True)
        request = Bare(self.app)
        stream = screen._run(request, screen._engine(request), interview_id,
                             "One more thing.",
                             screen.lock_for(self.app, interview_id))
        first = json.loads(next(stream)[len("data: "):])
        self.assertEqual(first, {"kind": "error", "code": "sheet-approved"})
        stream.close()
        self.assertEqual(
            interview.load(self.root, interview_id).person_turns(), [])

    def test_the_screen_says_so_instead_of_offering_the_box(self):
        interview_id = self.with_sheet(approved=True)
        page = self.client.get(f"/interview/{interview_id}")
        self.assertNotIn('id="say"', page.text)
        self.assertIn('id="sheet-approved-notice"', page.text)
        self.assertNotIn('id="sheet-approved-notice" hidden', page.text)

    def test_a_proposed_sheet_does_not_end_them(self):
        interview_id = self.with_sheet()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="say"', page.text)





class TestTheFirstLineIsChosenOnTheScreen(SheetCase):
    """F1. The sheet proposes one or two openings and the click that
    approves it now says which one was taken.

    The skill already says the post is written for the chosen proposal, to
    the character. Nobody was ever asked, so nothing was ever chosen, and
    what the model does with no decision is open on a lukewarm self
    description over two proposals that were better.
    """

    def test_a_proposed_sheet_offers_the_choice_beside_the_lines(self):
        interview_id = self.with_sheet()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('name="first_line" value="0"', page.text)
        self.assertIn('name="first_line" value="1"', page.text)
        self.assertIn('name="first_line" value="none"', page.text)
        # Beside the line and still part of the approval: the radios are
        # inside the sheet display and carry the form they belong to.
        self.assertIn('form="sheet-approve" required', page.text)

    def test_an_approval_that_decided_nothing_writes_nothing(self):
        interview_id = self.with_sheet()
        reply = self.approve(interview_id, first_line="")
        self.assertEqual(reply.status_code, 303)
        self.assertIn("notice=first-line-missing", reply.headers["location"])
        self.assertEqual(interview.load(self.root, interview_id).sheet.state,
                         "proposed")

    def test_the_screen_says_why_nothing_was_approved(self):
        interview_id = self.with_sheet()
        page = self.client.get(
            f"/interview/{interview_id}?notice=first-line-missing")
        self.assertIn(
            shown(self.app.state.t("interview.sheet_first_line_missing")),
            page.text)

    def test_a_value_that_is_not_a_decision_is_not_read_as_one(self):
        # Fail closed. The whole point of the step is that skipping it used
        # to be silent, so anything that is not one of the shapes the form
        # sends lands on undecided and is refused.
        interview_id = self.with_sheet()
        # The superscript is not decoration. `str.isdigit` says yes to it and
        # `int` says no, which is a 500 out of a form field rather than the
        # refusal this route documents. Its sibling `draft` has always
        # caught that; this one was written without the guard.
        for wrong in ("nope", "-1", "1.0", "nothing", "0x0", "none of them",
                      "\u00b2", "\u0662", "9" * 5000):
            reply = self.approve(interview_id, first_line=wrong)
            self.assertIn("notice=first-line-missing",
                          reply.headers["location"], wrong)
            self.assertEqual(
                interview.load(self.root, interview_id).sheet.state,
                "proposed", wrong)

    def test_whitespace_around_a_decision_is_not_a_different_decision(self):
        # Form handling, not leniency about the step: a padded value is the
        # same click.
        interview_id = self.with_sheet()
        self.approve(interview_id, first_line=" none ")
        self.assertEqual(interview.load(self.root, interview_id)
                         .sheet.first_line, interview.NEITHER)

    def test_taking_one_records_it_and_the_screen_says_which(self):
        interview_id = self.with_sheet()
        self.approve(interview_id, first_line="1")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.sheet.first_line, 1)
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn(shown(self.app.state.t(
            "interview.sheet_first_line_taken")), page.text)
        # And the choice is gone from the screen as a choice: an approved
        # sheet is frozen, and a radio that changes nothing is a lie.
        self.assertNotIn('name="first_line"', page.text)

    def test_refusing_both_is_recorded_and_said(self):
        interview_id = self.with_sheet()
        self.approve(interview_id, first_line="none")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.sheet.first_line, interview.NEITHER)
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn(shown(self.app.state.t(
            "interview.sheet_first_line_none_taken")), page.text)

    def test_the_writer_is_handed_the_line_that_was_taken(self):
        interview_id = self.with_sheet()
        self.approve(interview_id, first_line="1")
        conversation = interview.load(self.root, interview_id)
        material = interview.material(conversation)
        self.assertIn(f'"first_line": "{SHEET_ARGS["first_lines"][1]}"',
                      material)


class TestNothingIsOfferedWithNoHistoryBehindIt(SheetCase):
    """E2. Alchie's back arrow does not exist until the third question, and
    the rule under it is the one worth taking: a control with nothing behind
    it is not on the screen.

    Ours had one. The sheet is refused before anybody has said anything,
    with `nothing-to-send`, because a sheet asked for then is a sheet the
    model has to invent, and inventing it is the failure the sheet exists to
    catch. The button was on the page all the same, and clicking it was the
    only way to find out.
    """

    def test_the_sheet_is_not_offered_before_the_first_turn(self):
        interview_id = self.open_interview()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="ask-sheet"', page.text)
        self.assertIn('id="ask-sheet" hidden', page.text)
        self.assertIn('id="ask-sheet-hint" hidden', page.text)

    def test_the_server_refuses_what_the_screen_now_hides(self):
        # The two halves have to agree, and this is the one that matters:
        # hiding a control is a courtesy, and the refusal is the rule.
        interview_id = self.open_interview()
        reply = self.client.post(f"/interview/{interview_id}/sheet/propose")
        self.assertEqual(reply.status_code, 422)

    def test_it_is_offered_once_something_has_been_said(self):
        interview_id = self.open_interview()
        conversation = interview.load(self.root, interview_id)
        interview.say(conversation, "j'ai arrete les agences")
        interview.save(self.root, conversation)
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="ask-sheet"', page.text)
        self.assertNotIn('id="ask-sheet" hidden', page.text)
        self.assertNotIn('id="ask-sheet-hint" hidden', page.text)

    def test_the_answer_box_is_there_from_the_first_second(self):
        # What is hidden is the control with nothing behind it, not the one
        # that puts something there.
        interview_id = self.open_interview()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="say"', page.text)
        self.assertIn('id="text"', page.text)


class TestHowMuchIsOnTheTable(SheetCase):
    """The number beside the sentence. D1, and D2 as the thing it reads.

    The engine names what is missing every turn, which is the honest half
    and the unreadable one. This is the readable half, and it never replaces
    the sentence.
    """

    def test_an_interview_with_nothing_in_it_reads_zero(self):
        interview_id = self.open_interview()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn(shown(self.app.state.t("interview.sufficiency",
                                             ratio=0)), page.text)

    def test_what_was_said_is_what_moved_it(self):
        interview_id = self.open_interview()
        conversation = interview.load(self.root, interview_id)
        interview.say(conversation, "12 clients chez Malt en 3 semaines")
        interview.save(self.root, conversation)
        page = self.client.get(f"/interview/{interview_id}")
        reading = interview.sufficiency(conversation)
        self.assertEqual(reading.facts, 3)
        self.assertIn(shown(self.app.state.t("interview.sufficiency",
                                             ratio=reading.ratio)), page.text)

    def test_the_frame_carries_the_same_reading_the_page_would_draw(self):
        # One function for both, so the line rewritten mid interview is the
        # line a reload draws. Two would drift, and the live one is the one
        # nobody reloads to check.
        interview_id = self.open_interview()
        reply = self.client.post(f"/interview/{interview_id}/turn",
                                 data={"text": "12 clients chez Malt"})
        accepted = [f for f in frames(reply.text) if f["kind"] == "accepted"]
        self.assertEqual(len(accepted), 1)
        conversation = interview.load(self.root, interview_id)
        reading = interview.sufficiency(conversation)
        self.assertEqual(accepted[0]["ratio"], reading.ratio)
        self.assertEqual(accepted[0]["facts"], reading.facts)


DRAFT_ARGS = {
    "body": "Quatre mois pour rien.\n\nJ'ai écrit pour des agences, et le "
            "canal direct est le seul qui paie.",
    "anchors": [{"post": "le canal direct est le seul qui paie",
                 "said": "le canal direct est le seul qui paie"}],
}


class DraftCase(SheetCase):
    """The material a draft is written from: something said, a signed sheet."""

    def signed(self):
        interview_id = self.open_interview()
        conversation = interview.load(self.root, interview_id)
        interview.say(conversation,
                      "le canal direct est le seul qui paie, j'ai arrêté "
                      "les agences")
        interview.propose(conversation, dict(SHEET_ARGS))
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0)
        interview.save(self.root, conversation)
        return interview_id

    def draft(self, interview_id, text=""):
        return self.client.post(f"/interview/{interview_id}/draft",
                                data={"text": text})

    def drafted(self, interview_id=None):
        """A signed interview with a draft on it, put there directly: these
        tests are about the revision and the filing, not about the wire that
        carries a proposal."""
        interview_id = interview_id or self.signed()
        conversation = interview.load(self.root, interview_id)
        interview.write(conversation, dict(DRAFT_ARGS))
        interview.save(self.root, conversation)
        return interview_id


class TestAskingForASheet(SheetCase):
    """The person asks for the sheet, and the turn requires the tool. That
    requirement is the whole mechanism: a model too weak to reach for a tool
    on its own answers in prose, and prose triggers nothing at all."""

    scripts = (asks(("c1", "propose_sheet", SHEET_ARGS)),
               says("Here it is."))

    def ask(self, interview_id):
        return self.client.post(f"/interview/{interview_id}/sheet/propose")

    def said(self):
        """An interview with something in it. A sheet asked for before
        anybody has spoken is a sheet the model has to invent."""
        interview_id = self.open_interview()
        conversation = interview.load(self.root, interview_id)
        interview.say(conversation, "four months on agencies, nothing signed")
        interview.save(self.root, conversation)
        return interview_id

    def test_nothing_said_means_nothing_to_make_a_sheet_from(self):
        reply = self.ask(self.open_interview())
        self.assertEqual(reply.status_code, 422)
        self.assertEqual(self.transport.calls, [])

    def test_the_first_request_requires_the_sheet_tool(self):
        interview_id = self.said()
        self.ask(interview_id)
        self.assertEqual(self.transport.calls[0]["payload"]["tool_choice"],
                         {"type": "tool", "name": "propose_sheet"})

    def test_the_requirement_is_gone_from_the_turn_that_answers_it(self):
        interview_id = self.said()
        self.ask(interview_id)
        self.assertNotIn("tool_choice", self.transport.calls[1]["payload"])

    def test_the_sheet_lands_and_the_frame_fills_the_panel(self):
        interview_id = self.said()
        reply = self.ask(interview_id)
        self.assertIn("sheet", kinds(reply.text))
        self.assertEqual(
            interview.load(self.root, interview_id).sheet.state, "proposed")

    def test_an_approved_sheet_is_not_asked_for_again(self):
        interview_id = self.with_sheet(approved=True)
        self.assertEqual(self.ask(interview_id).status_code, 409)
        self.assertEqual(self.transport.calls, [])


class TestTheDraftTurn(DraftCase):
    scripts = (asks(("c1", "propose_draft", DRAFT_ARGS)),
               says("Written."))

    def test_nothing_is_drafted_before_the_sheet_is_signed(self):
        interview_id = self.open_interview()
        reply = self.draft(interview_id)
        self.assertEqual(reply.status_code, 409)
        self.assertEqual(reply.json()["detail"], "sheet-not-approved")
        self.assertEqual(self.transport.calls, [])

    def aimed(self, interview_id, text, index):
        """A revision aimed at one block of the draft on disk."""
        conversation = interview.load(self.root, interview_id)
        block = passages_of(conversation.draft.body)[index]
        return self.client.post(
            f"/interview/{interview_id}/draft",
            data={"text": text, "passage": block.digest,
                  "passage_index": str(index)})

    def test_a_scoped_request_requires_the_tool_that_can_only_reach_it(self):
        # The whole guarantee. `propose_draft` takes a body, so a body is
        # what it can write; the passage tool cannot reach past its span.
        self.aimed(self.drafted(), "Trop vague.", 1)
        self.assertEqual(self.transport.calls[0]["payload"]["tool_choice"],
                         {"type": "tool", "name": "rewrite_passage"})

    def test_an_unscoped_request_still_gets_the_whole_post_tool(self):
        self.draft(self.drafted(), text="Plus court.")
        self.assertEqual(self.transport.calls[0]["payload"]["tool_choice"],
                         {"type": "tool", "name": "propose_draft"})

    def test_the_material_of_a_scoped_turn_quotes_the_block(self):
        interview_id = self.drafted()
        block = passages_of(
            interview.load(self.root, interview_id).draft.body)[1]
        self.aimed(interview_id, "Trop vague.", 1)
        material = self.transport.calls[0]["payload"]["messages"][0][
            "content"][0]["text"]
        self.assertIn("## Passage", material)
        self.assertIn(block.text, material.split("## Passage")[1])

    def test_a_stale_passage_writes_nothing_and_says_so(self):
        # A turn behind the page can replace the post while somebody reads
        # it. The request must not land on whatever is at that index now.
        interview_id = self.drafted()
        reply = self.client.post(
            f"/interview/{interview_id}/draft",
            data={"text": "Trop vague.", "passage": "0" * 16,
                  "passage_index": "1"})
        self.assertIn("passage-gone",
                      [frame.get("code") for frame in frames(reply.text)])
        after = interview.load(self.root, interview_id)
        self.assertEqual(after.revisions, [])
        self.assertEqual(self.transport.calls, [])

    def test_an_index_that_is_not_a_number_is_refused_at_the_door(self):
        interview_id = self.drafted()
        reply = self.client.post(
            f"/interview/{interview_id}/draft",
            data={"text": "Trop vague.", "passage": "0" * 16,
                  "passage_index": "the second one"})
        self.assertEqual(reply.status_code, 400)

    def test_two_rewrites_in_one_message_do_not_cut_the_post_apart(self):
        """Both wired providers may put several calls in one message, and
        `tool_choice` asks for at least one, never at most one. The second
        call carries the offsets of the body the first one already rewrote:
        spliced blindly it eats the block after it and cuts the next one
        mid-word. The engine refuses it and the post is what the first call
        made it, which is the whole promise of a scoped rewrite."""
        interview_id = self.drafted()
        conversation = interview.load(self.root, interview_id)
        blocks = passages_of(conversation.draft.body)
        self.transport.scripts = list(
            (asks(("c1", "rewrite_passage", {"passage": "Court."}),
                  ("c2", "rewrite_passage",
                   {"passage": "Un deuxième essai, nettement plus long."})),
             says("Rewritten.")))
        self.aimed(interview_id, "Trop vague.", 1)
        after = interview.load(self.root, interview_id).draft.body
        self.assertEqual(
            after, replace_passage(conversation.draft.body, blocks[1],
                                   "Court."))
        self.assertEqual(len(passages_of(after)), len(blocks))

    def test_an_additive_first_call_does_not_let_a_second_one_weld_itself(self):
        """The same message, the same two calls, but the first one returns
        the block plus a sentence, which is what "put the real number in"
        comes back as. The bytes at the old span are then still the old
        text, so a guard comparing content there passes and the second call
        lands its text welded onto the first call's tail, inside a word."""
        interview_id = self.drafted()
        conversation = interview.load(self.root, interview_id)
        blocks = passages_of(conversation.draft.body)
        added = blocks[1].text + " Douze clients en trois semaines."
        self.transport.scripts = list(
            (asks(("c1", "rewrite_passage", {"passage": added}),
                  ("c2", "rewrite_passage", {"passage": "SUITEACCOLEE"})),
             says("Rewritten.")))
        self.aimed(interview_id, "Mets le vrai chiffre.", 1)
        after = interview.load(self.root, interview_id).draft.body
        self.assertEqual(after, replace_passage(conversation.draft.body,
                                                blocks[1], added))
        self.assertNotIn("SUITEACCOLEE", after)
        self.assertEqual(len(passages_of(after)), len(blocks))

    def test_a_first_call_that_splits_the_block_closes_it_too(self):
        """The variant a proof about the block cannot see: the first call
        answers with the block, a blank line and the added sentence. The
        block becomes two and the first half is byte-identical, so its index
        and its digest both still match while everything after it moved. A
        second call would splice into that half and orphan the sentence."""
        interview_id = self.drafted()
        conversation = interview.load(self.root, interview_id)
        blocks = passages_of(conversation.draft.body)
        split = blocks[1].text + "\n\nEt douze clients en trois semaines."
        self.transport.scripts = list(
            (asks(("c1", "rewrite_passage", {"passage": split}),
                  ("c2", "rewrite_passage", {"passage": "ORPHELINE"})),
             says("Rewritten.")))
        self.aimed(interview_id, "Mets le vrai chiffre.", 1)
        after = interview.load(self.root, interview_id).draft.body
        self.assertEqual(after, replace_passage(conversation.draft.body,
                                                blocks[1], split))
        self.assertNotIn("ORPHELINE", after)

    def test_a_scope_nobody_sent_does_not_survive_into_the_next_turn(self):
        """The screen says what is about to happen and the engine has to do
        that. A request aimed at a passage that got nothing back stays
        pending; a later turn whose picker reads "the whole post" must be a
        whole post turn, not that block again with the scope line hidden."""
        interview_id = self.drafted()
        self.aimed(interview_id, "Trop vague.", 1)
        self.transport.calls.clear()
        self.client.post(f"/interview/{interview_id}/draft", data={"text": ""})
        self.assertEqual(self.transport.calls[0]["payload"]["tool_choice"],
                         {"type": "tool", "name": "propose_draft"})

    def test_the_screen_offers_that_scope_back_instead_of_dropping_it(self):
        # The other half of the same rule: the engine follows the form, so
        # the form has to remember. A picker that reset itself would lose
        # the passage on the reload after a refusal.
        interview_id = self.drafted()
        block = passages_of(
            interview.load(self.root, interview_id).draft.body)[1]
        self.aimed(interview_id, "Trop vague.", 1)
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn(f'value="1" data-digest="{block.digest}"', page.text)
        self.assertIn("selected", page.text)

    def test_the_turn_requires_the_draft_tool(self):
        self.draft(self.signed())
        self.assertEqual(self.transport.calls[0]["payload"]["tool_choice"],
                         {"type": "tool", "name": "propose_draft"})

    def test_the_request_is_built_from_the_material_not_from_the_interview(self):
        # A revision restarts from the interview material, says the skill.
        # The engine therefore hands over one fresh message rather than
        # appending to the list the questions happened in.
        interview_id = self.signed()
        self.draft(interview_id)
        sent = self.transport.calls[0]["payload"]["messages"]
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["role"], "user")
        material = sent[0]["content"][0]["text"]
        self.assertIn("le canal direct est le seul qui paie", material)
        self.assertIn(SHEET_ARGS["angle"], material)

    def test_the_drafting_turn_writes_nothing_into_the_interview(self):
        # The anchoring source is what the person said. A turn that appended
        # to that list would let the engine put words in their mouth.
        interview_id = self.signed()
        before = interview.load(self.root, interview_id)
        self.draft(interview_id)
        after = interview.load(self.root, interview_id)
        self.assertEqual(after.messages, before.messages)
        self.assertEqual(after.said(), before.said())

    def test_the_draft_reaches_the_disk(self):
        interview_id = self.signed()
        self.draft(interview_id)
        draft = interview.load(self.root, interview_id).draft
        self.assertEqual(draft.body, DRAFT_ARGS["body"])
        self.assertEqual(len(draft.anchors), 1)
        self.assertTrue(draft.written)

    def test_the_step_that_drafts_is_the_writing_step(self):
        interview_id = self.signed()
        self.draft(interview_id)
        system = self.transport.calls[0]["payload"]["system"]
        self.assertIn("The signature block is not generated", system)

    def test_what_the_turn_cost_is_added_to_the_interview(self):
        interview_id = self.signed()
        self.draft(interview_id)
        conversation = interview.load(self.root, interview_id)
        self.assertGreater(conversation.usage.input_tokens, 0)

    def test_the_draft_frame_carries_the_panel(self):
        interview_id = self.signed()
        reply = self.draft(interview_id)
        sequence = kinds(reply.text)
        self.assertIn("draft", sequence)
        self.assertEqual(sequence.index("draft"),
                         sequence.index("tool_result") + 1)
        frame = [f for f in frames(reply.text) if f["kind"] == "draft"][0]
        self.assertEqual(frame["body"], DRAFT_ARGS["body"])
        self.assertEqual([verdict["status"] for verdict in frame["verdicts"]],
                         ["anchored"])
        self.assertEqual(frame["counts"]["unanchored"], 1)
        # The pieces the panel paints, and their coverage: the highlight is
        # decided here, never in the browser.
        painted = [piece for row in frame["lines"] for piece in row]
        self.assertIn(True, [piece["covered"] for piece in painted])
        self.assertIn(False, [piece["covered"] for piece in painted])

    def test_a_second_draft_replaces_the_first(self):
        interview_id = self.signed()
        self.draft(interview_id)
        self.transport.scripts = list(
            (asks(("c2", "propose_draft", dict(DRAFT_ARGS, body="Autre."))),
             says("Rewritten.")))
        self.draft(interview_id)
        self.assertEqual(
            interview.load(self.root, interview_id).draft.body, "Autre.")



class TestTheVersionOnScreen(DraftCase):
    """The badge, what moved, and the way back.

    A rewrite aimed at one block leaves every other byte where it was. What
    that guarantee is worth to somebody is seeing which block moved and
    being able to put it back, and neither is readable off one body.
    """

    def second(self, interview_id, body="Quatre mois pour rien.\n\nAutre."):
        conversation = interview.load(self.root, interview_id)
        interview.write(conversation, dict(DRAFT_ARGS, body=body))
        interview.save(self.root, conversation)
        return conversation

    def test_a_first_draft_carries_no_version_and_no_way_back(self):
        interview_id = self.drafted()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertNotIn("V2", page.text)
        self.assertNotIn("draft/revert", page.text)
        self.assertNotIn(shown(self.app.state.t("interview.moved_legend")),
                         page.text)

    def test_a_rewrite_puts_the_version_the_legend_and_the_way_back_up(self):
        interview_id = self.drafted()
        self.second(interview_id)
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn("V2", page.text)
        self.assertIn(f"/interview/{interview_id}/draft/revert", page.text)
        self.assertIn(shown(self.app.state.t("interview.moved_legend")),
                      page.text)

    def test_only_the_block_that_moved_carries_the_mark(self):
        interview_id = self.drafted()
        self.second(interview_id)
        page = self.client.get(f"/interview/{interview_id}")
        rows = re.findall(r'<p class="moved">(.*?)</p>|<p>(.*?)</p>',
                          page.text, re.S)
        moved = [a for a, b in rows if a]
        self.assertTrue(any("Autre." in row for row in moved), page.text)
        self.assertFalse(any("Quatre mois pour rien." in row
                             for row in moved), page.text)

    def test_the_frame_says_which_rows_moved_and_says_it_per_row(self):
        interview_id = self.drafted()
        self.second(interview_id)
        page = self.client.get(f"/interview/{interview_id}")
        conversation = interview.load(self.root, interview_id)
        from verbatim_app.routes.interview import panel
        trace = panel(conversation)
        self.assertEqual(len(trace["moved"]), len(trace["lines"]))
        self.assertEqual(trace["version"], 2)

    def test_going_back_restores_the_body_and_the_anchors(self):
        interview_id = self.drafted()
        first = interview.load(self.root, interview_id).draft
        self.second(interview_id)
        conversation = interview.load(self.root, interview_id)
        reply = self.client.post(
            f"/interview/{interview_id}/draft/revert",
            data={"body": digest_of(conversation.draft.body)},
            follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        again = interview.load(self.root, interview_id)
        self.assertEqual(again.draft.body, first.body)
        self.assertEqual(again.draft.anchors, first.anchors)
        self.assertEqual(again.earlier, [])

    def test_going_back_on_a_stale_screen_writes_nothing(self):
        interview_id = self.drafted()
        self.second(interview_id)
        reply = self.client.post(f"/interview/{interview_id}/draft/revert",
                                 data={"body": digest_of("un autre post")},
                                 follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertIn("notice=draft-changed", reply.headers["location"])
        again = interview.load(self.root, interview_id)
        self.assertEqual(again.draft.body, "Quatre mois pour rien.\n\nAutre.")
        self.assertEqual(len(again.earlier), 1)

    def test_a_stale_screen_is_told_so_when_it_comes_back(self):
        interview_id = self.drafted()
        self.second(interview_id)
        page = self.client.get(
            f"/interview/{interview_id}?notice=draft-changed")
        self.assertIn(shown(self.app.state.t("interview.draft_changed")),
                      page.text)

    def test_going_back_with_nowhere_to_go_writes_nothing(self):
        interview_id = self.drafted()
        conversation = interview.load(self.root, interview_id)
        reply = self.client.post(
            f"/interview/{interview_id}/draft/revert",
            data={"body": digest_of(conversation.draft.body)},
            follow_redirects=False)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(
            interview.load(self.root, interview_id).draft.body,
            DRAFT_ARGS["body"])

    def test_going_back_beside_a_running_turn_waits(self):
        interview_id = self.drafted()
        self.second(interview_id)
        conversation = interview.load(self.root, interview_id)
        digest = digest_of(conversation.draft.body)
        from verbatim_app.routes.interview import lock_for
        lock = lock_for(self.client.app, interview_id)
        lock.acquire()
        try:
            reply = self.client.post(
                f"/interview/{interview_id}/draft/revert",
                data={"body": digest}, follow_redirects=False)
        finally:
            lock.release()
        self.assertIn("notice=turn-running", reply.headers["location"])
        self.assertEqual(len(interview.load(self.root, interview_id).earlier),
                         1)



class TestWhereADraftingTurnTalks(DraftCase):
    """The panel a revision is typed in is the panel its answer lands in.

    The screen side of it: the container has to be on the page for the
    client to have somewhere to write. Which of the two channels a turn
    reaches for is the client's decision and is tested in
    `interview.test.js`, against the same id.
    """

    def test_the_panel_has_a_channel_of_its_own(self):
        interview_id = self.drafted()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="revision-reply"', page.text)
        # Empty until a turn speaks. A container holding last session's
        # exchange would be the screen answering a question nobody asked.
        self.assertIn('id="revision-reply" hidden></div>', page.text)

    def test_the_channel_is_there_for_a_first_draft_too(self):
        # It follows the button that starts a drafting turn, not the draft.
        # The thread above is the interview, and by the time this button is
        # on the page an approved sheet has ended the interview.
        interview_id = self.signed()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn('id="write-draft"', page.text)
        self.assertIn('id="revision-reply"', page.text)

    def test_there_is_no_channel_before_the_sheet_is_signed(self):
        interview_id = self.open_interview()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertNotIn('id="revision-reply"', page.text)




class TestTheBoxSaysWhichInterviewItIs(DraftCase):
    """F5's server half. What is typed in the revision box outlives the page
    it was typed on, in the browser's own store and per interview, so the
    box has to say which interview it belongs to.

    Nothing is kept on the conversation: a request reaches disk when
    somebody sends it, and a draft nobody sent is not something they said.
    """

    def test_the_box_carries_the_interview_it_belongs_to(self):
        interview_id = self.drafted()
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn(f'id="revision" rows="3" data-interview="{interview_id}"',
                      page.text)

    def test_a_request_never_sent_is_nowhere_on_the_conversation(self):
        interview_id = self.drafted()
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.revisions, [])


class TestTheTurnSaysWhichPhaseItIsIn(DraftCase):
    """F4. The waiting line follows the turn instead of saying one thing.

    Which phase is the server's to say, off the tool that was reached for.
    A browser holding the tool names would be a second place deciding which
    tool writes a post, and the two would disagree the day one is renamed.
    """

    scripts = (asks(("c1", "propose_draft", DRAFT_ARGS)), says("Done."))

    def test_the_draft_tool_is_the_post_phase(self):
        interview_id = self.signed()
        reply = self.draft(interview_id)
        calls = [f for f in frames(reply.text) if f["kind"] == "tool_call"]
        self.assertEqual([call["phase"] for call in calls], ["post"])

    def test_the_sheet_tool_is_the_sheet_phase(self):
        interview_id = self.open_interview()
        conversation = interview.load(self.root, interview_id)
        interview.say(conversation, "j'ai arrete les agences")
        interview.save(self.root, conversation)
        self.transport.scripts = list(
            (asks(("c1", "propose_sheet", SHEET_ARGS)), says("Here.")))
        reply = self.client.post(f"/interview/{interview_id}/sheet/propose")
        calls = [f for f in frames(reply.text) if f["kind"] == "tool_call"]
        self.assertEqual([call["phase"] for call in calls], ["sheet"])

    def test_every_phase_the_server_sends_has_a_sentence(self):
        # The language leak, caught where it starts. A phase the pack has no
        # words for renders as nothing on the screen, which is silent, so
        # the guard belongs here rather than in the browser.
        from verbatim_app.routes.interview import PHASE_OF
        strings = self.app.state.t
        for phase in set(PHASE_OF.values()):
            key = f"interview.waiting_{phase}"
            self.assertNotEqual(strings(key), key, phase)


PROSE = ("Quatre mois pour rien.\n\n"
         "J'ai écrit pour des agences, et le canal direct est le seul "
         "qui paie.\n\n"
         "ANCHORS\n"
         "POST: le canal direct est le seul qui paie\n"
         "SAID: le canal direct est le seul qui paie\n"
         "POST: an entry with no quote under it\n")


class TestARuntimeThatIgnoresTheRequiredTool(DraftCase):
    """Local runtimes do exactly this. The contract says the engine then
    reads the anchors block out of the prose, that the path is degraded, and
    that what could not be read is reported rather than swallowed."""

    scripts = (says(PROSE),)

    def test_the_block_is_read_out_of_the_prose(self):
        interview_id = self.signed()
        reply = self.draft(interview_id)
        draft = interview.load(self.root, interview_id).draft
        self.assertIsNotNone(draft)
        self.assertNotIn("ANCHORS", draft.body)
        self.assertEqual(len(draft.anchors), 1)
        self.assertIn("draft", kinds(reply.text))

    def test_what_could_not_be_read_travels_with_it(self):
        interview_id = self.signed()
        self.draft(interview_id)
        problems = interview.load(self.root, interview_id).draft.problems
        self.assertTrue(problems)
        # Anywhere in the list, not first: the road this arrived by leads it,
        # and the parse failures follow.
        self.assertIn("no SAID or SHEET quote", " ".join(problems))
        self.assertIn("propose_draft was required and was not called",
                      problems[0])


class TestAProseBlockWithASheetEntry(DraftCase):
    """The prose road carries the provenance too, or a local runtime, which
    is the one that takes this road, would land every sheet backing as
    something said."""

    scripts = (says("Quatre mois pour rien.\n\nJ'ai écrit pour des agences, "
                    "et le canal direct est le seul qui paie.\n\n"
                    "ANCHORS\n"
                    "POST: Quatre mois pour rien.\n"
                    "SHEET: Quatre mois pour rien.\n"),)

    def test_the_provenance_survives_the_prose_road(self):
        interview_id = self.signed()
        self.draft(interview_id)
        conversation = interview.load(self.root, interview_id)
        self.assertEqual([anchor.provenance
                          for anchor in conversation.draft.anchors], ["sheet"])
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["anchored"])


class TestProseWithNoBlockIsNotADraft(DraftCase):
    """Chatter is not a post. Storing it as one would put the engine's own
    talking in front of somebody with a traceability panel drawn round it."""

    scripts = (says("I would rather ask one more question first."),)

    def test_nothing_lands_and_the_page_is_not_asked_again(self):
        interview_id = self.signed()
        reply = self.draft(interview_id)
        self.assertIsNone(interview.load(self.root, interview_id).draft)
        self.assertNotIn("draft", kinds(reply.text))


class TestTheGuardUnderTheLock(DraftCase):
    """The handler refuses an unapproved sheet, and so does the generator.
    The copy the handler read is only as fresh as the moment it lost the
    race for the lock, so the one that matters is this one."""

    scripts = (says("should never run"),)

    def test_the_running_turn_refuses_on_its_own_reading(self):
        from verbatim_app.routes.interview import _engine, _run, lock_for
        interview_id = self.open_interview()
        conversation = interview.load(self.root, interview_id)
        interview.say(conversation, "something")
        interview.save(self.root, conversation)
        request = Bare(self.app)
        engine = _engine(request)
        sent = frames("".join(_run(request, engine, interview_id, "",
                                   lock_for(self.app, interview_id),
                                   require="propose_draft", drafting=True)))
        self.assertEqual([frame["kind"] for frame in sent], ["error"])
        self.assertEqual(sent[0]["code"], "sheet-not-approved")
        self.assertEqual(self.transport.calls, [])


class TestTheTraceabilityPanel(DraftCase):
    """The screen the product is named after. Three alarm states, equal in
    weight, and no verdict read off anything stored."""

    scripts = (asks(("c1", "propose_draft", dict(
        DRAFT_ARGS,
        anchors=[{"post": "le canal direct est le seul qui paie",
                  "said": "le canal direct est le seul qui paie"},
                 {"post": "Quatre mois pour rien.",
                  "said": "j'ai perdu quatre mois entiers"},
                 {"post": "une phrase absente du brouillon",
                  "said": "le canal direct est le seul qui paie"}]))),
               says("Written."))

    def test_the_three_states_are_all_on_the_screen(self):
        interview_id = self.signed()
        self.draft(interview_id)
        page = self.client.get(f"/interview/{interview_id}")
        self.assertEqual(page.status_code, 200)
        for state in ("anchored", "fabricated", "dangling"):
            self.assertIn(f"anchor-{state}", page.text, state)
        # And in the body itself: a claim backed by an invented quote is
        # marked there too, or the loudest alarm would show as clean text.
        self.assertIn("claim-fabricated", page.text)

    def test_two_claims_with_the_same_words_do_not_swap_verdicts(self):
        # The claim and its verdict are decided by two different functions.
        # This is the test that would catch them drifting out of step.
        interview_id = self.signed()
        self.draft(interview_id)
        conversation = interview.load(self.root, interview_id)
        from verbatim_app.routes.interview import panel
        painted = panel(conversation)
        by_text = {piece["text"]: piece["status"]
                   for row in painted["lines"] for piece in row}
        self.assertEqual(
            by_text["Quatre mois pour rien."], "fabricated")
        self.assertEqual(
            by_text["J'ai écrit pour des agences, et le canal direct est "
                    "le seul qui paie."], "anchored")

    def test_a_verdict_follows_the_transcript_rather_than_the_disk(self):
        interview_id = self.signed()
        self.draft(interview_id)
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["anchored", "fabricated", "dangling"])


class TestTheProfileBacksNothing(DraftCase):
    """A2 of the Alchie backlog, pinned before the sheet seam lands.

    The profile is legitimate input to a question and to an angle, and it is
    not evidence: a post that quotes it back proves only that the profile
    exists, and the person recognises their own words without noticing that
    nothing was verified. Here the quote is lifted from `examples/profile.md`
    word for word, and it comes back fabricated, because the transcript is
    the only thing a quote offered as something said is checked against.
    """

    LINE = "Fractional CFO work for seed and Series A B2B SaaS"

    scripts = (asks(("c1", "propose_draft", dict(
        DRAFT_ARGS,
        body=LINE + ".\n\n" + DRAFT_ARGS["body"],
        anchors=DRAFT_ARGS["anchors"] + [{"post": LINE, "said": LINE}]))),
               says("Written."))

    def test_the_quote_really_is_in_the_profile(self):
        # Or the test below would be passing on a typo.
        self.assertIn(self.LINE, (self.root / "profile.md")
                      .read_text(encoding="utf-8"))

    def test_it_comes_back_fabricated_on_the_screen(self):
        interview_id = self.signed()
        self.draft(interview_id)
        conversation = interview.load(self.root, interview_id)
        self.assertNotIn("Fractional", conversation.said())
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["anchored", "fabricated"])
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn("anchor-fabricated", page.text)
        self.assertIn("claim-fabricated", page.text)


class TestTheWordingFollowsTheProvenance(DraftCase):
    """A3 of the Alchie backlog: the words shown over a backing are computed
    from where it lives, never a fixed string in a template.

    "You said" is true over a transcript quote and false over every other
    one, and a template printing it regardless would one day print it over a
    sentence nobody uttered, looking exactly like a quotation. Written red,
    before the sheet seam existed, so that the seam could not land half way:
    a parse that accepted `sheet` while the screen still said "you said"
    would be precisely the mislabelling `references/anchoring.md` exists to
    prevent.
    """

    scripts = (asks(("c1", "propose_draft", dict(
        DRAFT_ARGS,
        # The second backing is a first line of the approved sheet, which
        # the person never typed: a quote of it offered as something said
        # would be fabricated, and offered as a line of the sheet it holds.
        anchors=DRAFT_ARGS["anchors"] + [
            {"post": "Quatre mois pour rien.",
             "sheet": "Quatre mois pour rien."}]))),
               says("Written."))

    def entries(self, interview_id):
        """The panel's entries, keyed by the provenance each one wears."""
        page = self.client.get(f"/interview/{interview_id}")
        self.assertEqual(page.status_code, 200)
        found = {}
        for chunk in page.text.split('<li class="anchor ')[1:]:
            body = chunk.split("</li>", 1)[0]
            worn = re.search(r"anchor-of-([a-z]+)", body)
            self.assertIsNotNone(worn, "an entry that names no provenance")
            found[worn.group(1)] = body
        return found

    def test_both_backings_land_and_both_are_anchored(self):
        interview_id = self.signed()
        self.draft(interview_id)
        verdicts = interview.checked(interview.load(self.root, interview_id))
        self.assertEqual([verdict.status for verdict in verdicts],
                         ["anchored", "anchored"])
        self.assertEqual([verdict.anchor.provenance for verdict in verdicts],
                         ["transcript", "sheet"])

    def test_a_transcript_backing_is_worded_as_something_said(self):
        from verbatim_app.i18n import load_strings
        strings = load_strings("en")
        interview_id = self.signed()
        self.draft(interview_id)
        entry = self.entries(interview_id)["transcript"]
        self.assertIn(shown(strings("interview.trace_transcript")), entry)
        self.assertIn(shown(strings("interview.anchor_anchored_transcript_hint")),
                      entry)

    def test_a_sheet_backing_is_never_worded_as_something_said(self):
        from verbatim_app.i18n import load_strings
        strings = load_strings("en")
        interview_id = self.signed()
        self.draft(interview_id)
        entry = self.entries(interview_id)["sheet"]
        self.assertIn(shown(strings("interview.trace_sheet")), entry)
        self.assertIn(shown(strings("interview.anchor_anchored_sheet_hint")),
                      entry)
        self.assertNotIn(shown(strings("interview.trace_transcript")), entry)
        self.assertNotIn(
            shown(strings("interview.anchor_anchored_transcript_hint")), entry)

    def test_the_two_wordings_are_different_sentences_in_every_pack(self):
        # A pack translating the two keys to the same words would put the
        # transcript's sentence back over the sheet, in that language only.
        from verbatim_app.i18n import load_strings
        for lang in ("en", "fr"):
            strings = load_strings(lang)
            for transcript, sheet in (
                    ("trace_transcript", "trace_sheet"),
                    ("anchor_anchored_transcript_hint",
                     "anchor_anchored_sheet_hint"),
                    ("anchor_fabricated_transcript_hint",
                     "anchor_fabricated_sheet_hint")):
                self.assertNotEqual(strings("interview." + transcript),
                                    strings("interview." + sheet), lang)


class TestTheInlineLintPass(DraftCase):
    scripts = (asks(("c1", "propose_draft", dict(
        DRAFT_ARGS, body="Quatre mois pour rien - et rien d'autre."))),
               says("Written."))

    def test_the_findings_come_back_on_the_screen(self):
        interview_id = self.signed()
        self.draft(interview_id)
        page = self.client.post(f"/interview/{interview_id}/draft/lint")
        self.assertEqual(page.status_code, 200)
        self.assertIn("lint-findings", page.text)

    def test_a_lint_that_will_not_run_says_so_in_the_pack_first(self):
        # The refusal comes back from a tool, written for a model, in English.
        # On a screen it needs the pack to say what kind of thing it is.
        interview_id = self.signed()
        self.draft(interview_id)
        conversation = interview.load(self.root, interview_id)
        conversation.output_language = "zz"
        interview.save(self.root, conversation)
        page = self.client.post(f"/interview/{interview_id}/draft/lint")
        self.assertEqual(page.status_code, 200)
        self.assertIn("did not run", page.text)
        self.assertIn("zz", page.text)

    def test_there_is_nothing_to_lint_without_a_draft(self):
        interview_id = self.signed()
        reply = self.client.post(f"/interview/{interview_id}/draft/lint",
                                 follow_redirects=False)
        self.assertEqual(reply.status_code, 303)


class TestTheRevisionRequest(DraftCase):
    """What somebody types to steer a rewrite. Kept, and kept on the Said
    side: `references/instance.md` says why, and the screen says so too."""

    scripts = (asks(("c1", "propose_draft", dict(DRAFT_ARGS,
                                                 body="Autre chose."))),
               says("done"))

    def test_the_request_reaches_disk_before_a_token_is_spent(self):
        interview_id = self.drafted()
        body = self.draft(interview_id, "Ouvre sur le chiffre.").text
        order = kinds(body)
        conversation = interview.load(self.root, interview_id)
        self.assertEqual([r.text for r in conversation.revisions],
                         ["Ouvre sur le chiffre."])
        # `accepted` is the seam: before it nothing was written, after it the
        # words are on disk whatever the turn does next.
        self.assertEqual(order[0], "accepted")

    def test_it_is_not_written_into_the_interview_message_list(self):
        # That list is the anchoring source. A message the engine appended
        # would be a quote the engine could forge.
        interview_id = self.drafted()
        before = interview.load(self.root, interview_id).messages
        self.draft(interview_id, "Plus court.")
        after = interview.load(self.root, interview_id)
        self.assertEqual(after.messages, before)
        self.assertEqual(after.person_turns(), [
            "le canal direct est le seul qui paie, j'ai arrêté les agences"])

    def test_it_counts_as_something_said(self):
        interview_id = self.drafted()
        self.draft(interview_id, "c'était quarante, pas trente")
        conversation = interview.load(self.root, interview_id)
        self.assertIn("c'était quarante, pas trente", conversation.said())

    def test_a_request_with_no_draft_to_revise_is_refused(self):
        interview_id = self.signed()
        reply = self.draft(interview_id, "Ouvre sur le chiffre.")
        self.assertEqual(reply.status_code, 409)
        self.assertEqual(reply.json()["detail"], "nothing-to-revise")
        self.assertEqual(interview.load(self.root, interview_id).revisions, [])

    def test_an_empty_request_is_a_plain_rewrite(self):
        interview_id = self.drafted()
        self.draft(interview_id, "   ")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.revisions, [])
        self.assertEqual(conversation.draft.body, "Autre chose.")

    def test_the_turn_reads_the_skill_rule_a_rewrite_forgets(self):
        # Wired here as well as unit tested, because the wiring is the half
        # that goes wrong: a section list computed correctly and then not
        # passed is a guard nobody sends.
        interview_id = self.drafted()
        self.draft(interview_id, "Ouvre sur le chiffre.")
        sent = self.transport.calls[0]["payload"]["system"]
        self.assertIn("A revision can reintroduce an invented detail", sent)

    def test_a_first_draft_is_not_handed_the_revision_vocabulary(self):
        self.draft(self.signed())
        sent = self.transport.calls[0]["payload"]["system"]
        self.assertNotIn("A revision can reintroduce an invented detail", sent)

    def test_the_screen_shows_what_was_asked_for(self):
        interview_id = self.drafted()
        self.draft(interview_id, "Ouvre sur le chiffre.")
        page = self.client.get(f"/interview/{interview_id}")
        self.assertIn("Ouvre sur le chiffre.", page.text)


class TestTheRevisionUnderTheLock(DraftCase):
    """The handler refuses what a status code can refuse; the generator
    re-checks under the lock, because the copy the handler read is only as
    fresh as losing the race left it."""

    def test_a_draft_that_vanished_between_the_two_is_a_frame(self):
        from verbatim_app.routes.interview import _engine, _run, lock_for
        interview_id = self.drafted()
        request = Bare(self.app)
        # The draft goes away between the handler's read and the lock: another
        # tab, a hand edited file. The handler saw one and let the turn start.
        conversation = interview.load(self.root, interview_id)
        conversation.draft = None
        interview.save(self.root, conversation)
        sent = frames("".join(_run(request, _engine(request), interview_id,
                                   "Ouvre sur le chiffre.",
                                   lock_for(self.app, interview_id),
                                   require="propose_draft", drafting=True)))
        self.assertEqual([frame["kind"] for frame in sent], ["error"])
        self.assertEqual(sent[0]["code"], "nothing-to-revise")
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(interview.load(self.root, interview_id).revisions, [])


class ArchiveCase(DraftCase):
    def filing(self, **kwargs):
        fields = dict(date="2026-08-29", slug="agences-quatre-mois",
                      pillar="3", format="the-post-mortem",
                      label="VISIBILITY", state="draft", idea="")
        fields.update(kwargs)
        return fields

    def file_it(self, interview_id, **kwargs):
        return self.client.post(f"/interview/{interview_id}/archive",
                                data=self.filing(**kwargs),
                                follow_redirects=False)


class TestArchiving(ArchiveCase):
    """The step the skill says decides whether any of this was worth doing."""

    def test_the_post_is_filed_and_the_interview_closes_on_its_name(self):
        interview_id = self.drafted()
        reply = self.file_it(interview_id)
        self.assertEqual(reply.status_code, 303)
        self.assertEqual(reply.headers["location"],
                         "/posts/2026-08-29-agences-quatre-mois.md")
        conversation = interview.load(self.root, interview_id)
        self.assertEqual(conversation.state, interview.CLOSED)
        self.assertEqual(conversation.post,
                         "posts/2026-08-29-agences-quatre-mois.md")
        self.assertTrue(
            (self.root / "posts"
             / "2026-08-29-agences-quatre-mois.md").is_file())

    def test_the_filed_post_shows_up_on_the_posts_screen(self):
        self.file_it(self.drafted())
        self.assertIn("agences-quatre-mois", self.client.get("/posts").text)

    def test_a_filing_this_engine_cannot_read_back_comes_back_as_a_screen(self):
        interview_id = self.drafted()
        for wrong, sentence in (({"slug": "Not A Slug"}, "archive_bad_slug"),
                                ({"date": "today"}, "archive_bad_date"),
                                ({"pillar": "9"}, "archive_bad_pillar"),
                                ({"format": "the-listicle"},
                                 "archive_bad_format"),
                                ({"label": "AWARENESS"}, "archive_bad_label"),
                                ({"state": "posted"}, "archive_bad_state")):
            page = self.file_it(interview_id, **wrong)
            self.assertEqual(page.status_code, 200, wrong)
            self.assertIn(shown(self.app.state.t("interview." + sentence)),
                          page.text)
        self.assertEqual(
            interview.load(self.root, interview_id).state, interview.OPEN)
        self.assertEqual(
            list((self.root / "posts").glob("2026-08-29-agences-*")), [])

    def test_a_name_already_taken_stops_the_step(self):
        interview_id = self.drafted()
        (self.root / "posts" / "2026-08-29-agences-quatre-mois.md").write_text(
            "not this one", encoding="utf-8")
        page = self.file_it(interview_id)
        self.assertIn(shown(self.app.state.t("interview.archive_name_taken")),
                      page.text)
        self.assertEqual(
            interview.load(self.root, interview_id).state, interview.OPEN)

    def test_archiving_twice_is_refused(self):
        interview_id = self.drafted()
        self.file_it(interview_id)
        page = self.file_it(interview_id, slug="autre-chose")
        self.assertIn(shown(self.app.state.t("interview.archive_already_closed")),
                      page.text)

    def test_a_profile_without_a_signature_block_is_a_repair(self):
        interview_id = self.drafted()
        text = (self.root / "profile.md").read_text(encoding="utf-8")
        (self.root / "profile.md").write_text(
            text.replace("## Signature block", "## Gone"), encoding="utf-8")
        page = self.file_it(interview_id)
        self.assertIn(shown(self.app.state.t("interview.archive_signature_missing")),
                      page.text)
        self.assertEqual(
            list((self.root / "posts").glob("2026-08-29-agences-*")), [])

    def test_the_consumed_angle_moves_into_used(self):
        interview_id = self.drafted()
        from verbatim_app.instance import Instance
        instance = Instance(self.root)
        angle = instance.ideas().angles[0]
        self.file_it(interview_id, idea=angle.text)
        bank = instance.ideas()
        self.assertNotIn(angle.text, [a.text for a in bank.angles])
        self.assertEqual(bank.used[-1].file,
                         "posts/2026-08-29-agences-quatre-mois.md")

    def test_a_running_turn_takes_the_lock_and_nothing_is_filed(self):
        interview_id = self.drafted()
        lock = self.app.state.locks[interview_id] \
            if hasattr(self.app.state, "locks") else None
        from verbatim_app.routes.interview import lock_for
        held = lock_for(self.app, interview_id)
        held.acquire()
        try:
            reply = self.file_it(interview_id)
        finally:
            held.release()
        self.assertEqual(reply.status_code, 303)
        self.assertIn("notice=turn-running", reply.headers["location"])
        self.assertEqual(
            interview.load(self.root, interview_id).state, interview.OPEN)


class TestWhatTheSessionLeavesBeside(DraftCase):
    """The photo ideas and the tips. Beside the post, never in it, and what
    did not arrive is shown as missing rather than left out."""

    def test_what_arrived_is_on_the_screen_and_not_in_the_post(self):
        interview_id = self.signed()
        conversation = interview.load(self.root, interview_id)
        interview.write(conversation, dict(
            DRAFT_ARGS,
            photos=[{"kind": "portrait", "text": "Devant le tableau."}],
            tips=[{"kind": "lesson", "text": "Ouvrir sur le chiffre."}]))
        interview.save(self.root, conversation)
        page = self.client.get(f"/interview/{interview_id}").text
        self.assertIn("Devant le tableau.", page)
        self.assertIn("Ouvrir sur le chiffre.", page)
        post = page.split('class="notes"')[0]
        self.assertNotIn("Devant le tableau.", post)

    def test_every_kind_the_skill_asks_for_is_labelled_present_or_not(self):
        page = self.client.get(f"/interview/{self.drafted()}").text
        strings = self.app.state.t
        for kind in interview.PHOTO_KINDS + interview.TIP_KINDS:
            self.assertIn(shown(strings("interview.note_" + kind)), page, kind)
        self.assertEqual(page.count(shown(strings("interview.note_missing"))),
                         len(interview.PHOTO_KINDS) + len(interview.TIP_KINDS))


class TestEveryArchiveCodeHasASentence(ArchiveCase):
    """A code the pack does not name renders as the key, in the middle of a
    callout. Read out of the module rather than listed by hand, so a refusal
    added without a sentence fails here instead of on somebody's screen."""

    #: Raised by the route rather than by `archive`, and mapped from the two
    #: instance failures the step can meet.
    FROM_THE_ROUTE = ("signature-missing", "instance-unreadable")

    def codes(self):
        source = (REPO / "app" / "verbatim_app" / "archive.py").read_text(
            encoding="utf-8")
        return set(re.findall(r'ArchiveError\("([a-z-]+)"', source)) \
            | set(self.FROM_THE_ROUTE)

    def test_the_screen_has_a_sentence_for_every_one(self):
        strings = self.app.state.t
        found = self.codes()
        self.assertTrue(found)
        for code in sorted(found):
            key = "interview.archive_" + code.replace("-", "_")
            self.assertNotEqual(strings(key), key, code)

    def test_the_french_pack_has_them_too(self):
        from verbatim_app.i18n import load_strings
        strings = load_strings("fr")
        self.assertEqual(strings.missing, ())
        for code in sorted(self.codes()):
            key = "interview.archive_" + code.replace("-", "_")
            self.assertNotEqual(strings(key), key, code)


PROSE_SHEET = """Bien sûr, voici la fiche de validation.

ANGLE
Le segment abandonné, avec ce qu'il a coûté

CONCRETE ELEMENTS
- onze conversations
- deux propositions

THE STRONG MOMENT
rien de signé au bout de quatre mois

CENTRAL CONVICTION
"le canal direct est le seul qui paie"

FIRST LINE
- Quatre mois à vendre aux agences.
"""


class TestATurnWhoseToolDidFire(SheetCase):
    """The other half of the fallback, and the one that fails quietly. If the
    engine decided "was it called" by looking at the conversation instead of
    at the loop, a turn that called the tool would still be parsed for prose,
    find none, and tell somebody nothing was read while their sheet sits on
    the screen."""

    scripts = (asks(("c1", "propose_sheet", SHEET_ARGS)), says("voilà"),
               asks(("c2", "propose_draft", DRAFT_ARGS)), says("voilà"))

    def test_no_refusal_follows_a_sheet_that_landed(self):
        interview_id = self.open_interview()
        interview.say(conversation := interview.load(self.root, interview_id),
                      "quatre mois sur les agences")
        interview.save(self.root, conversation)
        reply = self.client.post(f"/interview/{interview_id}/sheet/propose")
        sent = frames(reply.text)
        self.assertIn("sheet", [f["kind"] for f in sent])
        self.assertEqual([f for f in sent if f["kind"] == "error"], [])
        self.assertEqual(interview.load(self.root, interview_id).sheet.problems,
                         ())

    def test_no_refusal_follows_a_draft_that_landed(self):
        interview_id = self.open_interview()
        conversation = interview.load(self.root, interview_id)
        interview.say(conversation, "le canal direct est le seul qui paie")
        interview.propose(conversation, dict(SHEET_ARGS))
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0)
        interview.save(self.root, conversation)
        self.transport.scripts = self.transport.scripts[2:]
        reply = self.client.post(f"/interview/{interview_id}/draft",
                                 data={"text": ""})
        sent = frames(reply.text)
        self.assertIn("draft", [f["kind"] for f in sent])
        self.assertEqual([f for f in sent if f["kind"] == "error"], [])
        self.assertEqual(interview.load(self.root, interview_id).draft.problems,
                         ())


class TestARuntimeThatIgnoresTheSheetTool(SheetCase):
    """`tool_choice` is enforced by the provider on the native wire and
    advisory on an OpenAI compatible one: two calls in six on Ollama, see
    docs/smoke.md. Without this path the sheet guard fires on hosted models
    and quietly does not on local ones."""

    scripts = (says("Une question de plus, d'abord."), says(PROSE_SHEET),
               says("Une question de plus, d'abord."), says(PROSE_SHEET),
               says("Une question de plus, d'abord."), says(PROSE_SHEET))

    def test_the_sheet_is_read_out_of_the_prose(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "quatre mois sur les agences")
        reply = self.client.post(f"/interview/{interview_id}/sheet/propose")
        sheet = interview.load(self.root, interview_id).sheet
        self.assertIsNotNone(sheet)
        self.assertEqual(sheet.angle,
                         "Le segment abandonné, avec ce qu'il a coûté")
        self.assertEqual(sheet.elements,
                         ("onze conversations", "deux propositions"))
        self.assertEqual(sheet.conviction,
                         "le canal direct est le seul qui paie")
        self.assertIn("sheet", kinds(reply.text))

    def test_the_screen_says_it_was_parsed_rather_than_offered(self):
        # A sheet read out of free text is the weaker object, and the person
        # signing it decides with that in front of them or not at all.
        interview_id = self.open_interview()
        self.turn(interview_id, "quatre mois sur les agences")
        self.client.post(f"/interview/{interview_id}/sheet/propose")
        sheet = interview.load(self.root, interview_id).sheet
        # The marker is on even though this one parsed cleanly: the road it
        # came down is a fact of its own.
        self.assertIn("propose_sheet was required and was not called",
                      " ".join(sheet.problems))
        page = self.client.get(f"/interview/{interview_id}").text
        self.assertIn(shown(self.app.state.t("interview.sheet_problems_hint")),
                      page)

    def test_it_can_still_be_approved_and_still_guards_the_draft(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "quatre mois sur les agences")
        self.client.post(f"/interview/{interview_id}/sheet/propose")
        self.approve(interview_id)
        self.assertTrue(
            interview.sheet_approved(interview.load(self.root, interview_id)))


class TestAnAnswerThatIsNotASheetAtAll(SheetCase):
    """Refusing to guess is the point. A field invented here to get past the
    refusal is the invention the sheet exists to catch."""

    scripts = (says("Une question de plus, d'abord."),
               says("Bien sûr, je peux préparer cela. Dites-moi quand."))

    def test_nothing_lands_and_the_screen_is_told_why(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "quatre mois sur les agences")
        reply = self.client.post(f"/interview/{interview_id}/sheet/propose")
        self.assertIsNone(interview.load(self.root, interview_id).sheet)
        sent = frames(reply.text)
        self.assertEqual(sent[-1]["kind"], "error")
        self.assertEqual(sent[-1]["code"], "sheet-not-read")


class TestAPartialSheetInProse(SheetCase):
    scripts = (says("Une question de plus, d'abord."),
               says(PROSE_SHEET.replace(
                   'CENTRAL CONVICTION\n"le canal direct est le seul qui '
                   'paie"\n', "")))

    def test_a_missing_field_takes_the_whole_sheet_with_it(self):
        interview_id = self.open_interview()
        self.turn(interview_id, "quatre mois sur les agences")
        reply = self.client.post(f"/interview/{interview_id}/sheet/propose")
        self.assertIsNone(interview.load(self.root, interview_id).sheet)
        self.assertEqual(frames(reply.text)[-1]["code"], "sheet-not-read")


class TestARewriteWhoseToolIsIgnored(DraftCase):
    """The bug the `fired` set fixes. The old reading asked whether a draft
    existed, and on a rewrite one always does, so the fallback never ran on
    the turn that needs it most and the prose went into silence."""

    scripts = (says("Voici le post.\n\nQuatre mois pour rien.\n\n"
                    "ANCHORS\nPOST: Quatre mois pour rien.\n"
                    "SAID: le canal direct est le seul qui paie\n"),)

    def test_the_prose_still_becomes_the_new_draft(self):
        interview_id = self.drafted()
        before = interview.load(self.root, interview_id).draft.body
        self.draft(interview_id)
        after = interview.load(self.root, interview_id).draft
        self.assertNotEqual(after.body, before)
        self.assertIn("Quatre mois pour rien.", after.body)


class TestADraftTurnThatReturnsNothingUsable(DraftCase):
    scripts = (says("Je préfère poser une question de plus avant d'écrire."),)

    def test_nothing_lands_and_the_screen_is_told_why(self):
        interview_id = self.signed()
        reply = self.draft(interview_id)
        self.assertIsNone(interview.load(self.root, interview_id).draft)
        self.assertEqual(frames(reply.text)[-1]["code"], "draft-not-read")


class TestArchivingInFrench(ArchiveCase):
    lang = "fr"

    def test_no_english_reaches_the_screen(self):
        page = self.client.get(f"/interview/{self.drafted()}")
        self.assertIn(shown(self.app.state.t("interview.archive_hint")), page.text)
        self.assertNotIn("Archive this post", page.text)



if __name__ == "__main__":
    unittest.main(verbosity=2)
