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
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app import interview  # noqa: E402
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
