"""Tests for verbatim_app.archive, the step where an interview becomes a post.

The fixture is examples/, the Nadia Feriel persona, copied to a temp directory
so nothing here touches the shipped files. Every behaviour asserted is a clause
of references/instance.md or of skills/linkedin-post; when they disagree, the
contract wins and this file is wrong.

Runs with the standard library only:  python3 app/tests/test_archive.py
"""

import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app import archive, interview  # noqa: E402
from verbatim_app.instance import (  # noqa: E402
    Instance, InstanceError, UnreadableError, split_front_matter,
)

WHEN = datetime(2026, 8, 29, 10, 15, 0)

BODY = ("Quatre mois a vendre aux agences.\n\n"
        "Onze conversations, deux propositions, rien de signe.")


def filing(**kwargs):
    fields = dict(date="2026-08-29", slug="agences-quatre-mois", pillar=3,
                  format="the-post-mortem", label="VISIBILITY")
    fields.update(kwargs)
    return archive.Filing(**fields)


class ArchiveCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-archive-")
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
        self.instance = Instance(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def drafted(self, **draft):
        """An interview with a signed sheet and a draft on it: the only state
        anything is archived from."""
        conversation = interview.start(
            self.root, skill="linkedin-post", sections=("The interview",),
            interface_language="fr", output_language="fr",
            provider="anthropic", model="claude-opus-5", now=WHEN)
        interview.say(conversation, "quatre mois a vendre aux agences")
        interview.propose(conversation, {
            "angle": "Le segment abandonne, avec ce qu'il a coute",
            "elements": ["onze conversations", "deux propositions"],
            "moment": "rien de signe",
            "conviction": "le canal direct est le seul qui paie",
            "first_lines": ["Quatre mois a vendre aux agences."]}, now=WHEN)
        interview.approve(conversation, conversation.sheet.digest(), now=WHEN)
        fields = dict(body=BODY, anchors=[
            {"post": "Onze conversations", "said": "quatre mois a vendre"}])
        fields.update(draft)
        interview.write(conversation, fields, now=WHEN)
        interview.save(self.root, conversation, now=WHEN)
        return conversation


class TestTheFiling(ArchiveCase):
    """What the person decided on their screen. None of it is derivable from
    the draft, and a guess here is a guess counted in every ratio afterwards."""

    def test_the_file_name_is_the_date_and_the_slug(self):
        self.assertEqual(archive.filename(filing()),
                         "2026-08-29-agences-quatre-mois.md")

    def test_a_slug_that_could_address_another_directory_is_refused(self):
        for wrong in ("../escape", "a/b", "", "Agences", "-lead", "trail-",
                      "double--dash", "a b", ".hidden"):
            with self.assertRaises(archive.ArchiveError):
                archive.check(filing(slug=wrong))

    def test_a_date_that_is_not_one_is_refused(self):
        for wrong in ("29-08-2026", "2026-8-29", "", "2026-13-01",
                      "2026-02-30", "today"):
            with self.assertRaises(archive.ArchiveError):
                archive.check(filing(date=wrong))

    def test_the_format_comes_from_the_reference(self):
        for good in archive.FORMATS:
            archive.check(filing(format=good))
        with self.assertRaises(archive.ArchiveError):
            archive.check(filing(format="the-listicle"))

    def test_the_label_is_one_of_the_three(self):
        for good in archive.LABELS:
            archive.check(filing(label=good))
        with self.assertRaises(archive.ArchiveError):
            archive.check(filing(label="AWARENESS"))

    def test_the_formats_are_the_ones_the_reference_names(self):
        # Pinned rather than parsed at runtime. formats.md is prose for a
        # person, and a parser over it would break on a rewrite that changed
        # nothing a consumer cares about; a test breaks only when the set
        # itself moves, which is exactly when this list has to.
        text = (REPO / "references" / "formats.md").read_text(encoding="utf-8")
        named = re.findall(r"^\| \*\*(.+?)\*\* \|", text, re.M)
        self.assertEqual(
            sorted(archive.FORMATS),
            sorted(name.lower().replace(" ", "-") for name in named))

    def test_the_labels_are_the_ones_the_reference_names(self):
        text = (REPO / "references" / "formats.md").read_text(encoding="utf-8")
        named = re.findall(r"^\| `([A-Z]+)` \|", text, re.M)
        self.assertEqual(sorted(archive.LABELS), sorted(set(named)))

    def test_the_states_are_the_ones_the_measure_contract_names(self):
        text = (REPO / "references" / "measure.md").read_text(encoding="utf-8")
        named = re.search(r"^state:\s*\w+\s*#\s*(.+)$", text, re.M).group(1)
        self.assertEqual(sorted(archive.STATES),
                         sorted(part.strip() for part in named.split("|")))

    def test_a_fresh_archive_starts_as_a_draft(self):
        self.assertEqual(filing().state, "draft")

    def test_only_the_three_states_of_the_measure_contract_are_taken(self):
        for good in archive.STATES:
            archive.check(filing(state=good))
        with self.assertRaises(archive.ArchiveError):
            archive.check(filing(state="posted"))

    def test_a_pillar_outside_the_three_is_refused(self):
        for wrong in (0, 4, -1, "two"):
            with self.assertRaises(archive.ArchiveError):
                archive.check(filing(pillar=wrong))


class TestTheFileItWrites(ArchiveCase):
    """The front matter of references/measure.md, the post, the signature
    concatenated rather than generated, then the session notes."""

    def composed(self, conversation=None, **kwargs):
        conversation = conversation or self.drafted()
        return archive.compose(conversation, filing(**kwargs),
                               signature=self.instance.signature())

    def test_every_measure_key_is_present(self):
        text = self.composed()
        block, _ = split_front_matter(text)
        self.assertIsNotNone(block)
        for key in ("date", "pillar", "format", "label", "hook", "chars",
                    "state", "published_ref", "measured",
                    "inbound_connections", "inbound_dms", "meeting_mentions",
                    "note"):
            self.assertRegex(block, rf"(?m)^{key}:")

    def test_the_measurement_fields_start_empty_because_j7_has_not_happened(self):
        text = self.composed()
        for key in ("measured", "inbound_connections", "inbound_dms",
                    "meeting_mentions"):
            self.assertRegex(text, rf"(?m)^{key}:\s*$")
        self.assertRegex(text, r'(?m)^note: ""$')

    def test_the_hook_is_the_first_line_of_the_post_verbatim(self):
        text = self.composed()
        self.assertIn("hook: |\n  Quatre mois a vendre aux agences.\n", text)

    def test_the_post_is_in_the_file_as_it_stands(self):
        self.assertIn(BODY, self.composed())

    def test_the_signature_is_concatenated_never_generated(self):
        text = self.composed()
        signature = self.instance.signature()
        self.assertTrue(signature)
        self.assertIn(BODY + "\n\n" + signature, text)

    def test_the_character_count_is_what_would_be_published(self):
        text = self.composed()
        published = BODY + "\n\n" + self.instance.signature()
        self.assertIn(f"chars: {len(published)}", text)

    def test_the_session_notes_are_marked_as_not_the_post(self):
        text = self.composed()
        self.assertIn("Session notes, not published:", text)
        # The seam is below the post, never inside it.
        self.assertGreater(text.index("Session notes"), text.index(BODY))

    def test_the_notes_name_the_interview_so_the_words_stay_findable(self):
        conversation = self.drafted()
        text = self.composed(conversation)
        self.assertIn(f"interviews/{conversation.id}", text)

    def test_the_notes_carry_the_sheet_the_person_signed(self):
        text = self.composed()
        self.assertIn("Le segment abandonne, avec ce qu'il a coute", text)
        self.assertIn("le canal direct est le seul qui paie", text)

    def test_the_notes_carry_the_anchors_and_no_verdict(self):
        text = self.composed()
        notes = text.split("Session notes, not published:")[1]
        self.assertIn("Onze conversations", notes)
        self.assertIn("quatre mois a vendre", notes)
        # No verdict is ever stored. They are recomputed from the transcript,
        # which is next to this file.
        for verdict in ("anchored", "fabricated", "dangling", "unanchored"):
            self.assertNotIn(verdict, notes)

    def test_the_notes_say_where_each_backing_lives(self):
        # The archive carries the provenance, so a post read in a year still
        # says whether a line was said or approved.
        notes = self.composed().split("Session notes, not published:")[1]
        self.assertIn("<- said: 'quatre mois a vendre'", notes)
        conversation = self.drafted(anchors=[
            {"post": "Onze conversations",
             "sheet": "le canal direct est le seul qui paie"}])
        notes = self.composed(conversation).split(
            "Session notes, not published:")[1]
        self.assertIn("<- sheet: 'le canal direct est le seul qui paie'", notes)

    def test_the_photo_ideas_and_tips_land_in_the_notes_not_in_the_post(self):
        conversation = self.drafted(
            photos=[{"kind": "portrait", "text": "Devant le tableau."}],
            tips=[{"kind": "lesson", "text": "Ouvrir sur le chiffre."}])
        text = self.composed(conversation)
        post, notes = text.split("Session notes, not published:")
        self.assertIn("Devant le tableau.", notes)
        self.assertIn("Ouvrir sur le chiffre.", notes)
        self.assertNotIn("Devant le tableau.", post)

    def test_what_the_writing_step_did_not_return_is_shown_as_missing(self):
        notes = self.composed().split("Session notes, not published:")[1]
        self.assertIn("portrait", notes)
        self.assertIn("lesson", notes)

    def test_the_revisions_are_named_because_they_are_what_was_said(self):
        conversation = self.drafted()
        interview.revise(conversation, "Ouvre sur le chiffre.", now=WHEN)
        self.assertIn("Ouvre sur le chiffre.", self.composed(conversation))

    def test_the_file_it_writes_reads_back_as_a_conformant_post(self):
        archive.archive(self.instance, self.drafted().id, filing(), now=WHEN)
        gaps = [gap for gap in self.instance.conformance()
                if gap.code.startswith("post-")]
        self.assertEqual(gaps, [])

    def test_nothing_is_archived_without_a_draft(self):
        conversation = interview.start(
            self.root, skill="linkedin-post", sections=("The interview",),
            interface_language="fr", output_language="fr",
            provider="anthropic", model="claude-opus-5", now=WHEN)
        with self.assertRaises(archive.ArchiveError):
            archive.compose(conversation, filing(), signature="")


class TestTheSignature(ArchiveCase):
    """Concatenated from profile.md, never generated. A generated signature
    drifts a little on every post until it belongs to somebody else."""

    def test_it_comes_out_of_the_fenced_block(self):
        signature = self.instance.signature()
        self.assertIn("Nadia Feriel", signature)
        self.assertNotIn("```", signature)

    def test_an_empty_section_means_no_signature(self):
        text = self.instance.read("profile.md")
        head, _, tail = text.partition("## Signature block")
        tail = tail[tail.index("\n## "):]
        self.instance.write("profile.md",
                            head + "## Signature block\n" + tail)
        self.assertEqual(self.instance.signature(), "")

    def test_an_absent_section_is_a_repair_not_a_signature(self):
        # references/instance.md: its absence means the migration was
        # incomplete, not that there is none. Archiving on that reading would
        # publish a post without a signature and call it a decision.
        text = self.instance.read("profile.md")
        self.instance.write("profile.md",
                            text.replace("## Signature block", "## Gone"))
        with self.assertRaises(InstanceError):
            self.instance.signature()

    def test_archiving_refuses_rather_than_dropping_it_in_silence(self):
        text = self.instance.read("profile.md")
        self.instance.write("profile.md",
                            text.replace("## Signature block", "## Gone"))
        with self.assertRaises(InstanceError):
            archive.archive(self.instance, self.drafted().id, filing(),
                            now=WHEN)


class TestWritingThePost(ArchiveCase):
    def test_the_file_lands_under_posts(self):
        conversation = self.drafted()
        done = archive.archive(self.instance, conversation.id, filing(), now=WHEN)
        self.assertEqual(done.filename, "2026-08-29-agences-quatre-mois.md")
        self.assertEqual(done.problems, ())
        self.assertTrue((self.root / "posts" / done.filename).is_file())

    def test_a_name_already_taken_stops_before_anything_is_written(self):
        conversation = self.drafted()
        (self.root / "posts" / "2026-08-29-agences-quatre-mois.md").write_text(
            "someone else's", encoding="utf-8")
        with self.assertRaises(archive.ArchiveError):
            archive.archive(self.instance, conversation.id, filing(), now=WHEN)
        self.assertEqual(
            (self.root / "posts" / "2026-08-29-agences-quatre-mois.md")
            .read_text(encoding="utf-8"), "someone else's")
        self.assertEqual(
            interview.load(self.root, conversation.id).state, interview.OPEN)

    def test_the_model_cannot_reach_this_directory(self):
        # posts/ is not in the writable set the tools hand a model, and this
        # step is the reason it does not need to be.
        from verbatim_app.instance import WRITABLE
        self.assertNotIn("posts", " ".join(WRITABLE))


class TestTheTwoWaysTheInstanceCanRefuse(ArchiveCase):
    """Two failures the step can meet, and they want two different screens.
    One is a file to repair; the other is a directory that will not take one."""

    def test_a_bank_that_will_not_decode_is_its_own_state(self):
        # Not "that angle is not in the bank": it is there and nobody can read
        # it, and a 404 on a file that exists sends people to the wrong fix.
        (self.root / "ideas.md").write_bytes(b"\xff\xfe not utf-8")
        with self.assertRaises(InstanceError) as caught:
            archive.archive(self.instance, self.drafted().id,
                            filing(idea="anything"), now=WHEN)
        self.assertIsInstance(caught.exception, UnreadableError)

    def test_a_bank_that_is_not_there_answers_the_same_question(self):
        (self.root / "ideas.md").unlink()
        with self.assertRaises(archive.ArchiveError) as caught:
            archive.archive(self.instance, self.drafted().id,
                            filing(idea="anything"), now=WHEN)
        self.assertEqual(str(caught.exception), "no-such-idea")

    def test_a_directory_that_will_not_take_the_file_is_not_a_slug_to_change(self):
        conversation = self.drafted()
        (self.root / "posts").chmod(0o555)
        try:
            with self.assertRaises(archive.ArchiveError) as caught:
                archive.archive(self.instance, conversation.id, filing(),
                                now=WHEN)
        finally:
            (self.root / "posts").chmod(0o755)
        self.assertEqual(str(caught.exception), "cannot-write")
        self.assertEqual(
            interview.load(self.root, conversation.id).state, interview.OPEN)


class TestWhenTheCloseItselfFails(ArchiveCase):
    """The one refusal where something already landed. Rare by the order of
    the writes, not impossible, and a screen that hid it would send somebody
    to archive again into a name that is now taken."""

    def test_the_post_stays_and_the_refusal_says_which_half_ran(self):
        conversation = self.drafted()
        home = interview.directory(self.root, conversation.id)
        home.chmod(0o555)
        try:
            with self.assertRaises(archive.ArchiveError) as caught:
                archive.archive(self.instance, conversation.id, filing(),
                                now=WHEN)
        finally:
            home.chmod(0o755)
        self.assertEqual(str(caught.exception), "closed-nothing")
        self.assertTrue((self.root / "posts"
                         / "2026-08-29-agences-quatre-mois.md").is_file())
        self.assertEqual(
            interview.load(self.root, conversation.id).state, interview.OPEN)


class TestClosingTheInterview(ArchiveCase):
    """`interview.close` gets its first caller here, which is what the
    validation sheet slice said it would be."""

    def test_the_interview_names_the_post_it_became(self):
        conversation = self.drafted()
        done = archive.archive(self.instance, conversation.id, filing(), now=WHEN)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.state, interview.CLOSED)
        self.assertEqual(again.post, f"posts/{done.filename}")

    def test_the_words_stay_where_they_are(self):
        conversation = self.drafted()
        archive.archive(self.instance, conversation.id, filing(), now=WHEN)
        again = interview.load(self.root, conversation.id)
        self.assertEqual(again.said(), conversation.said())
        self.assertTrue((interview.directory(self.root, conversation.id)
                         / interview.TRANSCRIPT).is_file())

    def test_a_closed_interview_is_not_archived_twice(self):
        conversation = self.drafted()
        archive.archive(self.instance, conversation.id, filing(), now=WHEN)
        with self.assertRaises(archive.ArchiveError):
            archive.archive(self.instance, conversation.id,
                            filing(slug="autre-chose"), now=WHEN)


class TestTheIdeaBank(ArchiveCase):
    """A session never closes leaving the bank poorer than it found it. The
    half that is mechanical is moving the consumed line into Used."""

    def test_the_consumed_idea_moves_into_used(self):
        conversation = self.drafted()
        angle = self.instance.ideas().angles[0]
        archive.archive(self.instance, conversation.id,
                        filing(idea=angle.text), now=WHEN)
        bank = self.instance.ideas()
        self.assertIn(angle.text[:40],
                      " ".join(used.angle for used in bank.used))
        self.assertNotIn(angle.text, [a.text for a in bank.angles])

    def test_the_used_line_names_the_file_it_became(self):
        conversation = self.drafted()
        angle = self.instance.ideas().angles[0]
        done = archive.archive(self.instance, conversation.id,
                               filing(idea=angle.text), now=WHEN)
        used = self.instance.ideas().used[-1]
        self.assertEqual(used.file, f"posts/{done.filename}")
        self.assertEqual(used.date, "2026-08-29")
        self.assertEqual(used.pillar, "P1")

    def test_no_idea_named_means_the_bank_is_left_alone(self):
        before = self.instance.read("ideas.md")
        archive.archive(self.instance, self.drafted().id, filing(), now=WHEN)
        self.assertEqual(self.instance.read("ideas.md"), before)

    def test_an_idea_that_is_not_in_the_bank_is_reported_not_invented(self):
        conversation = self.drafted()
        with self.assertRaises(archive.ArchiveError):
            archive.archive(self.instance, conversation.id,
                            filing(idea="something nobody wrote"), now=WHEN)

    def test_a_bank_that_cannot_be_written_does_not_undo_the_post(self):
        # Last on purpose: a line not moved is bookkeeping somebody repairs by
        # hand, and undoing a post that is already filed is not.
        conversation = self.drafted()
        angle = self.instance.ideas().angles[0]
        # The directory, not the file: atomic_write renames a temporary into
        # it, so a read only ideas.md is still replaceable.
        self.root.chmod(0o555)
        try:
            done = archive.archive(self.instance, conversation.id,
                                   filing(idea=angle.text), now=WHEN)
        finally:
            self.root.chmod(0o755)
        self.assertTrue((self.root / "posts" / done.filename).is_file())
        self.assertEqual(
            interview.load(self.root, conversation.id).state, interview.CLOSED)
        # Reported rather than raised, and reported as a code the pack names.
        self.assertEqual(done.problems, ("idea-not-moved",))


class TestThePostAloneComesBackOutOfTheFile(ArchiveCase):
    """The publishing step reads a file this module wrote, and what is below
    the seam is not the post. It is the sheet, every anchor pair, and every
    interview sentence backing one, which is the rawest material in the whole
    instance. Sending the file body would publish all of it."""

    def body_of(self, conversation=None):
        text = archive.compose(conversation or self.drafted(), filing(),
                               signature=self.instance.signature())
        _, body = split_front_matter(text)
        return body

    def test_the_post_comes_back_and_the_notes_do_not(self):
        conversation = self.drafted()
        only = archive.post_only(self.body_of(conversation))
        self.assertEqual(
            only, BODY + "\n\n" + self.instance.signature().strip())
        self.assertNotIn("Session notes", only)
        self.assertNotIn("Onze conversations, deux propositions, rien de "
                         "signe.'", only)  # the anchor pair, quoted

    def test_a_body_with_no_seam_comes_back_whole(self):
        # A post file written by hand, or by a version older than the notes.
        text = "A post.\n\nWith two paragraphs.\n"
        self.assertEqual(archive.post_only(text), text.strip())

    def test_a_rule_inside_the_post_does_not_cut_it_short(self):
        # The seam is the marker, never the horizontal rule above it: a post
        # is allowed to contain a line of dashes.
        conversation = self.drafted(body="Before.\n\n---\n\nAfter.")
        only = archive.post_only(self.body_of(conversation))
        self.assertIn("After.", only)
        self.assertNotIn("Session notes", only)


class TestTheOtherHalfOfTheSeam(ArchiveCase):
    """`notes_only` is `post_only` read from the other end, and it exists so
    that the screen showing both never cuts the file twice by two rules. The
    post screen stops being one block of text: the post as it would go out,
    and the notes, which are a list and get read as one."""

    def body_of(self, conversation=None):
        text = archive.compose(conversation or self.drafted(), filing(),
                               signature=self.instance.signature())
        _, body = split_front_matter(text)
        return body

    def test_the_notes_come_back_and_the_post_does_not(self):
        notes = archive.notes_only(self.body_of())
        self.assertIn("Angle:", notes)
        self.assertIn("Anchors offered", notes)
        self.assertNotIn(BODY, notes)
        self.assertNotIn(archive.NOTES_MARKER, notes)

    def test_a_body_with_no_seam_has_no_notes(self):
        # A post file written by hand. There is nothing under the seam
        # because there is no seam, which is not the same as empty notes on a
        # file that has one.
        self.assertEqual(archive.notes_only("A post.\n\nTwo paragraphs.\n"), "")

    def test_a_rule_inside_the_post_does_not_start_the_notes(self):
        notes = archive.notes_only(
            self.body_of(self.drafted(body="Before.\n\n---\n\nAfter.")))
        self.assertNotIn("After.", notes)
        self.assertIn("Angle:", notes)

    def test_the_two_halves_account_for_the_whole_file(self):
        """The property that makes them one seam rather than two rules. What
        is not in the post is in the notes, and nothing is in both."""
        body = self.body_of()
        post, notes = archive.post_only(body), archive.notes_only(body)
        self.assertIn(post, body)
        self.assertIn(notes, body)
        self.assertLess(body.index(post), body.index(notes))
        for line in notes.splitlines():
            if line.strip():
                self.assertNotIn(line, post)


if __name__ == "__main__":
    unittest.main(verbosity=2)
