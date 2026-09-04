"""The step where an interview becomes a post.

`skills/linkedin-post` opens its last section with the sentence this module
exists for: a post that stays a draft is not finished, and a batch of drafts
that never shipped is the most common way this whole system dies. Everything
before this file is a conversation; this is where it lands in `posts/` and
becomes something the measurement store can count.

Three writes, in the order `references/instance.md` fixes, shortest trap
first: the post file, the interview closed on its name, then the consumed
angle moved into the used section of the bank. The first two are the step;
the third is bookkeeping and is reported rather than allowed to undo them.

What the front matter needs and the draft does not carry, the pillar, the
format, the label and the slug, is the person's decision on their screen. None
of it is derivable from a body of text, and a value guessed here would be a
guess counted in every ratio the system reports afterwards.

No LLM instruction lives here, like everywhere under `app/`. The English in
the session notes is the same English as the file names and the front matter
keys: `references/instance.md` calls those the machine seam and keeps them
fixed, while the prose between them stays in whatever language somebody was
interviewed in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from . import interview
from .anchors import KEY_OF
#: `STATES` is the three states of `references/measure.md`, imported rather
#: than repeated: archiving starts a post at `draft` and the publishing step
#: moves it, so the vocabulary belongs to the module that owns the front
#: matter contract rather than to either step.
from .instance import (
    STATES, Instance, InstanceError, NameTaken, UnreadableError,
)

#: The formats of `references/formats.md`, slugged the way the example posts
#: spell them. Pinned by a test against the reference rather than parsed out of
#: it: the reference is prose for a person, and a parser over it would fail on
#: a rewrite that changed nothing a consumer cares about.
FORMATS = ("counter-intuitive-number", "the-breakdown", "the-post-mortem",
           "the-stance", "the-story")

#: The three objective labels, same file.
LABELS = ("VISIBILITY", "TRUST", "ACTION")

#: Three pillars, and the contract says three. A fourth index would be a post
#: filed against a pillar the ratio does not know about.
PILLARS = (1, 2, 3)

#: A slug addresses a file inside `posts/` and nothing else.
SLUG = re.compile(r"\A[a-z0-9]+(?:-[a-z0-9]+)*\Z")

#: The seam between the post and what the session left beside it. English, and
#: fixed: it is what a consumer looks for to know where the post stops.
NOTES_MARKER = "Session notes, not published:"

NOT_RETURNED = "not returned"


class ArchiveError(Exception):
    """The filing is not one, or the interview is not in a state to become a
    post. Its message names the code the language pack answers with."""


@dataclass(frozen=True)
class Filing:
    """What the person decided on the archive form.

    `idea` is the angle of the bank this post consumed, empty when none did:
    not every post starts from a line somebody wrote down.
    """
    date: str
    slug: str
    pillar: int
    format: str
    label: str
    state: str = "draft"
    idea: str = ""


@dataclass(frozen=True)
class Result:
    """What archiving did. `problems` holds the codes of what it could not
    finish and did not roll back, so a screen can say so in the pack's own
    words instead of pretending the step was clean."""
    filename: str
    problems: tuple = ()


def check(filing: Filing) -> Filing:
    """Refuse a filing that would name a file, a pillar or a state nobody can
    read back. Every message names a code, never a sentence: the sentence is
    in `locales/<lang>/app.yml` like every other one a person reads."""
    if not isinstance(filing.slug, str) or not SLUG.match(filing.slug):
        raise ArchiveError("bad-slug")
    try:
        parsed = datetime.strptime(filing.date, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ArchiveError("bad-date") from None
    if parsed.strftime("%Y-%m-%d") != filing.date:
        raise ArchiveError("bad-date")
    if filing.pillar not in PILLARS or isinstance(filing.pillar, bool):
        raise ArchiveError("bad-pillar")
    if filing.format not in FORMATS:
        raise ArchiveError("bad-format")
    if filing.label not in LABELS:
        raise ArchiveError("bad-label")
    if filing.state not in STATES:
        raise ArchiveError("bad-state")
    return filing


def filename(filing: Filing) -> str:
    return f"{filing.date}-{filing.slug}.md"


def published(conversation, signature: str = "") -> str:
    """The post as it would go out: the body, then the signature block after a
    blank line. Concatenated, never generated, which is the rule the skill
    states and the reason `signature` arrives as an argument here."""
    if conversation.draft is None:
        raise ArchiveError("no-draft")
    body = conversation.draft.body.strip()
    return body + ("\n\n" + signature.strip() if signature.strip() else "")


def compose(conversation, filing: Filing, *, signature: str = "") -> str:
    """The whole file: front matter, the post, then the session notes.

    The character count is of the post as it would be published, signature
    included, because that is what the platform counts and what `publish.py`
    refuses on. Counting the body alone would report a post as fitting and
    then have it bounce.
    """
    check(filing)
    if conversation.draft is None:
        raise ArchiveError("no-draft")
    text = published(conversation, signature)
    hook = _hook(conversation.draft.body)
    front = "\n".join([
        "---",
        f"date: {filing.date}",
        f"pillar: {filing.pillar}",
        f"format: {filing.format}",
        f"label: {filing.label}",
        "hook: |",
        *(f"  {line}" for line in hook.splitlines()),
        f"chars: {len(text)}",
        f"state: {filing.state}",
        'published_ref: ""',
        "measured:",
        "inbound_connections:",
        "inbound_dms:",
        "meeting_mentions:",
        'note: ""',
        "---",
    ])
    return "\n".join([front, "", text, "", "---", "", NOTES_MARKER, "",
                      _notes(conversation), ""])


def post_only(body: str) -> str:
    """The post, cut out of a post file's body at the session notes seam.

    Publishing reads a file this module wrote, and everything below the seam
    is emphatically not the post: the sheet, every anchor the engine claimed
    and the interview sentence backing each one, which is the rawest material
    an instance holds. A tier handed the file body would put all of it in a
    feed.

    Cut at the marker, never at the rule above it: a post is allowed to
    contain a line of dashes, and `NOTES_MARKER` is the seam the contract
    fixes. The first occurrence wins, so a post that somehow contained the
    marker itself publishes less rather than publishing notes.

    A body with no seam comes back whole. That is a post file written by hand
    or by a version older than the notes, and refusing it would be refusing to
    publish somebody's own file over a section this module invented.
    """
    if NOTES_MARKER not in body:
        return body.strip()
    post = body.split(NOTES_MARKER, 1)[0].rstrip()
    return re.sub(r"\n-{3,}\s*\Z", "", post).strip()


@dataclass(frozen=True)
class Shape:
    """What a post is, structurally. Three numbers, no verdict."""
    paragraphs: int
    characters: int
    #: How much of `characters` is the tail every post carries. Zero when
    #: this post does not end on the signature it was handed.
    signature: int


def shape(body: str, signature: str = "") -> Shape:
    """How many paragraphs, how long, and how much of that is the signature.

    Over the published post alone. `post_only` is what a reader gets, and
    counting the session notes under it would report a length nobody reads.

    The signature is measured by finding it at the end rather than by
    trusting the instance to still hold the one this post was archived with.
    A signature rewritten last month does not retroactively change the shape
    of a post published before it, and a screen saying it did would be
    inviting somebody to shorten a post over characters that are not there.
    """
    text = post_only(body).strip()
    tail = signature.strip()
    return Shape(
        paragraphs=len([block for block in re.split(r"\n\s*\n", text)
                        if block.strip()]),
        characters=len(text),
        signature=len(tail) if tail and text.endswith(tail) else 0)


def notes_only(body: str) -> str:
    """What the session left beside the post, cut at the same seam.

    The other end of `post_only`, and here rather than in a screen so that
    the file is cut once by one rule. A screen that split it itself would be
    a second definition of where a post stops, and the two would drift the
    day the marker moves.

    The marker line goes with the cut: it is the seam, not a heading. A body
    with no seam has no notes at all, which is not the same as a file whose
    notes are empty, and neither is a state to invent one for.
    """
    if NOTES_MARKER not in body:
        return ""
    return body.split(NOTES_MARKER, 1)[1].strip()


def archive(instance: Instance, interview_id: str, filing: Filing, *,
            now: datetime | None = None) -> Result:
    """File the post, close the interview, move the idea. In that order.

    The interview is named rather than handed over, and read from disk here.
    A caller holding a copy from before the click would archive what it read:
    a draft that has since been rewritten, or an interview another tab has
    already turned into a post, filing the same words twice under two names.

    The order is the recovery story and it runs shortest trap first. Closing
    an interview onto a file that is not there is the worst of the three, so
    the file goes down first. Leaving it open after the file exists is the
    second worst, because a second attempt then collides with a name already
    taken and somebody is stuck between two half states. The bank comes last
    because a line not moved is ten seconds of hand editing, and undoing a
    post that is already filed is not.
    """
    check(filing)
    conversation = interview.load(instance.root, interview_id)
    if conversation.draft is None:
        raise ArchiveError("no-draft")
    if conversation.state != interview.OPEN:
        # Already a post. Archiving again would file a second one under a
        # second name from the same words, and both would count.
        raise ArchiveError("already-closed")
    if filing.idea:
        # Checked before anything is written: an angle the bank does not hold
        # is a stale page or a bug, and neither is worth a post filed against
        # a line nobody can find afterwards. A bank that is not there answers
        # the same question the same way, and says so with the same sentence;
        # a bank that will not parse is a different screen and travels on.
        try:
            known = [angle.text for angle in instance.ideas().angles]
        except UnreadableError:
            raise
        except InstanceError:
            raise ArchiveError("no-such-idea") from None
        if filing.idea not in known:
            raise ArchiveError("no-such-idea")
    # Raises when the section is gone, which is a profile to repair rather
    # than a signature to do without. Before the write, so a repair costs
    # nothing but the click. `UnreadableError` travels on to its own screen:
    # a profile that is there and will not decode is not a section to add.
    signature = instance.signature()
    name = filename(filing)
    try:
        instance.write_post(name, compose(conversation, filing,
                                          signature=signature))
    except NameTaken:
        # A filing decision, fixed on the form.
        raise ArchiveError("name-taken") from None
    except InstanceError:
        # A disk that will not take the file. Its own code, because the fix is
        # nothing the person can type into this form, and answering it with a
        # sentence about their profile would send them to the wrong file.
        raise ArchiveError("cannot-write") from None
    try:
        interview.close(instance.root, conversation.id, f"posts/{name}",
                        now=now)
    except (interview.InterviewError, OSError):
        # The post is on disk and the interview is not closed on it: the half
        # state the order above is arranged to make rare rather than
        # impossible. It gets its own code because it is the one refusal where
        # something already landed, and a screen that only said "it did not
        # work" would send somebody to archive again into a name now taken.
        raise ArchiveError("closed-nothing") from None
    problems = []
    if filing.idea:
        try:
            instance.use_idea(filing.idea, date=filing.date,
                              file=f"posts/{name}")
        except (InstanceError, OSError):
            problems.append("idea-not-moved")
    return Result(filename=name, problems=tuple(problems))


# ------------------------------------------------------------- the two halves

def _hook(body: str) -> str:
    """The first line as published, which is the first paragraph: a hook
    wrapped over two lines is one hook, and the front matter block scalar is
    the shape `references/measure.md` writes it in."""
    paragraph = []
    for line in body.strip().splitlines():
        if not line.strip():
            break
        paragraph.append(line.strip())
    return "\n".join(paragraph)


def _notes(conversation) -> str:
    """What the session leaves beside the post.

    A summary of somebody's words, never a replacement: the interview
    directory keeps the words themselves and the first line here says where.

    No verdict is written down. Anchored, fabricated and dangling are
    recomputed from the body, the anchors and the transcript every time
    anybody looks, and a verdict filed here would be a second source of truth
    that stops being true the moment one of the three moves. What is filed is
    the pairs the engine offered, which is the material the verdict is
    computed from.
    """
    draft, sheet = conversation.draft, conversation.sheet
    lines = [f"- Interview: {interview.DIRECTORY}/{conversation.id}, "
             "kept as it is."]
    if sheet is not None:
        lines += [f"- Angle: {sheet.angle}",
                  f"- Central conviction: {sheet.conviction}",
                  f"- The strong moment: {sheet.moment}"]
        if sheet.elements:
            lines.append("- Concrete elements:")
            lines += [f"  - {element}" for element in sheet.elements]
    lines.append("- Anchors offered, the claim then the line backing it, "
                 "marked with where that line lives: said, the interview; "
                 "sheet, the approved sheet. No verdict is filed here: it is "
                 "recomputed from the interview next to this file.")
    if draft.anchors:
        lines += [f"  - {anchor.fragment!r} <- {KEY_OF[anchor.provenance]}: "
                  f"{anchor.quote!r}"
                  for anchor in draft.anchors]
    else:
        lines.append(f"  - {NOT_RETURNED}")
    lines += _kinds("Photo ideas", draft.photos, interview.PHOTO_KINDS)
    lines += _kinds("Tips", draft.tips, interview.TIP_KINDS)
    if draft.problems:
        lines.append("- Could not be read in the way this draft arrived:")
        lines += [f"  - {problem}" for problem in draft.problems]
    if conversation.revisions:
        lines.append("- Asked for after the first draft:")
        lines += [f"  - {revision.text}" for revision in conversation.revisions]
    return "\n".join(lines)


def _kinds(heading: str, notes, kinds) -> list:
    """One line per kind the skill asks for, present or not.

    What did not arrive is written as not returned rather than left out. A
    list that silently holds one of two reads as a complete answer, and
    nobody asks again for a thing they were never told was missing.
    """
    by_kind = {note.kind: note.text for note in notes}
    return [f"- {heading}:"] + [
        f"  - {kind}: {by_kind.get(kind, NOT_RETURNED)}" for kind in kinds]
