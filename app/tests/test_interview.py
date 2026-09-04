"""Tests for the interview store: where a conversation lives between turns.

Nothing here opens a socket or needs a key. The subject is the disk format
`references/instance.md` gained for this slice, and the property that makes it
worth having: what is on disk after any step is a conversation a provider
would still accept.

    python3 app/tests/test_interview.py
"""

import json
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app import interview, passages  # noqa: E402
from verbatim_app.shown import shown  # noqa: E402
from verbatim_app.anchors import Anchor  # noqa: E402
from verbatim_app.providers import Usage  # noqa: E402
from verbatim_app.skills import system_block  # noqa: E402

WHEN = datetime(2026, 8, 28, 14, 32, 11)
LATER = datetime(2026, 8, 28, 14, 41, 2)


def started(root, **kwargs):
    fields = dict(skill="linkedin-post", sections=("The interview",),
                  interface_language="fr", output_language="fr",
                  provider="anthropic", model="claude-opus-5", now=WHEN)
    fields.update(kwargs)
    return interview.start(root, **fields)


def assistant(text="", calls=()):
    blocks = [{"type": "text", "text": text}] if text else []
    for call_id, name, arguments in calls:
        blocks.append({"type": "tool_use", "id": call_id, "name": name,
                       "input": arguments})
    return {"role": "assistant", "content": blocks}


def results(*pairs):
    return {"role": "user",
            "content": [{"type": "tool_result", "tool_use_id": call_id,
                         "content": text, "is_error": False}
                        for call_id, text in pairs]}


class InterviewCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-interview-")
        self.root = Path(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def directory(self, conversation):
        return self.root / interview.DIRECTORY / conversation.id


class TestStarting(InterviewCase):
    def test_the_id_is_the_minute_it_started(self):
        self.assertEqual(started(self.root).id, "2026-08-28-1432")

    def test_both_files_land_on_disk(self):
        here = self.directory(started(self.root))
        self.assertTrue((here / interview.CONVERSATION).is_file())
        self.assertTrue((here / interview.TRANSCRIPT).is_file())

    def test_a_second_interview_in_the_same_minute_is_suffixed(self):
        first = started(self.root)
        second = started(self.root)
        self.assertEqual(first.id, "2026-08-28-1432")
        self.assertEqual(second.id, "2026-08-28-1432-2")
        self.assertEqual(started(self.root).id, "2026-08-28-1432-3")

    def test_a_fresh_interview_is_open_and_empty(self):
        conversation = started(self.root)
        self.assertEqual(conversation.state, "open")
        self.assertEqual(conversation.messages, [])
        self.assertEqual(conversation.usage, Usage())
        self.assertEqual(conversation.post, "")

    def test_the_settings_that_rebuild_the_block_are_kept(self):
        conversation = started(self.root, interface_language="fr",
                               output_language="en",
                               sections=("Before anything", "The interview"))
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.interface_language, "fr")
        self.assertEqual(again.output_language, "en")
        self.assertEqual(again.skill, "linkedin-post")
        self.assertEqual(again.sections,
                         ("Before anything", "The interview"))

    def test_the_system_block_itself_is_not_stored(self):
        # It is rebuilt from the bundle every turn, so a bundle that gains a
        # correction reaches an interview already under way.
        raw = json.loads((self.directory(started(self.root))
                          / interview.CONVERSATION).read_text(encoding="utf-8"))
        self.assertNotIn("system", raw)

    def test_the_file_carries_a_format_version(self):
        raw = json.loads((self.directory(started(self.root))
                          / interview.CONVERSATION).read_text(encoding="utf-8"))
        self.assertEqual(raw["version"], interview.VERSION)


class TestSayingAndSaving(InterviewCase):
    def test_saying_appends_one_user_message(self):
        conversation = started(self.root)
        interview.say(conversation, "J'ai passé quatre mois sur les agences.")
        self.assertEqual(conversation.messages, [
            {"role": "user",
             "content": [{"type": "text",
                          "text": "J'ai passé quatre mois sur les agences."}]},
        ])

    def test_an_empty_answer_is_refused(self):
        conversation = started(self.root)
        with self.assertRaises(interview.InterviewError):
            interview.say(conversation, "   \n ")

    def test_a_saved_conversation_reloads_identical(self):
        conversation = started(self.root)
        interview.say(conversation, "Les agences.")
        conversation.messages.append(
            assistant("Quelle agence, et quand ?",
                      calls=[("toolu_01", "read_instance", {"path": "voice.md"})]))
        conversation.messages.append(results(("toolu_01", "traits...")))
        conversation.usage = Usage(1200, 340)
        interview.save(self.root, conversation, now=LATER)

        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.messages, conversation.messages)
        self.assertEqual(again.usage, Usage(1200, 340))
        self.assertEqual(again.updated, "2026-08-28T14:41:02")
        self.assertEqual(again.started, "2026-08-28T14:32:11")

    def test_a_tool_call_id_survives_the_round_trip(self):
        # The whole reason this file is JSON: a conversation whose tool_use id
        # does not come back is a conversation the provider rejects.
        conversation = started(self.root)
        conversation.messages.append(
            assistant(calls=[("toolu_ZW5jb2Rl", "read_instance", {"path": "ideas.md"})]))
        interview.save(self.root, conversation, now=LATER)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.messages[0]["content"][0]["id"], "toolu_ZW5jb2Rl")

    def test_a_conversation_stopped_mid_turn_is_still_valid(self):
        # The loop appends the results message already answered, so this is
        # the shape on disk when somebody closes the browser mid tool call.
        conversation = started(self.root)
        interview.say(conversation, "Les agences.")
        conversation.messages.append(
            assistant(calls=[("toolu_01", "read_instance", {"path": "voice.md"})]))
        conversation.messages.append(
            {"role": "user",
             "content": [{"type": "tool_result", "tool_use_id": "toolu_01",
                          "content": "not run", "is_error": True}]})
        interview.save(self.root, conversation, now=LATER)

        again = interview.load(self.root, conversation.id)
        asked = [block["id"] for message in again.messages
                 if message["role"] == "assistant"
                 for block in message["content"] if block["type"] == "tool_use"]
        answered = [block["tool_use_id"] for message in again.messages
                    if message["role"] == "user"
                    for block in message["content"]
                    if block.get("type") == "tool_result"]
        self.assertEqual(asked, answered)

    def test_a_broken_conversation_file_is_a_clear_error(self):
        conversation = started(self.root)
        (self.directory(conversation) / interview.CONVERSATION).write_text(
            "{ not json", encoding="utf-8")
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, conversation.id)

    def test_an_id_cannot_climb_out_of_the_directory(self):
        bad_ids = (
            "../../etc", "a/b", ".hidden", "..", "a\\b", "",
            "2026-08-28-1432\n",        # a trailing newline, which $ forgives
            "2026-08-28-1432\n../etc",  # and what that forgiveness buys
            "٢٠٢٦-٠٨-٢٨-١٤٣٢",           # Arabic-Indic digits, which \\d matches
            "2026-08-28-1432 ", " 2026-08-28-1432", "2026-08-28-143",
        )
        for bad in bad_ids:
            # `directory` is where the guard lives, and it is what has to
            # refuse: further down, a missing file refuses these anyway, so a
            # behavioural test alone would pass with the guard taken out.
            with self.assertRaises(interview.InterviewError, msg=repr(bad)):
                interview.directory(self.root, bad)
            with self.assertRaises(interview.InterviewError, msg=repr(bad)):
                interview.load(self.root, bad)
            with self.assertRaises(interview.InterviewError, msg=repr(bad)):
                interview.discard(self.root, bad)

    def test_the_ids_the_engine_writes_are_accepted(self):
        for good in ("2026-08-28-1432", "2026-08-28-1432-2", "1999-01-01-0000"):
            self.assertTrue(str(interview.directory(self.root, good))
                            .endswith(good), good)

    def test_a_conversation_from_another_format_version_is_refused(self):
        conversation = started(self.root)
        path = self.directory(conversation) / interview.CONVERSATION
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["version"] = interview.VERSION + 1
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(interview.InterviewError) as refusal:
            interview.load(self.root, conversation.id)
        self.assertIn(str(interview.VERSION), str(refusal.exception))

    def test_the_truth_is_written_before_its_rendering(self):
        # A process that dies between the two leaves the conversation current
        # and the transcript one turn stale, which the next save repairs. The
        # other order leaves a transcript claiming words the conversation
        # cannot answer for.
        from verbatim_app import instance as instance_module
        conversation = started(self.root)
        interview.say(conversation, "Quatre mois.")
        written = []
        original = instance_module.atomic_write

        def watching(path, text):
            written.append(Path(path).name)
            return original(path, text)

        interview.atomic_write = watching
        try:
            interview.save(self.root, conversation, now=LATER)
        finally:
            interview.atomic_write = original
        self.assertEqual(written,
                         [interview.CONVERSATION, interview.TRANSCRIPT])


class TestACorruptConversationFile(InterviewCase):
    """It parsed as JSON and then held the wrong shape.

    Refusing is right, and refusing with a traceback is not: the only screens
    that offer the discard button are the ones a traceback takes down, so a
    crash here leaves `rm -rf` in a terminal as somebody's only exit.
    """

    SHAPES = {
        "a word where a number belongs": {"spent": "beaucoup"},
        "a list where a map belongs": {"usage": ["a"]},
        "a word inside the token count": {"usage": {"input_tokens": "many"}},
        "a string where a message belongs": {"messages": ["nope"]},
        "a path where a skill name belongs": {"skill": "../../etc"},
        "a number where a list belongs": {"sections": 3},
        "a state nothing can read": {"state": 7},
        "a map where the messages belong": {"messages": {}},
        "an empty list where the token map belongs": {"usage": []},
    }

    def directory_of(self, interview_id):
        return self.root / interview.DIRECTORY / interview_id

    def corrupt(self, patch):
        conversation = started(self.root)
        path = self.directory(conversation) / interview.CONVERSATION
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.update(patch)
        path.write_text(json.dumps(raw), encoding="utf-8")
        return conversation.id

    def test_every_wrong_shape_is_refused_rather_than_raised_through(self):
        for name, patch in self.SHAPES.items():
            interview_id = self.corrupt(patch)
            with self.assertRaises(interview.InterviewError, msg=name):
                interview.load(self.root, interview_id)
            interview.discard(self.root, interview_id)

    def test_a_wrong_shape_still_lists_so_it_can_be_discarded(self):
        for name, patch in self.SHAPES.items():
            interview_id = self.corrupt(patch)
            entries = interview.listing(self.root)
            self.assertEqual(len(entries), 1, name)
            self.assertTrue(entries[0].unreadable, name)
            interview.discard(self.root, interview_id)

    #: The shapes that live one level inside a message, which is the level
    #: every reader walks and the level a top-level check cannot see.
    BLOCKS = {
        "a null where the text belongs":
            [{"role": "user", "content": [{"type": "text", "text": None}]}],
        "a number where the text belongs":
            [{"role": "user", "content": [{"type": "text", "text": 7}]}],
        "a list where the text belongs":
            [{"role": "user", "content": [{"type": "text", "text": ["a"]}]}],
        "a block that is not a map":
            [{"role": "user", "content": ["hello"]}],
        "a content that is neither text nor a list":
            [{"role": "user", "content": {"type": "text"}}],
        "a tool result holding a number":
            [{"role": "user", "content": [{"type": "tool_result",
                                           "tool_use_id": "t", "content": 7}]}],
        "a tool result whose parts are not maps":
            [{"role": "user", "content": [{"type": "tool_result",
                                           "tool_use_id": "t",
                                           "content": [None]}]}],
    }

    def test_a_wrongly_typed_block_is_refused_before_any_reader_walks_it(self):
        # `listing` reads every conversation to build its rows, so a block that
        # takes a reader down takes the screen down for every interview, and
        # that screen is the only one a corrupt interview can be discarded
        # from.
        for name, messages in self.BLOCKS.items():
            interview_id = self.corrupt({"messages": messages})
            with self.assertRaises(interview.InterviewError, msg=name):
                interview.load(self.root, interview_id)
            entries = interview.listing(self.root)
            self.assertTrue(entries[0].unreadable, name)
            interview.discard(self.root, interview_id)

    def test_bytes_that_are_not_text_are_refused_the_same_way(self):
        conversation = started(self.root)
        (self.directory(conversation) / interview.CONVERSATION).write_bytes(
            b'{"version": 1, \xff\xfe}')
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, conversation.id)
        self.assertTrue(interview.listing(self.root)[0].unreadable)

    def test_a_figure_that_is_not_a_figure_is_refused(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            interview_id = self.corrupt({})
            path = self.directory_of(interview_id) / interview.CONVERSATION
            path.write_text(
                path.read_text(encoding="utf-8").replace('"spent": 0.0',
                                                         f'"spent": {value}'),
                encoding="utf-8")
            with self.assertRaises(interview.InterviewError, msg=value):
                interview.load(self.root, interview_id)
            interview.discard(self.root, interview_id)

    def test_a_hand_written_string_turn_is_continued_not_doubled(self):
        # A shape this engine never writes, in a file people hand edit. The
        # invariant that matters is the one a provider enforces.
        conversation = started(self.root)
        conversation.messages.append({"role": "user", "content": "typed by hand"})
        interview.say(conversation, "and this too")
        self.assertEqual([m["role"] for m in conversation.messages], ["user"])
        self.assertEqual(conversation.said(), "typed by hand\n\nand this too")

    def test_a_file_that_is_not_even_an_object_is_refused(self):
        conversation = started(self.root)
        (self.directory(conversation) / interview.CONVERSATION).write_text(
            "[]", encoding="utf-8")
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, conversation.id)
        self.assertTrue(interview.listing(self.root)[0].unreadable)


class TestTranscript(InterviewCase):
    def rendered(self, conversation):
        return (self.directory(conversation)
                / interview.TRANSCRIPT).read_text(encoding="utf-8")

    def test_a_fresh_transcript_is_front_matter_and_a_title(self):
        text = self.rendered(started(self.root))
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("state: open", text)
        self.assertIn("interface_language: fr", text)
        self.assertNotIn("## Said", text)

    def test_the_two_sides_alternate_in_order(self):
        conversation = started(self.root)
        interview.say(conversation, "Les agences, quatre mois.")
        conversation.messages.append(assistant("Quelle agence, et quand ?"))
        interview.say(conversation, "Une agence de Lyon, en mars.")
        interview.save(self.root, conversation, now=LATER)

        body = self.rendered(conversation).split("---\n", 2)[2]
        self.assertEqual(
            [line for line in body.splitlines() if line.startswith("## ")],
            ["## Said", "## Asked", "## Said"])
        self.assertLess(body.index("Les agences, quatre mois."),
                        body.index("Quelle agence, et quand ?"))
        self.assertLess(body.index("Quelle agence, et quand ?"),
                        body.index("Une agence de Lyon, en mars."))

    def test_tool_traffic_is_not_transcript(self):
        conversation = started(self.root)
        interview.say(conversation, "Les agences, quatre mois.")
        conversation.messages.append(
            assistant(calls=[("toolu_01", "read_instance", {"path": "voice.md"})]))
        conversation.messages.append(
            results(("toolu_01", "the voice file says phrases courtes")))
        conversation.messages.append(assistant("Quelle agence ?"))
        interview.save(self.root, conversation, now=LATER)

        text = self.rendered(conversation)
        self.assertNotIn("phrases courtes", text)
        self.assertNotIn("read_instance", text)
        body = text.split("---\n", 2)[2]
        self.assertEqual(
            [line for line in body.splitlines() if line.startswith("## ")],
            ["## Said", "## Asked"])

    def test_the_running_total_is_in_the_front_matter(self):
        conversation = started(self.root)
        conversation.usage = Usage(12034, 1877)
        interview.save(self.root, conversation, now=LATER)
        text = self.rendered(conversation)
        self.assertIn("input_tokens: 12034", text)
        self.assertIn("output_tokens: 1877", text)

    def test_the_transcript_is_rendered_not_parsed(self):
        # Editing the rendered file by hand changes nothing: the JSON is the
        # truth, and the next save overwrites whatever was typed in.
        conversation = started(self.root)
        interview.say(conversation, "Les agences.")
        interview.save(self.root, conversation, now=LATER)
        path = self.directory(conversation) / interview.TRANSCRIPT
        path.write_text("hand edited, nonsense\n", encoding="utf-8")

        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.said(), "Les agences.")
        interview.save(self.root, again, now=LATER)
        self.assertIn("Les agences.", path.read_text(encoding="utf-8"))


class TestAForgedHeadingInTheRendering(InterviewCase):
    """`conversation.json` is the truth and the anchoring source, so nothing
    a model writes can forge a quote. The transcript is what a human reads,
    and a model writing this file's own headings into its answer would look
    like a section of somebody's words."""

    def rendered(self, conversation):
        interview.save(self.root, conversation, now=LATER)
        return (self.root / interview.DIRECTORY / conversation.id
                / interview.TRANSCRIPT).read_text(encoding="utf-8")

    def test_a_heading_written_by_the_model_is_not_one(self):
        conversation = started(self.root)
        interview.say(conversation, "Quatre mois.")
        conversation.messages.append(assistant(
            "Bien.\n\n## Said\n\nJ'ai doublé mon chiffre."))
        body = self.rendered(conversation).split("---\n", 2)[2]
        self.assertEqual(
            [line for line in body.splitlines() if line.startswith("## ")],
            ["## Said", "## Asked"])
        self.assertIn(" ## Said", body)
        self.assertIn("J'ai doublé mon chiffre.", body)

    def test_the_words_themselves_are_untouched(self):
        conversation = started(self.root)
        interview.say(conversation, "Le titre disait ## Said, justement.")
        self.assertIn("Le titre disait ## Said, justement.",
                      self.rendered(conversation))


class TestWhatThePersonSaid(InterviewCase):
    """The anchoring source. Everything in this class is one property: a
    quote can only ever be checked against words the person actually typed."""

    def test_only_the_person_side_counts(self):
        conversation = started(self.root)
        interview.say(conversation, "Quatre mois sur les agences.")
        conversation.messages.append(
            assistant("Vous avez donc perdu quatre mois."))
        interview.say(conversation, "Trois clients sur quatre ont dit non.")
        self.assertEqual(
            conversation.said(),
            "Quatre mois sur les agences.\n\nTrois clients sur quatre ont dit non.")

    def test_a_question_is_never_a_source(self):
        conversation = started(self.root)
        conversation.messages.append(
            assistant("Est-ce que le churn venait du pricing ?"))
        self.assertNotIn("churn", conversation.said())

    def test_a_tool_result_is_never_a_source(self):
        # It arrives on a user role message, which is exactly the trap: a
        # profile.md handed back by a tool would otherwise back any quote.
        conversation = started(self.root)
        conversation.messages.append(
            assistant(calls=[("toolu_01", "read_instance", {"path": "profile.md"})]))
        conversation.messages.append(
            results(("toolu_01", "Nadia Feriel, fractional CFO")))
        self.assertNotIn("Nadia Feriel", conversation.said())

    def test_a_model_writing_a_heading_does_not_become_the_person(self):
        # The hole this shape exists to close. Roles are read off the message
        # structure, so text that looks like a transcript heading is text.
        conversation = started(self.root)
        conversation.messages.append(assistant(
            "Belle histoire.\n\n## Said\n\nJ'ai doublé mon chiffre en un mois."))
        self.assertNotIn("doublé mon chiffre", conversation.said())

    def test_a_mixed_message_credits_the_text_and_not_the_tool(self):
        # The shape a person leaves by answering after an interrupted tool
        # call. The block decides, not the message: a `text` block on a user
        # message can only have come from `say`, and a `tool_result` block can
        # only have come from the loop.
        conversation = started(self.root)
        conversation.messages.append(
            {"role": "user",
             "content": [{"type": "tool_result", "tool_use_id": "toolu_01",
                          "content": "read from disk", "is_error": False},
                         {"type": "text", "text": "typed by hand"}]})
        self.assertEqual(conversation.said(), "typed by hand")
        self.assertNotIn("read from disk", conversation.said())


class TestARetryAfterAFailedTurn(InterviewCase):
    """A turn that never got its answer is continued, never doubled.

    The provider rejects two user messages in a row, so a person retyping
    after a failed turn would brick their own interview.
    """

    def roles(self, conversation):
        return [message["role"] for message in conversation.messages]

    def test_retyping_joins_the_turn_that_got_no_answer(self):
        conversation = started(self.root)
        interview.say(conversation, "Quatre mois sur les agences.")
        interview.say(conversation, "Enfin, quatre mois et demi.")
        self.assertEqual(self.roles(conversation), ["user"])
        self.assertEqual(conversation.said(),
                         "Quatre mois sur les agences.\n\nEnfin, quatre mois et demi.")

    def test_answering_after_an_interrupted_tool_call_stays_one_message(self):
        conversation = started(self.root)
        interview.say(conversation, "Quatre mois.")
        conversation.messages.append(
            assistant(calls=[("toolu_01", "read_instance", {"path": "voice.md"})]))
        conversation.messages.append(results(("toolu_01", "phrases courtes")))
        interview.say(conversation, "Une agence de Lyon.")

        self.assertEqual(self.roles(conversation), ["user", "assistant", "user"])
        self.assertEqual(conversation.said(), "Quatre mois.\n\nUne agence de Lyon.")
        self.assertNotIn("phrases courtes", conversation.said())
        # and the tool result still leads its own message, where a provider
        # expects it
        last = conversation.messages[-1]["content"]
        self.assertEqual([block["type"] for block in last],
                         ["tool_result", "text"])

    def test_no_sequence_of_turns_puts_two_user_messages_in_a_row(self):
        conversation = started(self.root)
        for round_number in range(4):
            interview.say(conversation, f"answer {round_number}")
            interview.say(conversation, f"and also {round_number}")
            conversation.messages.append(assistant(f"question {round_number}"))
        roles = self.roles(conversation)
        for one, two in zip(roles, roles[1:]):
            self.assertNotEqual(one, two, roles)


class TestTimeline(InterviewCase):
    """What a screen shows. Tool traffic is in it, on purpose: the brief for
    this screen is that the engine's reaching for files is visible, not
    tucked away."""

    def build(self):
        conversation = started(self.root)
        interview.say(conversation, "Quatre mois sur les agences.")
        conversation.messages.append(
            assistant("Je regarde la voix.",
                      calls=[("toolu_01", "read_instance", {"path": "voice.md"})]))
        conversation.messages.append(results(("toolu_01", "phrases courtes")))
        conversation.messages.append(assistant("Quelle agence ?"))
        return conversation

    def test_every_moment_is_there_in_order(self):
        moments = interview.timeline(self.build())
        self.assertEqual([moment.kind for moment in moments],
                         [interview.SAID, interview.ASKED, interview.CALL,
                          interview.RESULT, interview.ASKED])

    def test_a_call_carries_what_it_asked_for(self):
        call = [m for m in interview.timeline(self.build())
                if m.kind == interview.CALL][0]
        self.assertEqual(call.name, "read_instance")
        self.assertEqual(call.arguments, {"path": "voice.md"})
        self.assertEqual(call.call_id, "toolu_01")

    def test_a_result_carries_what_came_back(self):
        result = [m for m in interview.timeline(self.build())
                  if m.kind == interview.RESULT][0]
        self.assertEqual(result.text, "phrases courtes")
        self.assertFalse(result.is_error)
        self.assertEqual(result.call_id, "toolu_01")

    def test_a_failed_tool_says_so(self):
        conversation = started(self.root)
        conversation.messages.append(
            {"role": "user",
             "content": [{"type": "tool_result", "tool_use_id": "toolu_01",
                          "content": "no such file", "is_error": True}]})
        result = interview.timeline(conversation)[0]
        self.assertTrue(result.is_error)


class TestWhatATurnCost(InterviewCase):
    def test_the_running_cost_round_trips(self):
        conversation = started(self.root)
        conversation.spent = 0.0512
        interview.save(self.root, conversation, now=LATER)
        self.assertAlmostEqual(interview.load(self.root, conversation.id).spent,
                               0.0512)

    def test_an_unknown_cost_round_trips_as_unknown(self):
        conversation = started(self.root)
        conversation.spent = None
        interview.save(self.root, conversation, now=LATER)
        self.assertIsNone(interview.load(self.root, conversation.id).spent)
        text = (self.directory(conversation)
                / interview.TRANSCRIPT).read_text(encoding="utf-8")
        self.assertIn("\nspent:\n", text)


class TestListing(InterviewCase):
    def test_an_instance_without_the_directory_lists_nothing(self):
        self.assertEqual(interview.listing(self.root), [])

    def test_open_interviews_come_back_newest_first(self):
        first = started(self.root, now=datetime(2026, 8, 26, 9, 0, 0))
        second = started(self.root, now=datetime(2026, 8, 28, 14, 32, 11))
        self.assertEqual([entry.id for entry in interview.listing(self.root)],
                         [second.id, first.id])

    def test_an_entry_carries_what_a_screen_needs(self):
        conversation = started(self.root)
        interview.say(conversation, "Les agences, quatre mois.")
        interview.save(self.root, conversation, now=LATER)
        entry = interview.listing(self.root)[0]
        self.assertEqual(entry.state, "open")
        self.assertEqual(entry.updated, "2026-08-28T14:41:02")
        self.assertEqual(entry.turns, 1)
        self.assertEqual(entry.opening, "Les agences, quatre mois.")
        self.assertFalse(entry.unreadable)

    def test_an_unreadable_interview_still_shows_so_it_can_be_discarded(self):
        conversation = started(self.root)
        (self.directory(conversation) / interview.CONVERSATION).write_text(
            "{ not json", encoding="utf-8")
        entry = interview.listing(self.root)[0]
        self.assertTrue(entry.unreadable)
        self.assertEqual(entry.id, conversation.id)

    def test_a_stray_file_in_the_directory_is_ignored(self):
        started(self.root)
        (self.root / interview.DIRECTORY / ".DS_Store").write_text("", encoding="utf-8")
        self.assertEqual(len(interview.listing(self.root)), 1)


class TestPathDiscipline(InterviewCase):
    def test_the_interviews_directory_itself_is_never_a_link(self):
        outside = Path(self.tmp) / "elsewhere"
        (outside / "2026-01-01-0000").mkdir(parents=True)
        (outside / "keep.md").write_text("not yours", encoding="utf-8")
        (self.root / interview.DIRECTORY).symlink_to(outside)

        with self.assertRaises(interview.InterviewError):
            interview.listing(self.root)
        with self.assertRaises(interview.InterviewError):
            interview.discard(self.root, "2026-01-01-0000")
        self.assertTrue((outside / "keep.md").is_file())

    def test_a_linked_conversation_file_is_not_read_through(self):
        conversation = started(self.root)
        elsewhere = Path(self.tmp) / "other.json"
        elsewhere.write_text('{"version": 1, "messages": []}', encoding="utf-8")
        path = self.directory(conversation) / interview.CONVERSATION
        path.unlink()
        path.symlink_to(elsewhere)
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, conversation.id)

    def test_a_symlink_wearing_a_timestamp_is_not_an_interview(self):
        # The id pattern is satisfied and the link points anywhere. It matters
        # most on the way out: discard is an rmtree.
        outside = Path(self.tmp) / "elsewhere"
        outside.mkdir()
        (outside / "keep.md").write_text("not yours", encoding="utf-8")
        home = self.root / interview.DIRECTORY
        home.mkdir(parents=True, exist_ok=True)
        (home / "2026-01-01-0000").symlink_to(outside)

        # Listed, so it can be got rid of from a screen; unreadable, so
        # nothing reads through it; and discarding removes the link, never
        # what it points at.
        entries = interview.listing(self.root)
        self.assertEqual([entry.id for entry in entries], ["2026-01-01-0000"])
        self.assertTrue(entries[0].unreadable)
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, "2026-01-01-0000")

        interview.discard(self.root, "2026-01-01-0000")
        self.assertEqual(interview.listing(self.root), [])
        self.assertTrue((outside / "keep.md").is_file())
        self.assertTrue(outside.is_dir())


class TestWhoCanWriteTheAnchoringSource(InterviewCase):
    """`said()` credits a user role message that carries no tool_result, and a
    bare string counts. Nothing a model can reach writes one: `say()` and the
    loop's own results block are the only writers of a user message, and
    `write_instance` is gated on `instance.WRITABLE`, which does not include
    this directory. The rule is written down here so a future widening of
    what may write into an instance has to walk past it."""

    def test_a_hand_written_string_turn_counts_as_the_person(self):
        conversation = started(self.root)
        conversation.messages.append({"role": "user", "content": "typed by hand"})
        self.assertEqual(conversation.said(), "typed by hand")

    def test_a_hand_written_string_from_the_engine_does_not(self):
        conversation = started(self.root)
        conversation.messages.append({"role": "assistant", "content": "not mine"})
        self.assertEqual(conversation.said(), "")

    def test_the_writable_set_does_not_reach_this_directory(self):
        from verbatim_app.instance import WRITABLE
        self.assertNotIn(interview.DIRECTORY, WRITABLE)
        self.assertFalse([name for name in WRITABLE if "/" in name])


class TestEnding(InterviewCase):
    def test_closing_names_the_post_it_became(self):
        conversation = started(self.root)
        interview.close(self.root, conversation.id,
                        post="2026-08-28-agency-segment.md", now=LATER)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.state, "closed")
        self.assertEqual(again.post, "2026-08-28-agency-segment.md")
        text = (self.directory(conversation)
                / interview.TRANSCRIPT).read_text(encoding="utf-8")
        self.assertIn("state: closed", text)
        self.assertIn("post: 2026-08-28-agency-segment.md", text)

    def test_closing_keeps_the_words(self):
        conversation = started(self.root)
        interview.say(conversation, "Quatre mois sur les agences.")
        interview.save(self.root, conversation, now=LATER)
        interview.close(self.root, conversation.id, post="p.md", now=LATER)
        self.assertEqual(interview.load(self.root, conversation.id).said(),
                         "Quatre mois sur les agences.")

    def test_discarding_removes_the_directory_whole(self):
        conversation = started(self.root)
        interview.discard(self.root, conversation.id)
        self.assertFalse(self.directory(conversation).exists())
        self.assertEqual(interview.listing(self.root), [])

    def test_discarding_refuses_a_path_that_climbs_out(self):
        outside = self.root / "profile.md"
        outside.write_text("mine", encoding="utf-8")
        with self.assertRaises(interview.InterviewError):
            interview.discard(self.root, "../profile.md")
        self.assertTrue(outside.is_file())

    def test_discarding_something_that_is_not_there_says_so(self):
        with self.assertRaises(interview.InterviewError):
            interview.discard(self.root, "2026-01-01-0000")


class TestTheStep(InterviewCase):
    """The one place the app names a step of the skill. If a section is
    renamed in `skills/`, this fails here rather than at a person's first
    question."""

    def test_the_named_sections_exist_in_the_shipped_skill(self):
        block = system_block(REPO, interview.STEP_SKILL, "fr",
                             output_lang="en",
                             sections=interview.STEP_SECTIONS)
        self.assertIn("One question at a time", block.text)

    def test_the_step_carries_both_language_packs_when_they_differ(self):
        block = system_block(REPO, interview.STEP_SKILL, "fr",
                             output_lang="en",
                             sections=interview.STEP_SECTIONS)
        resolved = [citation.resolved for citation in block.citations]
        self.assertIn("locales/fr/interview.md", resolved)
        self.assertNotIn("locales/en/interview.md", resolved)


SHEET = {"angle": "Four months lost to agency work",
         "elements": ["four months on agencies", "two clients signed since"],
         "moment": "j'ai passé quatre mois à écrire pour des agences",
         "conviction": "le canal direct est le seul qui paie",
         "first_lines": ["Quatre mois pour rien.", "J'ai arrêté les agences."]}


def proposal(**kwargs):
    fields = dict(SHEET)
    fields.update(kwargs)
    return fields


class TestTheSheet(InterviewCase):
    """The validation sheet, `references/instance.md` under interviews/. The
    engine proposes, only the person approves, and the approved sheet is what
    stops the questions."""

    def test_a_proposal_lands_on_the_conversation(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal(), now=LATER)
        sheet = conversation.sheet
        self.assertEqual(sheet.state, "proposed")
        self.assertEqual(sheet.angle, SHEET["angle"])
        self.assertEqual(sheet.elements, tuple(SHEET["elements"]))
        self.assertEqual(sheet.moment, SHEET["moment"])
        self.assertEqual(sheet.conviction, SHEET["conviction"])
        self.assertEqual(sheet.first_lines, tuple(SHEET["first_lines"]))
        self.assertEqual(sheet.proposed, "2026-08-28T14:41:02")
        self.assertEqual(sheet.approved, "")

    def test_the_sheet_round_trips_through_the_disk(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal(), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.sheet, conversation.sheet)

    def test_no_sheet_means_no_key_on_disk(self):
        # The contract says absent until proposed, so an older reader sees a
        # file it already knows.
        conversation = started(self.root)
        raw = json.loads((self.directory(conversation)
                          / interview.CONVERSATION).read_text(encoding="utf-8"))
        self.assertNotIn("sheet", raw)

    def test_a_proposed_sheet_is_replaced_by_the_next_proposal(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal(), now=WHEN)
        interview.propose(conversation, proposal(angle="The direct channel"),
                          now=LATER)
        self.assertEqual(conversation.sheet.angle, "The direct channel")
        self.assertEqual(conversation.sheet.state, "proposed")

    def test_an_approved_sheet_cannot_be_replaced(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal(), now=WHEN)
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0, now=LATER)
        with self.assertRaisesRegex(interview.InterviewError, "frozen"):
            interview.propose(conversation, proposal(angle="Another one"))
        self.assertEqual(conversation.sheet.angle, SHEET["angle"])

    def test_a_closed_interview_takes_no_proposal(self):
        conversation = started(self.root)
        conversation.state = interview.CLOSED
        with self.assertRaises(interview.InterviewError):
            interview.propose(conversation, proposal())

    def test_every_field_is_required_and_non_empty(self):
        for name in ("angle", "moment", "conviction"):
            for wrong in ("", "   ", None, 3):
                conversation = started(self.root)
                with self.assertRaises(interview.InterviewError):
                    interview.propose(conversation,
                                      proposal(**{name: wrong}))
                self.assertIsNone(conversation.sheet, name)

    def test_the_lists_refuse_empties_and_non_lists(self):
        for name in ("elements", "first_lines"):
            for wrong in ([], ["ok", ""], ["ok", 3], "not a list", None):
                conversation = started(self.root)
                with self.assertRaises(interview.InterviewError):
                    interview.propose(conversation,
                                      proposal(**{name: wrong}))
                self.assertIsNone(conversation.sheet, name)

    def test_the_first_line_takes_two_proposals_at_most(self):
        # The skill says two proposals, or theirs. Three is a menu.
        conversation = started(self.root)
        with self.assertRaisesRegex(interview.InterviewError, "at most 2"):
            interview.propose(conversation,
                              proposal(first_lines=["a", "b", "c"]))

    def test_whitespace_is_trimmed_off_every_entry(self):
        conversation = started(self.root)
        interview.propose(conversation,
                          proposal(angle="  padded  ",
                                   elements=[" one ", "two"]))
        self.assertEqual(conversation.sheet.angle, "padded")
        self.assertEqual(conversation.sheet.elements, ("one", "two"))

    def test_how_a_sheet_arrived_travels_with_it(self):
        # The screen shows it: a sheet parsed out of free text is a weaker
        # object than one a model committed to through a tool.
        conversation = started(self.root)
        interview.propose(conversation, proposal(),
                          problems=["read out of prose"], now=WHEN)
        self.assertEqual(conversation.sheet.problems, ("read out of prose",))
        interview.save(self.root, conversation, now=WHEN)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.sheet, conversation.sheet)

    def test_a_model_cannot_write_the_problems_of_its_own_reception(self):
        conversation = started(self.root)
        interview.propose(conversation,
                          dict(proposal(), problems=["nothing went wrong"]),
                          now=WHEN)
        self.assertEqual(conversation.sheet.problems, ())

    def test_the_digest_does_not_move_with_how_it_arrived(self):
        # A signature is over what the sheet says, not over the road it came
        # down. Otherwise a digest would go stale on something invisible.
        one = started(self.root)
        interview.propose(one, proposal(), now=WHEN)
        two = started(self.root, now=LATER)
        interview.propose(two, proposal(), problems=["read out of prose"],
                          now=WHEN)
        self.assertEqual(one.sheet.digest(), two.sheet.digest())

    def test_a_mangled_problems_list_on_disk_is_refused(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal(), now=WHEN)
        interview.save(self.root, conversation, now=WHEN)
        path = self.directory(conversation) / interview.CONVERSATION
        for wrong in ("no", [3], {"a": 1}):
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["sheet"]["problems"] = wrong
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(interview.InterviewError):
                interview.load(self.root, conversation.id)

    def test_approving_freezes_and_stamps(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal(), now=WHEN)
        self.assertTrue(interview.approve(conversation,
                                          conversation.sheet.digest(),
                                          first_line=0, now=LATER))
        self.assertEqual(conversation.sheet.state, "approved")
        self.assertEqual(conversation.sheet.approved, "2026-08-28T14:41:02")
        self.assertTrue(interview.sheet_approved(conversation))

    def test_approving_twice_changes_nothing(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal(), now=WHEN)
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0, now=LATER)
        self.assertFalse(interview.approve(conversation,
                                           conversation.sheet.digest(),
                                           first_line=0,
                                           now=datetime(2026, 8, 28, 15, 0)))
        self.assertEqual(conversation.sheet.approved, "2026-08-28T14:41:02")

    def test_an_approval_signs_the_sheet_it_was_read_from(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal(), now=WHEN)
        stale = conversation.sheet.digest()
        interview.propose(conversation, proposal(angle="Another angle"),
                          now=LATER)
        with self.assertRaises(interview.SheetChanged):
            interview.approve(conversation, stale)
        self.assertEqual(conversation.sheet.state, "proposed")

    def test_the_digest_is_the_content_and_nothing_else(self):
        # Two proposals with the same five fields are the same decision,
        # whatever the timestamps say; one changed word is another sheet.
        one = started(self.root)
        interview.propose(one, proposal(), now=WHEN)
        two = started(self.root)
        interview.propose(two, proposal(), now=LATER)
        self.assertEqual(one.sheet.digest(), two.sheet.digest())
        interview.propose(two, proposal(conviction="something else"),
                          now=LATER)
        self.assertNotEqual(one.sheet.digest(), two.sheet.digest())

    def test_there_is_nothing_to_approve_before_a_proposal(self):
        conversation = started(self.root)
        with self.assertRaisesRegex(interview.InterviewError, "no sheet"):
            interview.approve(conversation, "")

    def test_a_closed_interview_takes_no_approval(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal())
        digest = conversation.sheet.digest()
        conversation.state = interview.CLOSED
        with self.assertRaises(interview.InterviewError):
            interview.approve(conversation, digest)

    def test_no_sheet_is_not_approved(self):
        self.assertFalse(interview.sheet_approved(started(self.root)))

    def test_a_proposed_sheet_is_not_approved(self):
        conversation = started(self.root)
        interview.propose(conversation, proposal())
        self.assertFalse(interview.sheet_approved(conversation))



class TestTheFirstLineIsDecided(InterviewCase):
    """F1. The sheet proposes one or two first lines and nothing recorded
    which one was taken.

    The skill already says the post is written for the chosen proposal, to
    the character. Nobody was ever asked, so nothing was ever chosen, and
    what the model does with no decision is write a lukewarm self
    description over two proposals that were better. The step existed and
    was invisible; this makes it a decision that has to be made.
    """

    def sheet(self, **kwargs):
        conversation = started(self.root)
        interview.propose(conversation, proposal(**kwargs), now=WHEN)
        return conversation

    def test_approving_records_which_line_was_taken(self):
        conversation = self.sheet()
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=1, now=LATER)
        self.assertEqual(conversation.sheet.first_line, 1)
        self.assertEqual(conversation.sheet.chosen,
                         conversation.sheet.first_lines[1])

    def test_neither_is_a_decision_and_is_recorded_as_one(self):
        conversation = self.sheet()
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=interview.NEITHER, now=LATER)
        self.assertEqual(conversation.sheet.first_line, interview.NEITHER)
        self.assertEqual(conversation.sheet.chosen, "")
        self.assertTrue(conversation.sheet.decided)

    def test_an_approval_that_decided_nothing_is_refused(self):
        # The whole of F1. Silence used to be the common case and it was
        # indistinguishable from a choice.
        conversation = self.sheet()
        with self.assertRaises(interview.FirstLineMissing):
            interview.approve(conversation, conversation.sheet.digest(),
                              now=LATER)
        self.assertEqual(conversation.sheet.state, interview.PROPOSED)

    def test_a_line_that_is_not_on_the_sheet_is_refused(self):
        conversation = self.sheet()
        for wrong in (2, 7, -3):
            with self.assertRaises(interview.FirstLineMissing):
                interview.approve(conversation, conversation.sheet.digest(),
                                  first_line=wrong, now=LATER)

    def lineless(self):
        """A sheet offering no first line, built by hand because `propose`
        refuses one: `_sheet_lines` has always required a non-empty list.
        So this shape reaches the engine from disk alone, which is a
        conversation written before this step existed, and it is the shape
        the refusal below must not fire on."""
        conversation = started(self.root)
        conversation.sheet = interview.Sheet(
            angle="Four months lost", elements=("four months",),
            moment="j'ai arrete", conviction="le direct paie",
            first_lines=(), proposed=WHEN.strftime(interview.STAMP))
        return conversation

    def test_a_sheet_offering_no_line_asks_nothing(self):
        # Nothing to choose between, so no step to skip. A refusal here
        # would be an unanswerable question.
        conversation = self.lineless()
        self.assertTrue(interview.approve(conversation,
                                          conversation.sheet.digest(),
                                          now=LATER))
        self.assertFalse(conversation.sheet.decided)

    def test_an_empty_sheet_cannot_record_that_both_were_refused(self):
        # Refusing both is an answer about two lines that were read. With
        # no lines there is nothing to refuse, so a click carrying that
        # answer stores no decision rather than a false one, and `decided`
        # stays the field that says whether anybody was asked.
        conversation = self.lineless()
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=interview.NEITHER, now=LATER)
        self.assertEqual(conversation.sheet.first_line, interview.UNDECIDED)
        self.assertFalse(conversation.sheet.decided)

    def test_a_second_click_is_the_same_decision_not_an_error(self):
        conversation = self.sheet()
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0, now=LATER)
        self.assertFalse(interview.approve(conversation,
                                           conversation.sheet.digest(),
                                           first_line=1, now=LATER))
        # And it does not move the decision either: the sheet is frozen.
        self.assertEqual(conversation.sheet.first_line, 0)

    def test_the_choice_is_not_in_the_digest(self):
        # The digest identifies the sheet somebody read. The choice is part
        # of the signature, not part of what is signed, and a digest moving
        # with it could never be matched by the form that carries the click.
        conversation = self.sheet()
        before = conversation.sheet.digest()
        interview.approve(conversation, before, first_line=1, now=LATER)
        self.assertEqual(conversation.sheet.digest(), before)

    def test_the_writer_is_told_which_line_was_taken(self):
        conversation = self.sheet()
        interview.say(conversation, "le canal direct est le seul qui paie")
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=1, now=LATER)
        material = interview.material(conversation)
        self.assertIn(f'"first_line": "{conversation.sheet.first_lines[1]}"',
                      material)

    def test_the_writer_is_told_when_neither_was_taken(self):
        # Not silence. A writer that cannot tell "nobody decided" from "both
        # were refused" writes the lukewarm line in both cases.
        conversation = self.sheet()
        interview.say(conversation, "le canal direct est le seul qui paie")
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=interview.NEITHER, now=LATER)
        self.assertIn('"first_line": null', interview.material(conversation))

    def test_a_sheet_nobody_was_asked_about_says_nothing_to_the_writer(self):
        conversation = self.lineless()
        interview.say(conversation, "le canal direct est le seul qui paie")
        interview.approve(conversation, conversation.sheet.digest(), now=LATER)
        material = interview.material(conversation)
        self.assertNotIn('"first_line":', material)

    def test_the_choice_credits_nothing_to_the_person(self):
        # An approval is a consent, not an utterance, and picking a line the
        # engine wrote is not saying it. `anchoring.md` again.
        conversation = self.sheet()
        before = interview.sufficiency(conversation)
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0, now=LATER)
        self.assertEqual(interview.sufficiency(conversation), before)
        self.assertNotIn(conversation.sheet.chosen, conversation.said())

    def test_the_choice_round_trips_through_the_disk(self):
        conversation = self.sheet()
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=1, now=LATER)
        interview.save(self.root, conversation, now=LATER)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.sheet, conversation.sheet)

    def test_a_sheet_nobody_decided_on_means_no_key_on_disk(self):
        # A conversation written before this step existed reads back byte
        # for byte, and reads back undecided rather than as a choice.
        conversation = self.sheet()
        interview.save(self.root, conversation, now=WHEN)
        raw = json.loads((self.directory(conversation)
                          / interview.CONVERSATION).read_text(encoding="utf-8"))
        self.assertNotIn("first_line", raw["sheet"])
        self.assertEqual(interview.load(self.root, conversation.id)
                         .sheet.first_line, interview.UNDECIDED)

    def test_a_choice_of_the_wrong_shape_on_disk_is_refused(self):
        conversation = self.sheet()
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0, now=LATER)
        interview.save(self.root, conversation, now=LATER)
        path = self.directory(conversation) / interview.CONVERSATION
        # 99 is in the list for the same reason the others are: `chosen`
        # would come back empty and `decided` true, and those two together
        # are how this file spells "both proposals were refused". A line
        # somebody took would read back as a line they turned down.
        for wrong in ("0", True, 1.5, None, 99, -7):
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["sheet"]["first_line"] = wrong
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(interview.InterviewError):
                interview.load(self.root, conversation.id)


class TestAMangledSheetOnDisk(InterviewCase):
    """A hand edited sheet the guard cannot read is refused with the file,
    exactly like a mangled message: a state the reader does not know would
    otherwise pass as `not approved` and quietly reopen the questions."""

    def mangle(self, **sheet):
        conversation = started(self.root)
        path = self.directory(conversation) / interview.CONVERSATION
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["sheet"] = sheet if sheet else None
        path.write_text(json.dumps(raw), encoding="utf-8")
        return conversation.id

    def test_an_unknown_state_is_refused(self):
        name = self.mangle(**dict(SHEET, state="maybe", proposed="",
                                  approved=""))
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, name)

    def test_a_field_of_the_wrong_shape_is_refused(self):
        name = self.mangle(state="proposed", angle=3,
                           elements=["ok"], moment="m", conviction="c",
                           first_lines=["f"], proposed="", approved="")
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, name)

    def test_a_list_holding_a_number_is_refused(self):
        name = self.mangle(state="proposed", angle="a",
                           elements=["ok", 3], moment="m", conviction="c",
                           first_lines=["f"], proposed="", approved="")
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, name)

    def test_an_explicit_null_reads_as_no_sheet(self):
        name = self.mangle()
        self.assertIsNone(interview.load(self.root, name).sheet)


DRAFT = {"body": "Quatre mois pour rien.\n\nLe canal direct est le seul "
                 "qui paie.",
         "anchors": [{"post": "Le canal direct est le seul qui paie.",
                      "said": "le canal direct est le seul qui paie"}]}


def offer(**kwargs):
    fields = dict(DRAFT)
    fields.update(kwargs)
    return fields


def approved(root):
    """An interview whose sheet is signed: the only state a draft is
    written from."""
    conversation = started(root)
    interview.say(conversation, "le canal direct est le seul qui paie")
    interview.propose(conversation, proposal(), now=WHEN)
    interview.approve(conversation, conversation.sheet.digest(),
                      first_line=0, now=LATER)
    return conversation


class TestTheDraft(InterviewCase):
    """The post the engine wrote, and the anchors it claims for it. The
    engine offers, the disk keeps, and no verdict is ever stored: the panel
    recomputes them from the body, the anchors and the transcript."""

    def test_an_offer_lands_on_the_conversation(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        draft = conversation.draft
        self.assertEqual(draft.body, DRAFT["body"])
        self.assertEqual(draft.anchors,
                         (Anchor(fragment=DRAFT["anchors"][0]["post"],
                                 quote=DRAFT["anchors"][0]["said"]),))
        self.assertEqual(draft.problems, ())
        self.assertEqual(draft.written, "2026-08-28T14:41:02")

    def test_nothing_is_drafted_before_the_sheet_is_approved(self):
        conversation = started(self.root)
        with self.assertRaisesRegex(interview.InterviewError, "approved"):
            interview.write(conversation, offer())
        self.assertIsNone(conversation.draft)
        interview.propose(conversation, proposal(), now=WHEN)
        with self.assertRaisesRegex(interview.InterviewError, "approved"):
            interview.write(conversation, offer())
        self.assertIsNone(conversation.draft)

    def test_a_closed_interview_takes_no_draft(self):
        conversation = approved(self.root)
        conversation.state = interview.CLOSED
        with self.assertRaises(interview.InterviewError):
            interview.write(conversation, offer())

    def test_a_new_draft_replaces_the_one_before_it(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=WHEN)
        interview.write(conversation, offer(body="Autre chose."), now=LATER)
        self.assertEqual(conversation.draft.body, "Autre chose.")
        self.assertEqual(conversation.draft.written, "2026-08-28T14:41:02")

    def test_the_draft_round_trips_through_the_disk(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.draft, conversation.draft)

    def test_no_draft_means_no_key_on_disk(self):
        conversation = approved(self.root)
        interview.save(self.root, conversation, now=LATER)
        raw = json.loads((self.directory(conversation)
                          / interview.CONVERSATION).read_text(encoding="utf-8"))
        self.assertNotIn("draft", raw)

    def test_a_body_that_is_not_a_non_empty_string_is_refused(self):
        for wrong in ("", "   ", None, 3, ["a"]):
            conversation = approved(self.root)
            with self.assertRaises(interview.InterviewError):
                interview.write(conversation, offer(body=wrong))
            self.assertIsNone(conversation.draft)

    def test_anchors_are_optional_because_a_bare_claim_is_honest(self):
        # anchoring.md: a claim with nothing to back it stays bare. An engine
        # that refused an empty block would be asking for a decoration.
        conversation = approved(self.root)
        interview.write(conversation, offer(anchors=[]), now=LATER)
        self.assertEqual(conversation.draft.anchors, ())

    def test_a_malformed_anchor_is_refused_rather_than_half_read(self):
        for wrong in ("not a list", [{"post": "x"}], [{"said": "y"}],
                      [{"post": 3, "said": "y"}], ["POST: x"], [None]):
            conversation = approved(self.root)
            with self.assertRaises(interview.InterviewError):
                interview.write(conversation, offer(anchors=wrong))
            self.assertIsNone(conversation.draft)

    def test_the_problems_of_a_prose_answer_travel_with_the_draft(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(),
                        problems=["ANCHORS was mangled"], now=LATER)
        self.assertEqual(conversation.draft.problems, ("ANCHORS was mangled",))

    def test_a_model_cannot_write_the_problems_of_its_own_reception(self):
        # The panel heads this list with what the engine failed to read. A
        # model that could fill it would be narrating its own arrival.
        conversation = approved(self.root)
        interview.write(conversation, offer(problems=["nothing went wrong"]),
                        now=LATER)
        self.assertEqual(conversation.draft.problems, ())

    def test_a_mangled_draft_on_disk_is_refused_whole(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        path = self.directory(conversation) / interview.CONVERSATION
        for wrong in ("not a map", {"body": 3, "anchors": []},
                      {"body": "ok", "anchors": [{"post": "a"}]},
                      {"body": "ok", "anchors": "no"},
                      {"body": "ok", "anchors": [], "problems": [3]}):
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["draft"] = wrong
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(interview.InterviewError):
                interview.load(self.root, conversation.id)



EVEN_LATER = datetime(2026, 8, 28, 15, 2, 30)
LATEST = datetime(2026, 8, 28, 15, 30, 0)


class TestTheVersionsOfADraft(InterviewCase):
    """Every draft this one replaced, oldest first, and the way back.

    A rewrite that aimed at one block leaves every other byte where it was,
    which is `passages.py`. What that guarantee is worth on a screen is
    somebody being able to see what moved and put it back, and neither is
    possible from one body.
    """

    def test_the_first_draft_replaces_nothing(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        self.assertEqual(conversation.earlier, [])
        self.assertEqual(interview.version(conversation), 1)

    def test_a_rewrite_keeps_the_draft_it_replaced(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        first = conversation.draft
        interview.write(conversation, offer(body="Autre chose."),
                        now=EVEN_LATER)
        self.assertEqual(conversation.earlier, [first])
        self.assertEqual(interview.version(conversation), 2)

    def test_a_passage_rewrite_keeps_it_too(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        first = conversation.draft
        block = passages.passages_of(first.body)[0]
        interview.write_passage(conversation, {"passage": "Quatre mois."},
                                scope=block, now=EVEN_LATER)
        self.assertEqual(conversation.earlier, [first])
        self.assertEqual(interview.version(conversation), 2)

    def test_going_back_puts_the_previous_draft_in_front_again(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        first = conversation.draft
        interview.write(conversation, offer(body="Autre chose."),
                        now=EVEN_LATER)
        interview.revert(conversation, shown(conversation.draft.body),
                         now=LATEST)
        self.assertEqual(conversation.draft.body, first.body)
        self.assertEqual(conversation.draft.anchors, first.anchors)
        self.assertEqual(conversation.earlier, [])
        self.assertEqual(interview.version(conversation), 1)

    def test_going_back_is_refused_on_a_body_that_is_not_on_the_screen(self):
        # The fourth signer of `shown`. A turn can replace the draft behind
        # a page already drawn, and the click that arrives from that page
        # would throw away a version its owner never saw.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.write(conversation, offer(body="Autre chose."),
                        now=EVEN_LATER)
        with self.assertRaises(interview.DraftChanged):
            interview.revert(conversation, shown("un autre post"), now=LATEST)
        self.assertEqual(conversation.draft.body, "Autre chose.")
        self.assertEqual(len(conversation.earlier), 1)

    def test_there_is_nothing_to_go_back_to_on_a_first_draft(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        with self.assertRaises(interview.InterviewError):
            interview.revert(conversation, shown(conversation.draft.body),
                             now=LATEST)

    def test_a_closed_interview_goes_nowhere(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.write(conversation, offer(body="Autre chose."),
                        now=EVEN_LATER)
        conversation.state = interview.CLOSED
        with self.assertRaises(interview.InterviewError):
            interview.revert(conversation, shown(conversation.draft.body),
                             now=LATEST)

    def test_going_back_stamps_the_moment_of_the_click(self):
        # `written` says when the engine wrote this body, because it did,
        # and `restored` says when it came back in front. Neither of them is
        # what decides whether a request has been answered: that is a fact
        # about turns, not about the body on screen, and it lives on the
        # conversation.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.write(conversation, offer(body="Autre chose."),
                        now=EVEN_LATER)
        interview.revert(conversation, shown(conversation.draft.body),
                         now=LATEST)
        self.assertEqual(conversation.draft.written,
                         LATER.strftime(interview.STAMP))
        self.assertEqual(conversation.draft.restored,
                         LATEST.strftime(interview.STAMP))

    def test_going_back_does_not_un_run_the_turn_it_threw_away(self):
        # A revert is not a drafting turn and it does not undo one. The
        # request that version answered stays answered, and the stamp that
        # says so does not move backwards with the body.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.revise(conversation, "plus court", now=EVEN_LATER)
        interview.write(conversation, offer(body="Autre chose."),
                        now=EVEN_LATER)
        interview.revert(conversation, shown(conversation.draft.body),
                         now=LATEST)
        self.assertEqual(conversation.drafted,
                         EVEN_LATER.strftime(interview.STAMP))
        interview.revise(conversation, "garde celui-la mais plus court",
                         now=datetime(2026, 8, 28, 16, 0, 0))
        asked = interview.material(conversation).split("## Revision")[1]
        self.assertIn("garde celui-la mais plus court", asked)
        self.assertNotIn("plus court\n\ngarde", asked)

    def test_going_back_keeps_every_request_no_turn_ever_answered(self):
        # The case the first shape of this got wrong. Two requests that
        # produced nothing, which `_pending` exists to carry together: a
        # refusal, then the source somebody comes back with. A revert in
        # the middle of that must not quietly mark the first one answered.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=WHEN)
        interview.write(conversation, offer(body="Autre chose."), now=LATER)
        interview.revise(conversation, "d'ou sortent ces chiffres",
                         now=EVEN_LATER)
        interview.revise(conversation, "barometre Malt, 2025",
                         now=datetime(2026, 8, 28, 15, 10, 0))
        interview.revert(conversation, shown(conversation.draft.body),
                         now=LATEST)
        asked = interview.material(conversation).split("## Revision")[1]
        self.assertIn("d'ou sortent ces chiffres", asked)
        self.assertIn("barometre Malt, 2025", asked)

    def test_when_the_last_turn_ran_survives_the_disk(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.drafted, LATER.strftime(interview.STAMP))

    def test_versions_on_disk_always_come_with_the_stamp_beside_them(self):
        # The two facts are written by one function so that no third writer
        # can set one and forget the other. A file carrying `earlier` and no
        # `drafted` is the shape where a revert moves the comparison stamp
        # backwards, and every request the discarded version answered comes
        # back as a live instruction.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.write(conversation, offer(body="Autre chose."),
                        now=EVEN_LATER)
        interview.save(self.root, conversation, now=EVEN_LATER)
        raw = json.loads((self.directory(conversation)
                          / interview.CONVERSATION).read_text(encoding="utf-8"))
        self.assertIn("earlier", raw)
        self.assertIn("drafted", raw)

    def test_a_file_with_versions_and_no_stamp_is_given_one_on_the_way_in(self):
        # A hand edited file, or one written by anything that ever fills
        # `earlier` without stamping. The current draft is the newest by
        # construction, so its own stamp is the high water mark and reading
        # it back is a migration rather than a guess.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=WHEN)
        interview.write(conversation, offer(body="Autre chose."), now=LATER)
        interview.revise(conversation, "R1", now=EVEN_LATER)
        interview.write(conversation, offer(body="Encore autre."),
                        now=datetime(2026, 8, 28, 15, 12, 0))
        interview.revise(conversation, "R2",
                         now=datetime(2026, 8, 28, 15, 15, 0))
        interview.save(self.root, conversation, now=LATEST)
        path = self.directory(conversation) / interview.CONVERSATION
        raw = json.loads(path.read_text(encoding="utf-8"))
        del raw["drafted"]
        path.write_text(json.dumps(raw), encoding="utf-8")

        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.drafted, again.draft.written)
        self.assertEqual([r.text for r in interview._pending(again)], ["R2"])
        interview.revert(again, shown(again.draft.body), now=LATEST)
        # R1 was answered by the version just thrown away, and it stays
        # answered. This is the whole of what the stamp is for.
        self.assertEqual([r.text for r in interview._pending(again)], ["R2"])

    def test_a_conversation_from_before_is_given_the_stamp_on_the_way_in(self):
        # No key on disk, so the draft in front supplies it: the body there
        # was written by the last turn that ran, which is true of every
        # conversation written before this stamp existed. A migration, not a
        # guess, and it is what makes the shape safe to go back from.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        path = self.directory(conversation) / interview.CONVERSATION
        raw = json.loads(path.read_text(encoding="utf-8"))
        del raw["drafted"]
        path.write_text(json.dumps(raw), encoding="utf-8")
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.drafted, LATER.strftime(interview.STAMP))
        interview.revise(again, "plus court", now=EVEN_LATER)
        self.assertIn("plus court", interview.material(again))

    def test_a_conversation_that_stamps_nothing_keeps_the_older_rule(self):
        # Neither key, and no draft stamp either. Nothing can be said about
        # what came after what, so the last request is the request.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        path = self.directory(conversation) / interview.CONVERSATION
        raw = json.loads(path.read_text(encoding="utf-8"))
        del raw["drafted"]
        raw["draft"]["written"] = ""
        path.write_text(json.dumps(raw), encoding="utf-8")
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.drafted, "")
        interview.revise(again, "premiere", now=EVEN_LATER)
        interview.revise(again, "seconde", now=LATEST)
        self.assertEqual([r.text for r in interview._pending(again)],
                         ["seconde"])

    def test_the_versions_round_trip_through_the_disk(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.write(conversation, offer(body="Autre chose."),
                        now=EVEN_LATER)
        interview.save(self.root, conversation, now=LATEST)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.earlier, conversation.earlier)
        self.assertEqual(again.draft, conversation.draft)

    def test_one_version_means_no_key_on_disk(self):
        # A conversation this engine never rewrote reads back byte for byte
        # through a version that never had the key.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        raw = json.loads((self.directory(conversation)
                          / interview.CONVERSATION).read_text(encoding="utf-8"))
        self.assertNotIn("earlier", raw)
        self.assertNotIn("restored", raw["draft"])

    def test_an_earlier_draft_of_the_wrong_shape_is_refused_whole(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        path = self.directory(conversation) / interview.CONVERSATION
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["earlier"] = [{"body": 42}]
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(interview.InterviewError):
            interview.load(self.root, conversation.id)



class TestOnlyWhatTheAuthorSaidCredits(InterviewCase):
    """D2, and it is A0 applied to a number.

    The gauge reads `said()` and nothing else, so the four provenances split
    the same way they split for an anchor: the transcript credits, the sheet
    is a consent rather than an utterance, the profile is not this
    interview, and a tool result is a machine's. Proved here rather than
    trusted, because the day somebody hands this function a wider text is
    the day the engine's own work is scored back to the person.
    """

    def test_what_the_person_said_moves_it(self):
        conversation = started(self.root)
        self.assertEqual(interview.sufficiency(conversation).facts, 0)
        interview.say(conversation, "12 clients chez Malt en 3 semaines")
        self.assertEqual(interview.sufficiency(conversation).facts, 3)

    def test_a_revision_request_moves_it_because_it_is_something_said(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        before = interview.sufficiency(conversation).facts
        interview.revise(conversation, "mets le vrai chiffre : 12 en 2024",
                         now=EVEN_LATER)
        self.assertEqual(interview.sufficiency(conversation).facts, before + 2)

    def test_the_sheet_credits_nothing(self):
        # An approval is a consent, not a parole. Every figure and every
        # name on this sheet is the engine's wording of what it heard, and
        # scoring it would pay the person twice for saying it once.
        conversation = started(self.root)
        before = interview.sufficiency(conversation)
        interview.propose(conversation, proposal(
            angle="4 mois perdus chez Malt",
            elements=["12 clients", "3 semaines chez Doctolib"],
            moment="on a signe 6800 euros",
            conviction="le direct paie",
            first_lines=["Quatre mois.", "2024 fut long."]), now=WHEN)
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0, now=LATER)
        self.assertEqual(interview.sufficiency(conversation), before)

    def test_a_tool_result_credits_nothing(self):
        # The profile arrives this way, and this is where a rich answer
        # about somebody else would arrive if the source door ever opened.
        conversation = started(self.root)
        conversation.messages.append(
            {"role": "user",
             "content": [{"type": "tool_result", "tool_use_id": "c1",
                          "content": "Le profil dit : 12 clients chez Malt, "
                                     "3 ans chez Doctolib, 6800 euros.",
                          "is_error": False}]})
        self.assertEqual(interview.sufficiency(conversation).facts, 0)

    def test_the_engine_asking_a_question_credits_nothing(self):
        # The loudest of the four. The engine quotes the previous answer in
        # its next question, on purpose, and a gauge reading the thread
        # would count every figure a second time the moment it was quoted
        # back, then climb on its own with nobody saying anything.
        conversation = started(self.root)
        interview.say(conversation, "12 clients")
        after_one = interview.sufficiency(conversation)
        conversation.messages.append(
            {"role": "assistant",
             "content": [{"type": "text",
                          "text": "Ces 12 clients, c'etait chez Malt en "
                                  "2024, sur 3 mois ?"}]})
        self.assertEqual(interview.sufficiency(conversation), after_one)


class TestTheDraftingStep(InterviewCase):
    """What a drafting turn is handed. Not the interview's own message list:
    a fresh request built from the material, which is what the skill asks
    for when it says a revision restarts from the interview every time."""

    def test_the_named_sections_exist_in_the_shipped_skill(self):
        block = system_block(REPO, interview.STEP_SKILL, "fr",
                             output_lang="en",
                             sections=interview.DRAFT_SECTIONS)
        self.assertIn("The signature block is not generated", block.text)

    def test_a_first_draft_is_not_handed_the_revision_vocabulary(self):
        # `Revisions` tells the model to offer five ways in when somebody asks
        # for a revision without saying what. Sent on a first draft, that is
        # an instruction to produce a menu instead of a post.
        conversation = approved(self.root)
        self.assertEqual(interview.drafting_sections(conversation),
                         interview.DRAFT_SECTIONS)

    def test_a_revision_is_handed_the_rule_it_is_the_one_that_forgets(self):
        # The skill: "the sheet rule applies here too, and this is where it is
        # usually forgotten". A rewrite that never reads it is the rewrite
        # that reintroduces an invented detail behind the signed sheet.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        interview.revise(conversation, REVISION, now=LATER)
        sections = interview.drafting_sections(conversation)
        self.assertEqual(sections[:-1], interview.DRAFT_SECTIONS)
        block = system_block(REPO, interview.STEP_SKILL, "fr",
                             output_lang="en", sections=sections)
        self.assertIn("A revision can reintroduce an invented detail",
                      block.text)

    def test_a_plain_rewrite_reads_them_too(self):
        # No new request, but still a rewrite of something already written.
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        self.assertNotEqual(interview.drafting_sections(conversation),
                            interview.DRAFT_SECTIONS)

    def test_the_material_is_the_interview_and_the_signed_sheet(self):
        conversation = approved(self.root)
        conversation.messages.insert(0, assistant("Qu'est-ce qui a changé ?"))
        material = interview.material(conversation)
        self.assertIn("Qu'est-ce qui a changé ?", material)
        self.assertIn("le canal direct est le seul qui paie", material)
        self.assertIn(SHEET["angle"], material)
        self.assertIn("first_lines", material)

    def test_the_material_carries_no_front_matter(self):
        # It is the interview as a reader meets it, not the file: a token
        # count and a price are not material anybody writes a post from.
        material = interview.material(approved(self.root))
        self.assertFalse(material.startswith("---"))
        self.assertNotIn("output_tokens", material)

    def test_there_is_no_material_before_the_sheet_is_signed(self):
        conversation = started(self.root)
        interview.say(conversation, "quelque chose")
        with self.assertRaisesRegex(interview.InterviewError, "approved"):
            interview.material(conversation)


class TestWhatTheDraftIsCheckedAgainst(InterviewCase):
    """The verdicts are not state. They are read off the body, the anchors
    and what the person said, every single time somebody looks."""

    def test_the_transcript_side_is_what_the_person_said_and_only_that(self):
        conversation = approved(self.root)
        conversation.messages.append(
            assistant("le canal direct est le seul qui paie, non ?"))
        interview.say(conversation, "oui")
        interview.write(conversation, offer(), now=LATER)
        # The quote is in the engine's question too. Reading the engine's
        # side as a source would let a model anchor on its own words.
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["anchored"])
        conversation.messages[0]["content"][0]["text"] = "autre chose"
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["fabricated"])

    def test_no_draft_means_nothing_to_check(self):
        self.assertEqual(interview.checked(approved(self.root)), [])

    def test_a_quote_lifted_from_the_profile_is_fabricated(self):
        # A2 of the Alchie backlog, pinned before the sheet seam lands. The
        # profile reaches the model on a tool result, which `said()` never
        # credits, so a draft that quotes the profile back is anchored on
        # nothing: the person recognises their own words and nothing was
        # verified. Fabricated is the right verdict today, and it has to stay
        # the right verdict once a second provenance exists.
        conversation = started(self.root)
        conversation.messages.append(assistant(
            calls=[("toolu_01", "read_instance", {"path": "profile.md"})]))
        conversation.messages.append(results(
            ("toolu_01", "Fractional CFO work for seed and Series A B2B "
                         "SaaS, three to five days a month.")))
        interview.say(conversation, "le canal direct est le seul qui paie")
        interview.propose(conversation, proposal(), now=WHEN)
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0, now=LATER)
        interview.write(conversation, offer(
            body="Fractional CFO work for seed and Series A B2B SaaS.\n\n"
                 "Le canal direct est le seul qui paie.",
            anchors=[{"post": "Fractional CFO work for seed and Series A",
                      "said": "Fractional CFO work for seed and Series A "
                              "B2B SaaS"},
                     {"post": "Le canal direct est le seul qui paie.",
                      "said": "le canal direct est le seul qui paie"}]),
            now=LATER)
        self.assertNotIn("Fractional", conversation.said())
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["fabricated", "anchored"])

    def test_a_sheet_line_quoted_as_something_said_is_fabricated(self):
        # The sheet is the engine's rewording of what was said, approved by
        # a click. A quote that names the transcript is looked for in the
        # transcript and nowhere else, so the sheet's own words offered as
        # something said come back fabricated. This is the verdict a sheet
        # seam must leave exactly where it is: a backing never converts.
        conversation = approved(self.root)
        line = conversation.sheet.angle
        self.assertNotIn(line, conversation.said())
        interview.write(conversation, offer(
            body=line + ".\n\nLe canal direct est le seul qui paie.",
            anchors=[{"post": line, "said": line}]), now=LATER)
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["fabricated"])



class TestASheetBacking(InterviewCase):
    """The second provenance, `references/anchoring.md` under Provenance. A
    claim that descends from the sheet the person approved is backed under
    the `sheet` key, checked against the sheet's own words, and never
    converted into something they said: an approval is consent, not
    utterance."""

    def backed(self, conversation, quote, key="sheet"):
        line = conversation.sheet.elements[1]
        interview.write(conversation, offer(
            body=line + ".\n\nLe canal direct est le seul qui paie.",
            anchors=[{"post": line, key: quote}]), now=LATER)
        return line

    def test_a_sheet_pair_lands_with_its_provenance(self):
        conversation = approved(self.root)
        line = self.backed(conversation, conversation.sheet.elements[1])
        self.assertEqual(conversation.draft.anchors,
                         (Anchor(fragment=line, quote=line, provenance="sheet"),))

    def test_it_round_trips_through_the_disk_under_its_own_key(self):
        conversation = approved(self.root)
        self.backed(conversation, conversation.sheet.elements[1])
        interview.save(self.root, conversation, now=LATER)
        raw = json.loads((self.directory(conversation) / interview.CONVERSATION)
                         .read_text(encoding="utf-8"))
        self.assertEqual(sorted(raw["draft"]["anchors"][0]), ["post", "sheet"])
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.draft.anchors, conversation.draft.anchors)

    def test_a_pair_naming_both_backings_is_refused(self):
        conversation = approved(self.root)
        with self.assertRaisesRegex(interview.InterviewError, "never both"):
            interview.write(conversation, offer(anchors=[
                {"post": "Le canal direct est le seul qui paie.",
                 "said": "le canal direct est le seul qui paie",
                 "sheet": "le canal direct est le seul qui paie"}]))

    def test_a_pair_naming_no_backing_is_refused(self):
        conversation = approved(self.root)
        with self.assertRaisesRegex(interview.InterviewError, "never neither"):
            interview.write(conversation, offer(anchors=[
                {"post": "Le canal direct est le seul qui paie."}]))

    def test_a_sheet_quote_is_checked_against_the_sheet(self):
        conversation = approved(self.root)
        line = self.backed(conversation, conversation.sheet.elements[1])
        self.assertNotIn(line, conversation.said())
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["anchored"])

    def test_a_sheet_quote_absent_from_the_sheet_is_fabricated(self):
        conversation = approved(self.root)
        self.backed(conversation, "une phrase que la fiche ne dit pas")
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["fabricated"])

    def test_the_sources_hold_the_sheet_only_once_approved(self):
        conversation = started(self.root)
        interview.say(conversation, "le canal direct est le seul qui paie")
        interview.propose(conversation, proposal(), now=WHEN)
        self.assertEqual(sorted(interview.sources(conversation)),
                         ["transcript"])
        interview.approve(conversation, conversation.sheet.digest(),
                          first_line=0, now=LATER)
        found = interview.sources(conversation)
        self.assertEqual(sorted(found), ["sheet", "transcript"])
        self.assertEqual(found["transcript"], conversation.said())
        self.assertEqual(found["sheet"], conversation.sheet.text())

    def test_the_sheet_text_is_the_five_fields_whole(self):
        sheet = interview.Sheet(angle="a", elements=("b", "c"), moment="d",
                                conviction="e", first_lines=("f", "g"))
        self.assertEqual(sheet.text(), "a\nb\nc\nd\ne\nf\ng")


REVISION = "L'accroche est trop commerciale, ouvre sur le chiffre."


class TestARevision(InterviewCase):
    """What the person asks for once a draft exists.

    Their words, kept as such. `references/instance.md` says why: the same
    person typed them on the same screen as every interview answer, so a
    correction is material a redraft may quote.
    """

    def drafted(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        return conversation

    def test_a_request_lands_on_the_conversation(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=LATER)
        self.assertEqual([r.text for r in conversation.revisions], [REVISION])
        self.assertEqual(conversation.revisions[0].asked,
                         "2026-08-28T14:41:02")

    def test_the_list_is_append_only(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=WHEN)
        interview.revise(conversation, "Plus court.", now=LATER)
        self.assertEqual([r.text for r in conversation.revisions],
                         [REVISION, "Plus court."])

    def test_an_empty_request_is_not_a_request(self):
        conversation = self.drafted()
        for wrong in ("", "   ", "\n"):
            with self.assertRaises(interview.InterviewError):
                interview.revise(conversation, wrong)
        self.assertEqual(conversation.revisions, [])

    def test_whitespace_is_trimmed(self):
        conversation = self.drafted()
        interview.revise(conversation, "  " + REVISION + "\n", now=LATER)
        self.assertEqual(conversation.revisions[0].text, REVISION)

    def test_there_is_nothing_to_revise_before_a_draft(self):
        # The sheet steers the first draft. A revision revises something.
        conversation = approved(self.root)
        with self.assertRaises(interview.InterviewError):
            interview.revise(conversation, REVISION)
        self.assertEqual(conversation.revisions, [])

    def test_a_closed_interview_takes_no_revision(self):
        conversation = self.drafted()
        conversation.state = interview.CLOSED
        with self.assertRaises(interview.InterviewError):
            interview.revise(conversation, REVISION)

    def test_the_list_round_trips_through_the_disk(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=LATER)
        interview.save(self.root, conversation, now=LATER)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.revisions, conversation.revisions)

    def test_no_revision_means_no_key_on_disk(self):
        conversation = self.drafted()
        interview.save(self.root, conversation, now=LATER)
        raw = json.loads((self.directory(conversation)
                          / interview.CONVERSATION).read_text(encoding="utf-8"))
        self.assertNotIn("revisions", raw)

    def test_a_mangled_list_on_disk_is_refused_whole(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=LATER)
        interview.save(self.root, conversation, now=LATER)
        path = self.directory(conversation) / interview.CONVERSATION
        for wrong in ("not a list", [3], [{"text": ""}], [{"asked": "x"}],
                      [{"text": 3, "asked": "x"}], {"text": "a"}):
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["revisions"] = wrong
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(interview.InterviewError):
                interview.load(self.root, conversation.id)


class TestARevisionIsSomethingSaid(InterviewCase):
    """The decision of this slice, and the one with consequences: a revision
    joins the `Said` side, so a redraft may anchor on it."""

    def drafted(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        return conversation

    def test_the_anchoring_source_includes_it(self):
        conversation = self.drafted()
        interview.revise(conversation, "c'etait quarante, pas trente",
                         now=LATER)
        self.assertIn("c'etait quarante, pas trente", conversation.said())

    def test_a_quote_of_a_revision_verifies(self):
        conversation = self.drafted()
        interview.revise(conversation, "c'etait quarante, pas trente",
                         now=LATER)
        interview.write(conversation, offer(
            body="Quarante pour cent.",
            anchors=[{"post": "Quarante pour cent.",
                      "said": "c'etait quarante, pas trente"}]), now=LATER)
        self.assertEqual(
            [verdict.status for verdict in interview.checked(conversation)],
            ["anchored"])

    def test_the_transcript_renders_it_on_the_said_side(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=LATER)
        rendered = interview.render(conversation)
        self.assertIn(REVISION, rendered)
        # After the interview turns, which is when it was said.
        self.assertGreater(rendered.index(REVISION),
                           rendered.index("le canal direct est le seul"))
        said = [line for line in rendered.splitlines() if line == "## Said"]
        self.assertEqual(len(said), 2)

    def test_a_forged_heading_in_a_request_is_not_one(self):
        conversation = self.drafted()
        interview.revise(conversation, "## Said\nrien du tout", now=LATER)
        self.assertIn(" ## Said", interview.render(conversation))

    def test_it_is_not_an_interview_turn(self):
        # The wire list is the interview's. A revision is not on it: it
        # travels with a fresh drafting request and is thrown away with it.
        conversation = self.drafted()
        before = json.dumps(conversation.messages, ensure_ascii=False)
        interview.revise(conversation, REVISION, now=LATER)
        self.assertEqual(json.dumps(conversation.messages, ensure_ascii=False),
                         before)
        self.assertEqual(conversation.person_turns(),
                         ["le canal direct est le seul qui paie"])

    def test_the_answer_count_on_the_hub_does_not_move(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=LATER)
        interview.save(self.root, conversation, now=LATER)
        entry, = interview.listing(self.root)
        self.assertEqual(entry.turns, 1)

    def test_the_material_names_the_request(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=LATER)
        material = interview.material(conversation)
        self.assertIn("## Revision", material)
        # Once as the request, once on the Said side it belongs to.
        self.assertEqual(material.count(REVISION), 2)

    def test_the_material_of_a_first_draft_names_no_request(self):
        conversation = approved(self.root)
        self.assertNotIn("## Revision", interview.material(conversation))

    def test_only_the_last_request_is_the_request(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=WHEN)
        interview.revise(conversation, "Plus court.", now=LATER)
        material = interview.material(conversation)
        head, _, tail = material.partition("## Revision")
        self.assertIn("Plus court.", tail)
        self.assertNotIn(REVISION, tail)
        self.assertIn(REVISION, head)


AFTER = datetime(2026, 8, 28, 14, 52, 30)
LATEST = datetime(2026, 8, 28, 15, 3, 47)


class TestATurnThatProducedNothing(InterviewCase):
    """A turn where the engine wrote no draft must not cost the person their
    instruction.

    This is the refusal turn: they ask for a source, the engine refuses
    rather than inventing one and rewrites nothing. Their next message is a
    source, not an instruction, and a block carrying only the last request
    would hand the writer "Malt barometer, 2025" as the thing to do.

    Told from the timestamps the two objects already carry, not from a new
    key: a `conversation.json` written before this reads back the same way.
    """

    def drafted(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        return conversation

    def pending(self, conversation) -> str:
        _, _, tail = interview.material(conversation).partition("## Revision")
        return tail

    def test_a_request_nothing_answered_stays_in_front(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=AFTER)
        interview.revise(conversation, "Baromètre Malt, 2025.", now=LATEST)
        tail = self.pending(conversation)
        self.assertIn(REVISION, tail)
        self.assertIn("Baromètre Malt, 2025.", tail)
        self.assertLess(tail.index(REVISION), tail.index("Baromètre Malt"))

    def test_a_request_a_draft_answered_drops_out(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=AFTER)
        interview.write(conversation, offer(), now=LATEST)
        interview.revise(conversation, "Plus court.", now=datetime(
            2026, 8, 28, 15, 20, 0))
        tail = self.pending(conversation)
        self.assertIn("Plus court.", tail)
        self.assertNotIn(REVISION, tail)

    def test_the_block_still_names_one_when_everything_was_answered(self):
        # Nothing is pending and a redraft is asked for anyway. The old rule
        # applies rather than an empty block, which would be a writing turn
        # with no instruction at all.
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=AFTER)
        interview.write(conversation, offer(), now=LATEST)
        self.assertIn(REVISION, self.pending(conversation))

    def test_a_request_answered_in_the_same_second_is_answered(self):
        # The route asks for the revision, then the turn writes the draft,
        # and both can land inside one second. Equal stamps mean served:
        # a boundary nothing else pins, and the difference between one
        # instruction in front of the writer and two.
        conversation = self.drafted()          # the draft is written at LATER
        interview.revise(conversation, REVISION, now=LATER)
        interview.revise(conversation, "Plus court.", now=AFTER)
        tail = self.pending(conversation)
        self.assertIn("Plus court.", tail)
        self.assertNotIn(REVISION, tail)

    def test_a_run_of_dead_turns_does_not_grow_without_bound(self):
        # Ten turns that produced nothing is a provider failing, not ten
        # instructions. The block is capped and keeps the most recent, which
        # are the wordings the earlier ones were retyped into.
        conversation = self.drafted()
        for minute in range(10):
            interview.revise(conversation, f"Demande {minute}.",
                             now=datetime(2026, 8, 28, 15, minute, 0))
        tail = self.pending(conversation)
        self.assertEqual(tail.count("Demande "), interview.MOST_PENDING)
        self.assertIn("Demande 9.", tail)
        self.assertNotIn("Demande 0.", tail)

    def test_a_conversation_with_no_timestamp_keeps_the_old_rule(self):
        # Written by a version that stamped neither the turn nor the draft.
        # Nothing can be said about what came after what, so nothing new is
        # claimed. Both stamps, because a file from that version has neither
        # and the fallback is what such a file has always got.
        conversation = self.drafted()
        conversation.drafted = ""
        conversation.draft = replace(conversation.draft, written="")
        interview.revise(conversation, REVISION, now=AFTER)
        interview.revise(conversation, "Plus court.", now=LATEST)
        tail = self.pending(conversation)
        self.assertIn("Plus court.", tail)
        self.assertNotIn(REVISION, tail)


class TestARevisionAimedAtOnePassage(InterviewCase):
    """A revision used to be aimed at the post. It can be aimed at a block.

    The mechanism is `passages.py`, which is `sections.py` for prose: the
    block carries its span, and a rewrite of it touches those characters and
    leaves every other byte of the post where it was. What that buys is not
    tidiness. It is that a person asking for a sharper second paragraph
    cannot lose the first one to a model that decided to improve it too.
    """

    BODY = ("Quatre mois à vendre aux agences.\n\n"
            "Onze conversations, deux propositions, rien de signé.\n\n"
            "J'ai arrêté.")
    #: One anchor per block, so a test can say which pairs a rewrite keeps.
    PAIRS = [{"post": "Quatre mois à vendre aux agences.",
              "said": "le canal direct est le seul qui paie"},
             {"post": "rien de signé",
              "said": "le canal direct est le seul qui paie"}]

    def drafted(self):
        conversation = approved(self.root)
        interview.write(conversation,
                        offer(body=self.BODY, anchors=self.PAIRS), now=LATER)
        return conversation

    def blocks(self, conversation):
        return passages.passages_of(conversation.draft.body)

    def test_a_request_can_name_the_block_it_is_about(self):
        conversation = self.drafted()
        block = self.blocks(conversation)[1]
        interview.revise(conversation, "Trop vague, mets le vrai chiffre.",
                         passage=block.digest, passage_index=1, now=AFTER)
        kept = conversation.revisions[0]
        self.assertEqual(kept.passage, block.digest)
        self.assertEqual(kept.passage_index, 1)

    def test_a_request_about_nothing_in_particular_still_works(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=AFTER)
        self.assertEqual(conversation.revisions[0].passage, "")
        self.assertEqual(conversation.revisions[0].passage_index, -1)
        self.assertIsNone(interview.passage_for(conversation, "", -1))
        self.assertIsNone(interview.pending_scope(conversation))

    def test_a_stale_screen_is_refused_at_the_click(self):
        # The turn behind a page can rewrite the post while somebody is
        # reading it. A request aimed at what used to be the second block
        # must not land on whatever is there now.
        conversation = self.drafted()
        with self.assertRaises(interview.InterviewError):
            interview.revise(conversation, "Trop vague.",
                             passage=shown("what the screen used to show"),
                             passage_index=1, now=AFTER)
        self.assertEqual(conversation.revisions, [])

    def test_an_index_that_is_not_there_is_refused(self):
        conversation = self.drafted()
        with self.assertRaises(interview.InterviewError):
            interview.revise(conversation, "Trop vague.",
                             passage=self.blocks(conversation)[0].digest,
                             passage_index=9, now=AFTER)

    def test_the_scope_of_a_turn_is_what_the_screen_sent(self):
        # From the form and from nothing else. A scope read off the
        # conversation outlives the screen: the request below stays pending
        # after a turn that produced nothing, and a later turn whose picker
        # said "the whole post" would still be confined to this block.
        conversation = self.drafted()
        block = self.blocks(conversation)[1]
        interview.revise(conversation, "Trop vague.",
                         passage=block.digest, passage_index=1, now=AFTER)
        self.assertEqual(
            interview.passage_for(conversation, block.digest, 1).text,
            block.text)
        self.assertIsNone(interview.passage_for(conversation, "", -1))

    def test_a_stale_scope_from_a_form_is_refused(self):
        conversation = self.drafted()
        with self.assertRaises(interview.InterviewError):
            interview.passage_for(conversation, shown("stale"), 1)

    def test_the_screen_offers_a_pending_scope_back(self):
        # So a refusal, a failed turn or a reload does not drop the passage
        # somebody chose. It decides what the picker shows, never what a
        # turn does.
        conversation = self.drafted()
        block = self.blocks(conversation)[1]
        interview.revise(conversation, "Trop vague.",
                         passage=block.digest, passage_index=1, now=AFTER)
        self.assertEqual(interview.pending_scope(conversation).text, block.text)

    def test_nothing_is_offered_back_once_a_draft_answered_it(self):
        conversation = self.drafted()
        block = self.blocks(conversation)[1]
        interview.revise(conversation, "Trop vague.",
                         passage=block.digest, passage_index=1, now=AFTER)
        interview.write_passage(conversation, {"passage": "Onze."},
                                scope=block, now=LATEST)
        self.assertIsNone(interview.pending_scope(conversation))

    def test_the_material_carries_the_passage_word_for_word(self):
        conversation = self.drafted()
        block = self.blocks(conversation)[1]
        interview.revise(conversation, "Trop vague.",
                         passage=block.digest, passage_index=1, now=AFTER)
        material = interview.material(conversation, scope=block)
        self.assertIn("## Passage", material)
        head, _, tail = material.partition("## Passage")
        self.assertIn(block.text, tail)

    def test_the_material_of_an_unscoped_request_names_no_passage(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=AFTER)
        self.assertNotIn("## Passage", interview.material(conversation))

    def test_the_scoped_turn_is_handed_its_own_section(self):
        conversation = self.drafted()
        block = self.blocks(conversation)[1]
        interview.revise(conversation, "Trop vague.",
                         passage=block.digest, passage_index=1, now=AFTER)
        self.assertIn(interview.PASSAGE_SECTION,
                      interview.drafting_sections(conversation, scope=block))

    def test_an_unscoped_revision_is_not(self):
        conversation = self.drafted()
        interview.revise(conversation, REVISION, now=AFTER)
        self.assertNotIn(interview.PASSAGE_SECTION,
                         interview.drafting_sections(conversation))


class TestRewritingOnePassage(InterviewCase):
    """What the engine hands back for a scoped request, and what the post
    becomes. The guarantee is that every other byte is where it was."""

    BODY = TestARevisionAimedAtOnePassage.BODY
    PAIRS = TestARevisionAimedAtOnePassage.PAIRS

    def scoped(self):
        conversation = approved(self.root)
        interview.write(conversation,
                        offer(body=self.BODY, anchors=self.PAIRS), now=LATER)
        block = passages.passages_of(conversation.draft.body)[1]
        interview.revise(conversation, "Trop vague, mets le vrai chiffre.",
                         passage=block.digest, passage_index=1, now=AFTER)
        return conversation, block

    def test_only_the_named_block_moves(self):
        conversation, block = self.scoped()
        interview.write_passage(
            conversation, {"passage": "Onze conversations en quatre mois."},
            scope=block, now=LATEST)
        self.assertEqual(
            conversation.draft.body,
            self.BODY.replace(
                "Onze conversations, deux propositions, rien de signé.",
                "Onze conversations en quatre mois."))

    def test_the_draft_is_stamped_like_any_other(self):
        conversation, block = self.scoped()
        interview.write_passage(conversation, {"passage": "Onze."},
                                scope=block, now=LATEST)
        self.assertEqual(conversation.draft.written, "2026-08-28T15:03:47")

    def test_a_rewrite_with_nothing_in_it_is_refused(self):
        conversation, block = self.scoped()
        for empty in ("", "   "):
            with self.assertRaises(interview.InterviewError):
                interview.write_passage(conversation, {"passage": empty},
                                        scope=block)
        self.assertEqual(conversation.draft.body, self.BODY)

    def test_a_second_rewrite_in_the_same_turn_lands_nothing(self):
        """A model may put two calls in one message, and both wired
        providers do: `tool_choice` asks for at least one call, never at
        most one. The second arrives holding the offsets of the body the
        first one already rewrote. Refused, and the post is what the first
        call made it."""
        conversation, block = self.scoped()
        interview.write_passage(conversation, {"passage": "Court."},
                                scope=block, now=LATEST)
        after = conversation.draft.body
        with self.assertRaises(interview.InterviewError):
            interview.write_passage(
                conversation, {"passage": "Un deuxième essai, plus long."},
                scope=block, now=LATEST)
        self.assertEqual(conversation.draft.body, after)
        self.assertIn("J'ai arrêté.", conversation.draft.body)

    def test_an_additive_rewrite_does_not_open_the_span_again(self):
        """The shape a comparison at the offsets cannot catch: the first
        call returns the block plus a sentence, so the bytes at the old
        span are still the old text and a second call would weld itself
        onto the first call's tail, inside a word."""
        conversation, block = self.scoped()
        interview.write_passage(
            conversation, {"passage": block.text + " Douze en trois semaines."},
            scope=block, now=LATEST)
        after = conversation.draft.body
        with self.assertRaises(interview.InterviewError):
            interview.write_passage(conversation, {"passage": "Autre chose."},
                                    scope=block, now=LATEST)
        self.assertEqual(conversation.draft.body, after)

    def test_a_pair_offered_twice_is_one_pair(self):
        # The panel counts rows. A model re-offering a pair it was told it
        # could keep would count one claim twice.
        conversation, block = self.scoped()
        interview.write_passage(
            conversation,
            {"passage": "Onze.",
             "anchors": [{"post": "Quatre mois à vendre aux agences.",
                          "said": "le canal direct est le seul qui paie"}]},
            scope=block, now=LATEST)
        fragments = [pair.fragment for pair in conversation.draft.anchors]
        self.assertEqual(fragments.count("Quatre mois à vendre aux agences."), 1)

    def test_nothing_is_rewritten_before_the_sheet_is_signed(self):
        # The guard its sibling `write` has. The route makes this
        # unreachable today, and that is the argument that stops being true
        # the day somebody calls this from somewhere else.
        conversation = approved(self.root)
        interview.write(conversation, offer(body=self.BODY), now=LATER)
        block = passages.passages_of(conversation.draft.body)[1]
        conversation.sheet = replace(conversation.sheet, state="proposed")
        with self.assertRaisesRegex(interview.InterviewError, "approved"):
            interview.write_passage(conversation, {"passage": "Onze."},
                                    scope=block)

    def test_a_rewrite_with_no_scope_is_refused(self):
        # Nothing said which block. Rewriting the post from a tool meant for
        # a passage would be the whole post silently replaced by a fragment.
        conversation = approved(self.root)
        interview.write(conversation, offer(body=self.BODY), now=LATER)
        with self.assertRaises(interview.InterviewError):
            interview.write_passage(conversation, {"passage": "Onze."})

    def test_an_anchor_of_a_block_that_did_not_move_is_kept(self):
        conversation, block = self.scoped()
        interview.write_passage(conversation, {"passage": "Onze."},
                                scope=block, now=LATEST)
        kept = [pair.fragment for pair in conversation.draft.anchors]
        self.assertIn("Quatre mois à vendre aux agences.", kept)

    def test_an_anchor_of_the_block_that_moved_is_dropped(self):
        # Its fragment is not in the post any more. Keeping it would show as
        # dangling on every read, which is a true verdict about a pair that
        # has no business still being there.
        conversation, block = self.scoped()
        interview.write_passage(conversation, {"passage": "Onze."},
                                scope=block, now=LATEST)
        kept = [pair.fragment for pair in conversation.draft.anchors]
        self.assertNotIn("rien de signé", kept)

    def test_a_pair_the_panel_calls_backing_is_not_thrown_away(self):
        """The engine has one answer to "is this fragment in the draft", and
        it is `anchors.contains`: typography folded, whitespace collapsed,
        case ignored. A plain `in` here is a second answer, and the two
        disagree on the commonest thing there is, a straight apostrophe
        stored against a curly one in the post. The pair backs its claim on
        every read; dropping it here would take a real quote off a block
        nobody asked to change, silently and on disk."""
        conversation = approved(self.root)
        body = ("J’ai signé douze clients cette semaine.\n\n"
                "Onze conversations, deux propositions, rien de signé.")
        interview.write(conversation, offer(
            body=body,
            anchors=[{"post": "J'ai signé douze clients cette semaine.",
                      "said": "le canal direct est le seul qui paie"}]),
            now=LATER)
        block = passages.passages_of(conversation.draft.body)[1]
        interview.revise(conversation, "Trop vague.", passage=block.digest,
                         passage_index=1, now=AFTER)
        interview.write_passage(conversation, {"passage": "Onze."},
                                scope=block, now=LATEST)
        self.assertEqual([pair.fragment for pair in conversation.draft.anchors],
                         ["J'ai signé douze clients cette semaine."])

    def test_the_new_block_brings_its_own_anchors(self):
        conversation, block = self.scoped()
        interview.write_passage(
            conversation,
            {"passage": "Onze conversations.",
             "anchors": [{"post": "Onze conversations.",
                          "said": "le canal direct est le seul qui paie"}]},
            scope=block, now=LATEST)
        pairs = {pair.fragment: pair.quote
                 for pair in conversation.draft.anchors}
        self.assertIn("Onze conversations.", pairs)
        self.assertIn("Quatre mois à vendre aux agences.", pairs)


PHOTOS = [{"kind": "portrait", "text": "Devant le tableau, marqueur en main."},
          {"kind": "visual", "text": "Le tableau des onze heures."}]
TIPS = [{"kind": "strong", "text": "« Quatre mois pour rien » porte le post."},
        {"kind": "weak", "text": "La cloture retombe."},
        {"kind": "lesson", "text": "Ouvrir sur le chiffre la prochaine fois."}]


class TestWhatTheSessionLeavesBehind(InterviewCase):
    """The two photo ideas and the three tips the skill asks the writing step
    for. They are not the post: archiving files them under session notes."""

    def test_they_land_on_the_draft(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(photos=PHOTOS, tips=TIPS),
                        now=LATER)
        self.assertEqual([(n.kind, n.text) for n in conversation.draft.photos],
                         [(p["kind"], p["text"]) for p in PHOTOS])
        self.assertEqual([(n.kind, n.text) for n in conversation.draft.tips],
                         [(t["kind"], t["text"]) for t in TIPS])

    def test_they_are_optional_because_the_post_is_worth_more(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(), now=LATER)
        self.assertEqual(conversation.draft.photos, ())
        self.assertEqual(conversation.draft.tips, ())

    def test_a_partial_answer_keeps_what_arrived(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(photos=PHOTOS[:1]), now=LATER)
        self.assertEqual(len(conversation.draft.photos), 1)

    def test_an_unknown_kind_is_refused(self):
        conversation = approved(self.root)
        with self.assertRaises(interview.InterviewError):
            interview.write(conversation, offer(
                photos=[{"kind": "selfie", "text": "x"}]))
        self.assertIsNone(conversation.draft)

    def test_a_kind_offered_twice_is_refused(self):
        conversation = approved(self.root)
        with self.assertRaises(interview.InterviewError):
            interview.write(conversation, offer(photos=PHOTOS[:1] + PHOTOS[:1]))
        self.assertIsNone(conversation.draft)

    def test_a_malformed_entry_is_refused_rather_than_half_read(self):
        for wrong in ("not a list", [None], [{"kind": "strong"}],
                      [{"text": "x"}], [{"kind": "strong", "text": ""}],
                      [{"kind": 3, "text": "x"}]):
            conversation = approved(self.root)
            with self.assertRaises(interview.InterviewError):
                interview.write(conversation, offer(tips=wrong))
            self.assertIsNone(conversation.draft)

    def test_they_round_trip_through_the_disk(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(photos=PHOTOS, tips=TIPS),
                        now=LATER)
        interview.save(self.root, conversation, now=LATER)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.draft, conversation.draft)

    def test_a_mangled_shape_on_disk_is_refused_whole(self):
        conversation = approved(self.root)
        interview.write(conversation, offer(photos=PHOTOS), now=LATER)
        interview.save(self.root, conversation, now=LATER)
        path = self.directory(conversation) / interview.CONVERSATION
        for wrong in ("no", [3], [{"kind": "portrait"}],
                      [{"kind": "selfie", "text": "x"}]):
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["draft"]["photos"] = wrong
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(interview.InterviewError):
                interview.load(self.root, conversation.id)
if __name__ == "__main__":
    unittest.main(verbosity=2)
