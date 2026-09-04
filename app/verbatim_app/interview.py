"""Where an interview lives between two turns.

An interview in progress is per instance state, so `references/instance.md`
carries it before this file does: `interviews/<id>/`, one directory each,
holding `conversation.json` and `transcript.md`. Read that section first, it
is the contract and this is only its implementation.

Two things are worth restating here, because they are the reasons the format
looks the way it does.

**The JSON is the truth, the markdown is a rendering.** A tool call carries an
id the next request has to echo back, and a markdown round trip that loses it
produces a conversation the provider rejects. So the wire shaped message list
is stored as it is, and `transcript.md` is written from it on every save and
never read back. When the two disagree, the JSON is right, exactly as `posts/`
is right against any view computed over it.

**Roles come from structure, never from headings.** What the person said is
read off the message list, where the person's turns and a tool's answers are
different shapes even though both travel on a user role message. A model that
writes `## Said` into its own answer is writing text, not becoming somebody.
That matters because this is the file anchoring checks a quote against, and a
source a model can forge is not a source.

Standard library only, like the rest of the engine seam.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

#: The two provenances travel under other names here: `TRANSCRIPT` is a
#: file name in this module, and the file is a rendering, never a source.
from .anchors import (
    Anchor, KEYS, KEY_OF, SHEET as FROM_SHEET, TRANSCRIPT as FROM_TRANSCRIPT,
    contains, verify,
)
from .instance import atomic_write
from .passages import (
    PassageGone, passage_at, passages_of, replace_passage,
)
from .providers import Usage
from .shown import shown

#: Bumped when the stored shape changes in a way a reader has to know about.
VERSION = 1

DIRECTORY = "interviews"
CONVERSATION = "conversation.json"
TRANSCRIPT = "transcript.md"

OPEN = "open"
CLOSED = "closed"

#: The validation sheet's two states. `proposed` is replaceable, `approved`
#: is frozen, and only a person's click ever writes the second one.
PROPOSED = "proposed"
APPROVED = "approved"

#: What one moment of a conversation is, once the wire shape is read for what
#: it means. `said` and `asked` are people talking; `call` and `result` are the
#: engine reaching for a file. The screen shows all four, the transcript keeps
#: the first two, and anchoring reads `said` alone.
SAID, ASKED, CALL, RESULT = "said", "asked", "call", "result"

#: What the writing step is asked for beside the post itself. The skill names
#: two photo ideas, a staged portrait and a visual of the number or object, and
#: three tips: the strong message, the weak spot and the lesson. Kinds rather
#: than positions, so a partial answer says which half arrived.
PHOTO_KINDS = ("portrait", "visual")
TIP_KINDS = ("strong", "weak", "lesson")

#: The step of the bundle this screen drives. Structure, not text: the app
#: names which part of the skill applies here, the skill holds every word.
#: A section renamed in `skills/` fails the test that pins these names rather
#: than reaching somebody's first question.
STEP_SKILL = "linkedin-post"
STEP_SECTIONS = ("Before anything", "The interview",
                 "The break: format and angle", "The validation sheet")

#: The step that writes. Its own list, because drafting is its own request:
#: the skill says a revision restarts from the interview material rather than
#: rewriting blind, so the engine builds that request from `material` every
#: time instead of appending to the conversation the questions happened in.
DRAFT_SECTIONS = ("Before anything", "Writing", "The deterministic pass",
                  "Hard rules")

#: What a rewrite reads on top of them. The skill's `Revisions` section holds
#: the rule it says is the one usually forgotten, that the sheet still applies
#: and a revision can smuggle an invented detail in behind it. It is not sent
#: on a first draft: the same section tells the model to offer five ways in
#: when a revision is asked for without saying what, which on a first draft is
#: an instruction to produce a menu instead of a post.
REVISION_SECTION = "Revisions"

#: The section a rewrite confined to one block is assembled with. It
#: says what the turn may touch, and the tool behind it can touch
#: nothing else anyway: the span is the guarantee, this is the
#: sentence that stops a model wasting a turn rewriting the rest.
PASSAGE_SECTION = "Rewriting one passage"

#: The contract's name format, and the whole path guard: an id that is not a
#: timestamp cannot address anything, inside this directory or out of it.
ID = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}(?:-[0-9]+)?\Z")

#: A skill name is a directory under the bundle, so it is checked like an id.
SKILL_NAME = re.compile(r"\A[a-z0-9][a-z0-9-]{0,63}\Z")

ID_STAMP = "%Y-%m-%d-%H%M"
STAMP = "%Y-%m-%dT%H:%M:%S"

#: How many unanswered revision requests a writing turn is handed at once.
#: One is the normal case, two after a refusal. Past that, turns have been
#: failing and the block would grow without bound inside a context window
#: this project already has to watch.
MOST_PENDING = 4


class InterviewError(Exception):
    pass


class DraftChanged(InterviewError):
    """The draft on disk is not the draft the screen was showing. Its own
    class rather than a message, for the same reason `SheetChanged` is one:
    the screen answering it has a sentence to say and a page to redraw."""


class SheetChanged(InterviewError):
    """The sheet on disk is not the sheet the person read. Its own type
    because the answer is a different screen: read again, then decide."""


# ------------------------------------------------------------------ the state

@dataclass
class Sheet:
    """The validation sheet, `references/instance.md` under interviews/.

    The five fields are the skill's, spelled the same. The guard is `state`:
    nothing drafts until it is `approved`, a `proposed` sheet is replaced by
    the next proposal, an `approved` one is frozen. Approving is the person's
    click on their screen, which is why nothing in `propose` can write it.
    """
    angle: str
    elements: tuple
    moment: str
    conviction: str
    first_lines: tuple
    state: str = PROPOSED
    proposed: str = ""
    approved: str = ""
    #: What could not be read in the way this sheet arrived. Empty when it
    #: came through the tool; a runtime that answered in prose fills it. The
    #: person signing this is entitled to know which of the two is in front
    #: of them, since a sheet parsed out of free text is the weaker object.
    problems: tuple = ()

    def digest(self) -> str:
        """What identifies this sheet: its content, nothing else.

        An approval must sign the sheet the person read, and the form that
        carries the click can be older than the disk: a turn still streaming
        can replace a proposed sheet behind a screen already drawn. So the
        page carries this digest and `approve` refuses a mismatch. Content
        only, no timestamp: two proposals with the same five fields are the
        same decision, and a turn can propose twice inside one second.
        """
        # `problems` is deliberately out: it says how this sheet arrived, not
        # what it says. The same five fields are the same decision whichever
        # road they came down, and a digest that moved with the road would
        # invalidate a signature over nothing the person can see.
        payload = json.dumps(
            [self.angle, list(self.elements), self.moment, self.conviction,
             list(self.first_lines)], ensure_ascii=False)
        return shown(payload)

    def text(self) -> str:
        """The sheet as words a quote can be looked for in: the five fields,
        one line each, the two lists one line per entry. What the person
        approved, whole, and nothing that was not on that screen. This is the
        source a `SHEET:` quote is checked against, and only once the sheet
        is approved: `sources` decides that, not this method."""
        return "\n".join([self.angle, *self.elements, self.moment,
                          self.conviction, *self.first_lines])


@dataclass(frozen=True)
class Note:
    """One photo idea or one tip: what it is, and what it says.

    Keyed by kind rather than by position because these arrive incomplete. A
    list of two strings cannot say which of the two ideas is missing, and a
    screen that has to guess shows the wrong label half the time.
    """
    kind: str
    text: str


@dataclass(frozen=True)
class Revision:
    """One request the person made once a draft existed.

    Their words, which is the whole of it: `references/instance.md` says why
    this joins the `Said` side and what that costs.
    """
    text: str
    asked: str = ""
    #: The block of the post this request is about, when it is about one.
    #: Two keys because each answers a different question: the index says
    #: which block, and it is the only thing separating two that read alike;
    #: the digest says the screen was not stale. Empty and -1 mean the
    #: request is about the post, which is what every request used to be.
    passage: str = ""
    passage_index: int = -1

    @property
    def scoped(self) -> bool:
        return bool(self.passage) and self.passage_index >= 0


@dataclass(frozen=True)
class Draft:
    """The post the engine wrote, and the anchors it claims for it.

    No verdict is stored beside them. Anchored, fabricated and dangling are
    read off `body`, `anchors` and the transcript by `checked`, every time
    somebody looks: a stored verdict stops being true the moment any of the
    three moves, and it goes stale in the direction that flatters the engine.
    """
    body: str
    anchors: tuple = ()
    #: The two photo ideas and the three tips, when they arrived. Not the
    #: post and never concatenated into it: archiving files them under the
    #: post's session notes, which is where the contract puts them.
    photos: tuple = ()
    tips: tuple = ()
    #: What could not be read in the way this draft arrived. Empty when it
    #: came through the tool; a runtime that answered in prose fills it.
    problems: tuple = ()
    written: str = ""
    #: When this body was put back in front, on a version somebody went back
    #: to. `written` still says when the engine wrote it, because it did, and
    #: this says when it became the draft again. Both, because `_pending`
    #: reads one of them and the screen reads the other: going back moves the
    #: draft's stamp backwards in time, and a single stamp would hand the
    #: next turn the very request whose answer was just thrown away.
    restored: str = ""

    @property
    def since(self) -> str:
        """The stamp anything asking what came after this draft compares to.

        The later of the two, and a plain `max` over strings works because
        `STAMP` is fixed width and orders lexically, which is the property
        `_pending` already relies on.
        """
        return max(self.written, self.restored)


@dataclass
class Conversation:
    id: str
    skill: str
    sections: tuple
    interface_language: str
    output_language: str
    provider: str
    model: str
    started: str
    updated: str
    state: str = OPEN
    post: str = ""
    usage: Usage = field(default_factory=Usage)
    #: Dollars, accumulated turn by turn at the rate of the model that ran
    #: that turn. None the moment one turn had no price: a total that silently
    #: drops a turn is worse than no total, and applying today's rate to
    #: yesterday's turns is worse still.
    spent: float | None = 0.0
    sheet: Sheet | None = None
    draft: Draft | None = None
    #: The drafts this one replaced, oldest first. Not a log: it is what
    #: `revert` walks back through, and what says which version is on screen.
    #: The engine's words rather than the person's, so nothing here is an
    #: anchoring source and `said` does not read it.
    earlier: list = field(default_factory=list)
    #: Append only, and written by a person's click alone. Part of what they
    #: said, which is why `said` reads it and the transcript renders it.
    revisions: list = field(default_factory=list)
    messages: list = field(default_factory=list)

    # -- what the person said, and nothing else

    def person_turns(self) -> list:
        return [moment.text for moment in timeline(self) if moment.kind == SAID]

    def said(self) -> str:
        """The anchoring source: every word the person typed, and no other.

        Their revision requests included. Same person, same screen, same
        keyboard as every interview answer, so a correction typed there is
        material a redraft may quote. What this rules out is the engine
        writing here, and no path does.
        """
        return "\n\n".join(
            self.person_turns()
            + [revision.text for revision in self.revisions])

    def engine_turns(self) -> list:
        return [moment.text for moment in timeline(self) if moment.kind == ASKED]


@dataclass(frozen=True)
class Entry:
    """One line of the interview list. `unreadable` is not an error state to
    hide: a directory whose conversation file no longer parses is still
    somebody's, and they get to see it and discard it."""
    id: str
    state: str = OPEN
    updated: str = ""
    turns: int = 0
    opening: str = ""
    unreadable: bool = False


@dataclass(frozen=True)
class Moment:
    kind: str
    text: str = ""
    name: str = ""
    call_id: str = ""
    arguments: dict = field(default_factory=dict)
    is_error: bool = False


def timeline(conversation: Conversation) -> list:
    """The conversation as a reader meets it, in order.

    This is the one place that decides who said what, and it decides it from
    the shape of each block rather than from anything written inside one. On a
    user role message the two travel together: a `tool_result` block is a tool
    answering and is never credited to anybody, while a `text` block is the
    person, because `say` is the only thing in this engine that writes one and
    nothing a model can reach calls it. Crediting the block rather than the
    message is what lets an answer typed after an interrupted tool call be kept
    without the tool's output being kept with it.
    """
    found = []
    for message in conversation.messages:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            if content.strip():
                found.append(Moment(SAID if role == "user" else ASKED,
                                    text=content))
            continue
        if not isinstance(content, list):
            continue
        blocks = [block for block in content if isinstance(block, dict)]
        if role == "user":
            for block in blocks:
                if block.get("type") == "tool_result":
                    found.append(Moment(RESULT,
                                        text=_as_text(block.get("content")),
                                        call_id=str(block.get("tool_use_id", "")),
                                        is_error=bool(block.get("is_error"))))
        text = "\n\n".join(block.get("text", "") for block in blocks
                            if block.get("type") == "text"
                            and block.get("text", "").strip())
        if text.strip():
            found.append(Moment(SAID if role == "user" else ASKED, text=text))
        for block in blocks:
            if block.get("type") == "tool_use":
                found.append(Moment(CALL, name=str(block.get("name", "")),
                                    call_id=str(block.get("id", "")),
                                    arguments=block.get("input") or {}))
    return found


def _as_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(block.get("text", "") for block in value
                          if isinstance(block, dict))
    return "" if value is None else str(value)


# ------------------------------------------------------------------- the disk

def _safe_id(candidate: str) -> str:
    if not isinstance(candidate, str) or not ID.match(candidate):
        raise InterviewError(
            f"{candidate!r} is not an interview id; they are timestamps, "
            "as in 2026-08-28-1432")
    return candidate


def _home(instance_root) -> Path:
    home = Path(instance_root) / DIRECTORY
    # A link, for the same reason as `directory` one level down: discard is an
    # rmtree and a linked home points it anywhere. A regular file for a duller
    # reason: mkdir then raises FileExistsError, which is a traceback rather
    # than the screen this state deserves.
    if home.is_symlink() or (home.exists() and not home.is_dir()):
        raise InterviewError(f"{DIRECTORY}/ is not a directory")
    return home


def directory(instance_root, interview_id: str) -> Path:
    path = _home(instance_root) / _safe_id(interview_id)
    if path.is_symlink():
        # The id names a directory inside the instance. A link wearing a
        # timestamp for a name passes the pattern and then points anywhere,
        # which matters most on the way out: discard is an rmtree.
        raise InterviewError(
            f"{interview_id} is a link, not an interview directory")
    return path


def say(conversation: Conversation, text: str) -> None:
    """Append what the person typed. Nothing else ever writes a user turn.

    When the previous turn never got its answer, which is the whole failure
    mode this screen is built around, the words join that turn instead of
    starting a second one. Two user messages in a row is a conversation the
    provider rejects, and it is the shape a retry after a failed turn would
    otherwise leave behind: a person retyping would brick their own interview.
    """
    text = (text or "").strip()
    if not text:
        raise InterviewError("an empty answer is not an answer")
    block = {"type": "text", "text": text}
    pending = conversation.messages[-1] if conversation.messages else None
    if pending is not None and pending.get("role") == "user":
        if isinstance(pending.get("content"), str):
            # A shape this engine never writes, and a file people hand edit.
            # Normalising it beats appending after it, which is the one thing
            # a provider refuses.
            pending["content"] = [{"type": "text", "text": pending["content"]}]
        # After tool results, which is where the loop leaves an interrupted
        # turn: the text goes last, since a tool result leads its message.
        # A content that is neither a list nor a string cannot get here: the
        # engine never writes one and `_build` refuses to load one.
        pending["content"].append(block)
        return
    conversation.messages.append({"role": "user", "content": [block]})


def _sheet_line(arguments: dict, name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InterviewError(f"the sheet needs {name!r}, a non-empty string")
    return value.strip()


def _sheet_lines(arguments: dict, name: str, most: int = 0) -> tuple:
    value = arguments.get(name)
    if not isinstance(value, list) or not value or not all(
            isinstance(entry, str) and entry.strip() for entry in value):
        raise InterviewError(
            f"the sheet needs {name!r}, a non-empty list of non-empty strings")
    if most and len(value) > most:
        raise InterviewError(f"{name!r} takes at most {most} entries")
    return tuple(entry.strip() for entry in value)


def propose(conversation: Conversation, arguments: dict, *, problems=(),
            now: datetime | None = None) -> Sheet:
    """The engine's half of the sheet: propose, never decide.

    Raised messages address the model, because they travel back as the tool
    result. A proposal on a conversation whose sheet is already approved is
    refused rather than replacing it: the approved sheet is what the person
    signed, and the guard would be worth nothing if the next turn could swap
    what sits under their signature.

    `problems` is the caller's and never the model's, keyword only for that
    reason alone, exactly as it is on `write`. It says what could not be read
    in the way this sheet arrived, and a model that could fill it would be
    narrating its own reception on the one screen built to doubt it.
    """
    if conversation.state != OPEN:
        raise InterviewError(
            "this interview is closed; nothing about it changes any more")
    if conversation.sheet is not None and conversation.sheet.state == APPROVED:
        raise InterviewError(
            "the sheet of this interview is approved and frozen; "
            "it cannot be replaced")
    sheet = Sheet(
        angle=_sheet_line(arguments, "angle"),
        elements=_sheet_lines(arguments, "elements"),
        moment=_sheet_line(arguments, "moment"),
        conviction=_sheet_line(arguments, "conviction"),
        first_lines=_sheet_lines(arguments, "first_lines", most=2),
        problems=tuple(problems),
        proposed=(now or datetime.now()).strftime(STAMP))
    conversation.sheet = sheet
    return sheet


def approve(conversation: Conversation, digest: str,
            now: datetime | None = None) -> bool:
    """The person's half: freeze the sheet. Returns whether anything changed,
    so a double click is a repeat of the same decision, not an error. The
    caller saves; approval is not worth anything until it is on disk.

    `digest` is the identity of the sheet as the person read it, required
    positionally so no caller can approve blind: a proposal can replace the
    sheet between the screen being drawn and the click landing, and the party
    writing replacements is the model, the very party the sheet guards
    against. A signature that can land on unread text is not a signature.
    """
    if conversation.state != OPEN:
        raise InterviewError(
            f"interview {conversation.id} is closed; its sheet is settled")
    if conversation.sheet is None:
        raise InterviewError(
            f"interview {conversation.id} has no sheet to approve")
    if digest != conversation.sheet.digest():
        raise SheetChanged(
            f"the sheet of {conversation.id} is not the one this approval "
            "was read from")
    if conversation.sheet.state == APPROVED:
        return False
    conversation.sheet.state = APPROVED
    conversation.sheet.approved = (now or datetime.now()).strftime(STAMP)
    return True


def sheet_approved(conversation: Conversation) -> bool:
    """The guard every consumer asks about: no interview turn runs past an
    approved sheet, and nothing drafts before one."""
    return (conversation.sheet is not None
            and conversation.sheet.state == APPROVED)


def _anchor_pairs(arguments: dict) -> tuple:
    """The anchors of a proposal, refused whole rather than half read.

    An empty list is fine and is not a slip: `references/anchoring.md` says a
    claim with nothing to back it stays bare, and an engine that demanded a
    pair per claim would be asking a weak model to decorate.

    Each pair names where its quote lives by the key it travels under, `said`
    for the interview sentence or `sheet` for a line of the approved sheet.
    One of the two, never both and never neither: a pair naming no source
    could only be checked against a guess, and a pair naming two would be
    checked against whichever one flattered it.
    """
    entries = arguments.get("anchors", [])
    if not isinstance(entries, list):
        raise InterviewError(
            "'anchors' is a list of {post, said} or {post, sheet} pairs, "
            "or absent")
    found = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise InterviewError(
                "each anchor is a {post, said} or {post, sheet} pair")
        named = [key for key in KEYS if key in entry]
        if len(named) != 1:
            raise InterviewError(
                "each anchor names one backing beside 'post': 'said', the "
                "interview sentence, or 'sheet', a line of the approved "
                "sheet; never both and never neither")
        fragment, quote = entry.get("post"), entry.get(named[0])
        if not isinstance(fragment, str) or not fragment.strip() \
                or not isinstance(quote, str) or not quote.strip():
            raise InterviewError(
                "each anchor needs 'post', a fragment of the draft, and "
                f"'{named[0]}', the line backing it quoted word for word, "
                "both non-empty")
        found.append(Anchor(fragment=fragment.strip(), quote=quote.strip(),
                            provenance=KEYS[named[0]]))
    return tuple(found)


def _notes(arguments: dict, name: str, kinds: tuple) -> tuple:
    """The photo ideas or the tips of a proposal, refused whole or not at all.

    Absent is fine and is the documented bargain: the skill asks the writing
    step for eight things and a small runtime returns some of them, so a
    missing photo idea does not cost the post. Malformed is refused, like a
    half read anchor, because the refusal travels back as the tool result and
    a model that sent nonsense gets to send it again.
    """
    entries = arguments.get(name, [])
    if not isinstance(entries, list):
        raise InterviewError(
            f"{name!r} is a list of {{kind, text}} entries, or absent")
    found, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise InterviewError(f"each entry of {name!r} is a {{kind, text}}")
        kind, text = entry.get("kind"), entry.get("text")
        if kind not in kinds:
            raise InterviewError(
                f"the 'kind' of a {name!r} entry is one of "
                + ", ".join(kinds))
        if not isinstance(text, str) or not text.strip():
            raise InterviewError(
                f"each entry of {name!r} needs 'text', a non-empty string")
        if kind in seen:
            # One of each. A kind offered twice is padding, and the screen
            # labels by kind, so the second one would overwrite the first.
            raise InterviewError(f"{kind!r} is offered twice in {name!r}")
        seen.add(kind)
        found.append(Note(kind=kind, text=text.strip()))
    return tuple(found)


def write(conversation: Conversation, arguments: dict, *, problems=(),
          now: datetime | None = None) -> Draft:
    """The engine's draft, offered the way the sheet is proposed.

    Refused before the sheet is approved, which is the whole point of the
    sheet: the skill says nothing is written until it is signed, and this is
    where that sentence becomes a machine. Raised messages address the model,
    since they travel back as the tool result.

    `problems` is the caller's, never the model's, and it is a keyword for
    that reason alone. It says what could not be read in the way this draft
    arrived, so a model that could write it would be narrating its own
    reception, in a panel headed by what the engine failed to understand.
    """
    if conversation.state != OPEN:
        raise InterviewError(
            "this interview is closed; nothing about it changes any more")
    if not sheet_approved(conversation):
        raise InterviewError(
            "the validation sheet of this interview is not approved yet, so "
            "nothing is drafted; propose a sheet and wait for the person")
    body = arguments.get("body")
    if not isinstance(body, str) or not body.strip():
        raise InterviewError(
            "the draft needs 'body', the post as it would be published")
    draft = Draft(body=body.strip(), anchors=_anchor_pairs(arguments),
                  photos=_notes(arguments, "photos", PHOTO_KINDS),
                  tips=_notes(arguments, "tips", TIP_KINDS),
                  problems=tuple(problems),
                  written=(now or datetime.now()).strftime(STAMP))
    _keep_version(conversation)
    conversation.draft = draft
    return draft


def write_passage(conversation: Conversation, arguments: dict, *, scope=None,
                  problems=(), now: datetime | None = None) -> Draft:
    """The engine's rewrite of one block, spliced into the draft.

    The guarantee this exists for is that every other byte of the post is
    where it was, and it is a guarantee by construction: the span comes from
    `passages.py`, the tool hands back that block alone, and nothing here
    can reach the rest of the body even if the model wrote a whole post into
    the field.

    Refused when nothing said which block. A tool meant for a passage,
    landing on a conversation with no scope, would be a post replaced by a
    fragment of itself, which is the loudest possible way to lose somebody's
    work.

    Anchors are merged rather than replaced. Every pair whose fragment is
    still somewhere in the post keeps backing what it backed; the pairs that
    were quoting the old block are dropped, since their fragment is gone and
    a stored pair pointing at nothing reads as dangling on every future
    look. What the model offers for the new block is added to those.

    Still somewhere means `anchors.contains`, which is the engine's one
    answer to that question and the one the panel paints with: it folds
    typography, whitespace and case. A plain `in` here would have been a
    second answer, and the two disagree exactly where it hurts. A fragment
    stored with a straight apostrophe against a post carrying a curly one
    is shown as backing its claim on every read, and would have been thrown
    away here, on a block nobody asked to change, silently and on disk.
    """
    if conversation.state != OPEN:
        raise InterviewError(
            "this interview is closed; nothing about it changes any more")
    if not sheet_approved(conversation):
        # Its sibling `write` has this guard and this had none. Unreachable
        # through the route today, which re-checks under the lock, and that
        # is exactly the argument that stops being true the day somebody
        # calls this from somewhere else.
        raise InterviewError(
            "the validation sheet of this interview is not approved yet, so "
            "nothing is drafted; propose a sheet and wait for the person")
    block = scope
    if block is None:
        raise InterviewError(
            "nothing said which passage this rewrites; a request has to name "
            "the block it is about before one can be rewritten on its own")
    written = arguments.get("passage")
    if not isinstance(written, str) or not written.strip():
        raise InterviewError(
            "the rewrite needs 'passage', the block as it should now read")
    try:
        body = replace_passage(conversation.draft.body, block, written)
    except PassageGone as gone:
        raise InterviewError(str(gone)) from None
    kept = tuple(pair for pair in conversation.draft.anchors
                 if contains(body, pair.fragment))
    # Deduplicated, because the two sides can name the same pair: what the
    # model offers for the new block is added to what already backed the
    # rest, and a model re-offering a pair it was told it could keep would
    # otherwise put two identical rows in the panel and count one claim
    # twice. Order is kept: `dict.fromkeys` is the cheapest way to say it.
    merged = tuple(dict.fromkeys(kept + _anchor_pairs(arguments)))
    _keep_version(conversation)
    conversation.draft = Draft(
        body=body, anchors=merged,
        photos=conversation.draft.photos, tips=conversation.draft.tips,
        problems=tuple(problems),
        written=(now or datetime.now()).strftime(STAMP))
    return conversation.draft


def _keep_version(conversation: Conversation) -> None:
    """Put the draft about to be replaced on the pile of earlier ones.

    Called by both writers, because a rewrite is a rewrite whether it aimed
    at the whole post or at one block. A first draft replaces nothing and
    pushes nothing: the pile holds versions, not a slot for the absence of
    one.
    """
    if conversation.draft is not None:
        conversation.earlier.append(conversation.draft)


def version(conversation: Conversation) -> int:
    """Which version of the post is in front of somebody, counting from one.

    Derived, never stored, for the reason no verdict is stored either: a
    number written down beside the thing it counts goes wrong the first time
    anything else moves, and it goes wrong quietly.
    """
    return len(conversation.earlier) + 1 if conversation.draft else 0


def revert(conversation: Conversation, body: str,
           now: datetime | None = None) -> Draft:
    """Put the previous version back in front.

    `body` is the digest of the post as the person read it, positional for
    the reason `approve` takes one that way: a turn can replace the draft
    behind a screen already drawn, and a click that arrived from that screen
    would throw away a version whose owner never saw it. The fourth signer
    of `shown`, and the same digest, so the four cannot drift apart.

    The pile shrinks rather than growing. Going back and going back again
    walks the versions in order, which is what the button on the screen says
    it does; a revert that appended the old body as a new version would show
    V3 to somebody who asked for V1 and would never reach V1 at all.

    What is lost is one body the engine wrote. Nothing anchors on it:
    `said` is the person's turns and their requests, and this list is the
    engine's words, which is exactly why they can be dropped and those
    cannot.
    """
    if conversation.state != OPEN:
        raise InterviewError(
            f"interview {conversation.id} is closed; its post is settled")
    if conversation.draft is None or not conversation.earlier:
        raise InterviewError(
            f"interview {conversation.id} has one version of its post and "
            "no earlier one to go back to")
    if body != shown(conversation.draft.body):
        raise DraftChanged(
            f"the post of {conversation.id} is not the one this was read "
            "from; it has been rewritten since the screen was drawn")
    # The stamp is the moment of the click, not the moment the engine wrote
    # this body, and it is why `restored` exists: `_pending` asks what was
    # asked after the current draft, and going back moves that backwards.
    # Without it, the request whose answer was just taken back would be
    # handed to the next turn as an unanswered one.
    conversation.draft = replace(
        conversation.earlier.pop(),
        restored=(now or datetime.now()).strftime(STAMP))
    return conversation.draft


def revise(conversation: Conversation, text: str, *, passage: str = "",
           passage_index: int = -1,
           now: datetime | None = None) -> Revision:
    """What the person asks for once a draft exists.

    Kept, and kept on the `Said` side. A record that dropped it could not say
    why the third draft differs from the second, and a person who types a
    correction here would watch the engine quote it back marked fabricated,
    which is the loudest alarm this screen has, fired at the most legitimate
    thing anybody does on it.

    It is not an interview turn. Nothing is appended to `messages`: that list
    is a wire request, and a drafting turn is not on it.
    """
    if conversation.state != OPEN:
        raise InterviewError(
            "this interview is closed; nothing about it changes any more")
    if conversation.draft is None:
        # The sheet steers the first draft. A revision revises something.
        raise InterviewError(
            f"{conversation.id} has no draft yet, so there is nothing to "
            "revise; the approved sheet is what the first one is written to")
    text = (text or "").strip()
    if not text:
        raise InterviewError("an empty request is not a request")
    if passage or passage_index >= 0:
        # Resolved here rather than at the turn. The screen that offered
        # this block can be older than the disk, and a request aimed at what
        # used to be the second paragraph must be refused while somebody is
        # still looking at it, not silently landed on whatever is there now.
        try:
            passage_at(conversation.draft.body, passage_index, passage)
        except PassageGone as gone:
            raise InterviewError(str(gone)) from None
    revision = Revision(text=text, asked=(now or datetime.now()).strftime(STAMP),
                        passage=passage, passage_index=passage_index)
    conversation.revisions.append(revision)
    return revision


def passage_for(conversation: Conversation, passage: str,
                passage_index: int) -> object | None:
    """The block a turn is confined to, resolved from what the screen sent.

    From the form and from nothing else, which is the whole of the fix this
    replaced. A scope derived from the conversation outlives the screen: a
    request that named a passage and got nothing back stays pending, and the
    next turn would be confined to that block while the picker in front of
    the person reads "the whole post" and the sentence promising a scope is
    hidden. The engine has to do what the screen says it will do.

    What keeps a scope alive across a turn that produced nothing is the
    screen offering it back, in `pending_scope`, where the person can see it
    and change it.
    """
    if conversation.draft is None or not passage or passage_index < 0:
        return None
    try:
        return passage_at(conversation.draft.body, passage_index, passage)
    except PassageGone as gone:
        raise InterviewError(str(gone)) from None


def pending_scope(conversation: Conversation) -> object | None:
    """The block the screen should offer back, pre-selected.

    The last pending request that named one, so a refusal, a failed turn or
    a reload does not quietly drop the scope somebody chose. It decides what
    a picker shows, never what a turn does: `passage_for` decides that.

    Nothing is raised on a scope that no longer resolves. A draft written
    since would have answered it, and a post rewritten under it is exactly
    the case where offering it back would be wrong.
    """
    if conversation.draft is None:
        return None
    for revision in reversed(_pending(conversation)):
        if revision.scoped:
            try:
                return passage_at(conversation.draft.body,
                                  revision.passage_index, revision.passage)
            except PassageGone:
                return None
    return None


def drafting_sections(conversation: Conversation, *, scope=None) -> tuple:
    """Which sections of the skill a drafting turn is assembled from.

    A rewrite is not a first draft, and the skill has a section about exactly
    that difference. Which one applies is read off the conversation rather
    than passed in: the caller that knows there is a draft already is the one
    holding this object.
    """
    if conversation.draft is None:
        return DRAFT_SECTIONS
    if scope is not None:
        return DRAFT_SECTIONS + (REVISION_SECTION, PASSAGE_SECTION)
    return DRAFT_SECTIONS + (REVISION_SECTION,)


def material(conversation: Conversation, *, scope=None) -> str:
    """What a drafting turn is handed: the interview as a human reads it,
    then the sheet the person signed.

    Both are state, rendered. Neither is an instruction: what to do with them
    is the skill's `Writing` section, loaded from the bundle like every other
    word this engine sends.

    This is handed over as one fresh user message rather than by continuing
    the interview's own message list, and that is the point. A message the
    engine wrote into that list would be credited to the person by `timeline`,
    which is the anchoring source: a model could then anchor a claim on text
    the engine put in its mouth. The material travels, the source does not
    move.
    """
    if not sheet_approved(conversation):
        raise InterviewError(
            f"the sheet of {conversation.id} is not approved, so there is "
            "nothing to draft from")
    sheet = conversation.sheet
    parts = [f"## {heading}\n\n{_not_a_heading(text.strip())}"
             for heading, text in _sides(conversation)]
    # The sheet's own keys, the ones its tool declares. Structure, not prose:
    # a label written here would be a label in one language on every screen.
    parts.append("## Sheet\n\n" + json.dumps(
        {"angle": sheet.angle, "elements": list(sheet.elements),
         "moment": sheet.moment, "conviction": sheet.conviction,
         "first_lines": list(sheet.first_lines), "state": sheet.state},
        ensure_ascii=False, indent=2))
    pending = _pending(conversation)
    if pending:
        # Said twice on purpose. The sides above are the record and the
        # anchoring source, where every request belongs in order; this one is
        # what is being answered now, and a reader that had to work out which
        # of five `Said` sections was the instruction would sometimes answer
        # the wrong one.
        parts.append("## Revision\n\n" + "\n\n".join(
            _not_a_heading(revision.text) for revision in pending))
    if scope is not None:
        # Word for word, and after the request, because it is what the
        # request is about. A turn handed a paraphrase of the passage would
        # rewrite the paraphrase, and the span it lands in belongs to the
        # text that is actually there.
        parts.append("## Passage\n\n" + _not_a_heading(scope.text))
    return "\n\n".join(parts)


def _pending(conversation: Conversation) -> list:
    """The requests this drafting turn still owes an answer to.

    Every revision asked since the current draft was written, in order, and
    usually that is one. It is more than one after a turn where the engine
    produced nothing: a refusal, above all, which is a turn it is supposed to
    have. Somebody who answers a refusal with `Malt barometer, 2025` is
    naming a source, not asking for a shorter post, and a block carrying only
    their last message would hand the writer the source as the instruction
    and drop what was actually asked for.

    Told from the two timestamps both objects already carry rather than from
    a key saying so. A `conversation.json` written before this reads back
    unchanged and `VERSION` does not move. When either timestamp is missing,
    nothing can be said about what came after what, and the older rule
    applies rather than a guess: the last request is the request. Same for
    the hour a clock goes back: both stamps are local and naive, a genuinely
    later request can carry the smaller one, and the fallback is the old
    behaviour rather than a wrong order.

    Equal stamps count as answered, which is why the comparison is strict.
    The route asks for the revision before the drafting turn fires, so a
    request answered inside the same second is a request this draft already
    served.

    Capped, because the signal cannot tell a refusal from a provider that
    failed and a person who retyped. Two is the normal run: what was asked,
    and what they came back with. A longer one means turns kept producing
    nothing, and there the oldest wordings are the ones most likely to have
    been superseded by the retype that follows them.
    """
    if not conversation.revisions:
        return []
    written = conversation.draft.since if conversation.draft else ""
    if written:
        pending = [revision for revision in conversation.revisions
                   if revision.asked > written]
        if pending:
            return pending[-MOST_PENDING:]
    return conversation.revisions[-1:]


def sources(conversation: Conversation) -> dict:
    """The text each provenance is checked against, by provenance.

    The transcript side is `said()` and nothing else: the engine's own
    questions and every tool result stay out of it, or a model could satisfy
    anchoring by quoting the question it just asked. The sheet side is the
    approved sheet's own words, and only once approved: a proposed sheet is
    replaceable and signed by nobody, so nothing is backed by it, and a draft
    cannot exist before the approval anyway. What is not in this mapping
    backs nothing, the profile first of all.
    """
    found = {FROM_TRANSCRIPT: conversation.said()}
    if sheet_approved(conversation):
        found[FROM_SHEET] = conversation.sheet.text()
    return found


def checked(conversation: Conversation) -> list:
    """The verdict on every anchor of the current draft, computed now, each
    quote against the one source its provenance names: `sources` says
    which, and a quote is never looked for anywhere else."""
    if conversation.draft is None:
        return []
    return verify(conversation.draft.body, conversation.draft.anchors,
                  sources(conversation))


def start(instance_root, *, skill: str, sections, interface_language: str,
          output_language: str, provider: str, model: str,
          now: datetime | None = None) -> Conversation:
    home = _home(instance_root)
    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError as broken:
        # An unwritable instance directory reads the same way to somebody as a
        # refused one, and neither is a traceback.
        raise InterviewError(
            f"cannot create {DIRECTORY}/: {broken.strerror}") from None
    now = now or datetime.now()
    stamp = now.strftime(STAMP)
    base = now.strftime(ID_STAMP)
    # mkdir is the claim. Two interviews opened in the same minute is a person
    # starting over, not a collision to paper over with a random suffix.
    for attempt in range(1, 1000):
        interview_id = base if attempt == 1 else f"{base}-{attempt}"
        try:
            (home / interview_id).mkdir()
            break
        except FileExistsError:
            continue
        except OSError as broken:
            # The one that fails in practice: after the first interview the
            # home exists, so its own mkdir succeeds and only this one can hit
            # a read only mount, a wrong owner, or a full disk.
            raise InterviewError(
                f"cannot create {DIRECTORY}/{interview_id}: "
                f"{broken.strerror}") from None
    else:
        raise InterviewError(f"too many interviews already started at {base}")
    conversation = Conversation(
        id=interview_id, skill=skill, sections=tuple(sections),
        interface_language=interface_language, output_language=output_language,
        provider=provider, model=model, started=stamp, updated=stamp)
    save(instance_root, conversation, now=now)
    return conversation


def save(instance_root, conversation: Conversation,
         now: datetime | None = None) -> None:
    """Write the conversation, then its rendering.

    That order is the recoverable one: a process that dies between the two
    leaves the truth current and the transcript one turn stale, which the next
    save repairs. The other order would leave a transcript claiming words the
    conversation cannot answer for.
    """
    here = directory(instance_root, conversation.id)
    if not here.is_dir():
        raise InterviewError(f"no interview {conversation.id} in {instance_root}")
    conversation.updated = (now or datetime.now()).strftime(STAMP)
    atomic_write(here / CONVERSATION, _as_json(conversation))
    atomic_write(here / TRANSCRIPT, render(conversation))


def load(instance_root, interview_id: str) -> Conversation:
    path = directory(instance_root, interview_id) / CONVERSATION
    if path.is_symlink():
        # The contract says nothing under here is a link. Writing is already
        # safe, os.replace replaces the link rather than following it; reading
        # through one is what would quietly serve another file's contents.
        raise InterviewError(
            f"{CONVERSATION} of {interview_id} is a link, not a file")
    if not path.is_file():
        raise InterviewError(f"no interview {interview_id} in {instance_root}")
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as unreadable:
        # Half written bytes from a sync client, a mode that came across wrong.
        # Refusing one interview is right; taking the screen that lists them
        # down with it is not, and that screen is the only way to discard it.
        raise InterviewError(
            f"the conversation file of {interview_id} cannot be read: "
            f"{type(unreadable).__name__}") from None
    return _from_json(raw, interview_id)


def listing(instance_root) -> list:
    """Every interview on disk, newest first. Ids are timestamps, so their
    order is chronological and does not need the files to be read to sort."""
    home = _home(instance_root)
    if not home.is_dir():
        return []
    try:
        children = sorted(home.iterdir(), key=lambda path: path.name,
                          reverse=True)
    except OSError as unreadable:
        raise InterviewError(
            f"{DIRECTORY}/ cannot be listed: {unreadable.strerror}") from None
    found = []
    for child in children:
        if not ID.match(child.name):
            continue
        if child.is_symlink() or not child.is_dir():
            # Refusing to read through it is right; hiding it would leave an
            # entry only a terminal can remove.
            found.append(Entry(id=child.name, unreadable=True))
            continue
        try:
            conversation = load(instance_root, child.name)
        except InterviewError:
            found.append(Entry(id=child.name, unreadable=True))
            continue
        turns = conversation.person_turns()
        found.append(Entry(id=conversation.id, state=conversation.state,
                           updated=conversation.updated, turns=len(turns),
                           opening=turns[0] if turns else ""))
    return found


def close(instance_root, interview_id: str, post: str,
          now: datetime | None = None) -> Conversation:
    """Mark the interview as the post it became. The directory stays: those
    are the person's own words, and the session notes in the post file are a
    summary of them, not a replacement."""
    conversation = load(instance_root, interview_id)
    conversation.state = CLOSED
    conversation.post = post
    save(instance_root, conversation, now=now)
    return conversation


def discard(instance_root, interview_id: str) -> None:
    here = _home(instance_root) / _safe_id(interview_id)
    if here.is_symlink():
        # Not through it: the link goes, whatever it pointed at stays. Hiding
        # it instead would leave somebody an entry they can only remove with a
        # terminal.
        here.unlink()
        return
    if not here.is_dir():
        raise InterviewError(f"no interview {interview_id} in {instance_root}")
    shutil.rmtree(here)


# ----------------------------------------------------------------- the format

def _draft_json(draft: Draft) -> dict:
    """One draft on disk. Written by `_as_json` for the current one and for
    every earlier one, so the pile and the post in front of it are the same
    shape and `_check_draft` reads both."""
    return {
        "body": draft.body,
        # The key of the quote is its provenance, `said` or `sheet`, the
        # same spelling the tool call travels under.
        "anchors": [{"post": anchor.fragment,
                     KEY_OF[anchor.provenance]: anchor.quote}
                    for anchor in draft.anchors],
        "photos": [{"kind": note.kind, "text": note.text}
                   for note in draft.photos],
        "tips": [{"kind": note.kind, "text": note.text}
                 for note in draft.tips],
        "problems": list(draft.problems),
        "written": draft.written,
        # Written only when there is one, so a conversation nobody ever took
        # back reads byte for byte through a version that never had the key.
        **({"restored": draft.restored} if draft.restored else {}),
    }


def _as_json(conversation: Conversation) -> str:
    data = {
        "version": VERSION,
        "id": conversation.id,
        "skill": conversation.skill,
        "sections": list(conversation.sections),
        "state": conversation.state,
        "post": conversation.post,
        "started": conversation.started,
        "updated": conversation.updated,
        "interface_language": conversation.interface_language,
        "output_language": conversation.output_language,
        "provider": conversation.provider,
        "model": conversation.model,
        "usage": {"input_tokens": conversation.usage.input_tokens,
                  "output_tokens": conversation.usage.output_tokens},
        "spent": conversation.spent,
    }
    if conversation.sheet is not None:
        # Absent until proposed, per the contract: a conversation without a
        # sheet stays a file an older reader already knows byte for byte.
        sheet = conversation.sheet
        data["sheet"] = {
            "state": sheet.state,
            "angle": sheet.angle,
            "elements": list(sheet.elements),
            "moment": sheet.moment,
            "conviction": sheet.conviction,
            "first_lines": list(sheet.first_lines),
            "problems": list(sheet.problems),
            "proposed": sheet.proposed,
            "approved": sheet.approved,
        }
    if conversation.draft is not None:
        # Absent until there is one, exactly like `sheet` above.
        data["draft"] = _draft_json(conversation.draft)
    if conversation.earlier:
        # Absent until the first rewrite, exactly like `sheet` and `draft`.
        # The same writer as the draft above and read back by the same
        # reader: two spellings of one object is how the pile and the post
        # in front of it start meaning different things.
        data["earlier"] = [_draft_json(draft) for draft in conversation.earlier]
    if conversation.revisions:
        # Absent until the first one, exactly like `sheet` and `draft`.
        data["revisions"] = [
            # The scope keys are written only when there is one, so a
            # conversation with no scoped request round trips byte for byte
            # through a version that never had them.
            {"text": revision.text, "asked": revision.asked,
             **({"passage": revision.passage,
                 "passage_index": revision.passage_index}
                if revision.scoped else {})}
            for revision in conversation.revisions]
    data["messages"] = conversation.messages
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _from_json(raw: str, interview_id: str) -> Conversation:
    try:
        data = json.loads(raw)
    except ValueError as broken:
        raise InterviewError(
            f"the conversation file of {interview_id} does not parse: "
            f"{broken}. Nothing repairs it automatically; the words are in "
            f"{TRANSCRIPT} next to it.") from None
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise InterviewError(
            f"the conversation file of {interview_id} is not a conversation")
    version = data.get("version")
    if version != VERSION:
        raise InterviewError(
            f"the conversation file of {interview_id} is version {version!r} "
            f"and this engine reads version {VERSION}")
    try:
        return _build(data, interview_id)
    except (TypeError, ValueError, AttributeError, KeyError) as wrong:
        # It parsed as JSON and then held the wrong shape: a number where a
        # word belongs, a list where a map belongs. Refusing is right, and
        # refusing with a traceback is not: a directory nobody can list is a
        # directory nobody can discard from the screen either.
        raise InterviewError(
            f"the conversation file of {interview_id} does not hold a "
            f"conversation: {type(wrong).__name__}") from None


def _build(data: dict, interview_id: str) -> Conversation:
    usage = data.get("usage", {})
    if usage is None:
        usage = {}
    if not isinstance(usage, dict):
        raise ValueError("usage")
    spent = data.get("spent", 0.0)
    if spent is not None:
        spent = float(spent)
        if spent != spent or spent in (float("inf"), float("-inf")):
            # A figure that is not a figure would render as `nan` on a screen
            # about somebody's bill.
            raise ValueError("spent")
    for message in data["messages"]:
        _check_message(message)
    if str(data.get("state") or OPEN) not in (OPEN, CLOSED):
        raise ValueError("state")
    skill = str(data.get("skill", ""))
    if skill and not SKILL_NAME.match(skill):
        # It is joined into a path under the bundle, and an instance is a
        # directory people copy, sync and sometimes commit.
        raise ValueError("skill")
    return Conversation(
        id=str(data.get("id") or interview_id),
        skill=skill,
        sections=tuple(str(name) for name in (data.get("sections") or ())),
        interface_language=str(data.get("interface_language", "")),
        output_language=str(data.get("output_language", "")),
        provider=str(data.get("provider", "")),
        model=str(data.get("model", "")),
        started=str(data.get("started", "")),
        updated=str(data.get("updated", "")),
        state=str(data.get("state") or OPEN),
        post=str(data.get("post") or ""),
        usage=Usage(int(usage.get("input_tokens") or 0),
                    int(usage.get("output_tokens") or 0)),
        spent=spent,
        sheet=_check_sheet(data.get("sheet")),
        draft=_check_draft(data.get("draft")),
        earlier=_check_earlier(data.get("earlier")),
        revisions=_check_revisions(data.get("revisions")),
        messages=data["messages"])


def _check_sheet(data) -> Sheet | None:
    """The sheet, refused when it does not hold one.

    Strict on shape and on `state`, for the same reason `_check_message` is:
    the guard reads `state`, and a hand edited value it does not know would
    otherwise pass as `not approved` and quietly reopen the questions. Length
    rules are proposal time rules and are not re-litigated here.
    """
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("sheet")
    if data.get("state") not in (PROPOSED, APPROVED):
        raise ValueError("sheet")
    for name in ("angle", "moment", "conviction", "proposed", "approved"):
        if not isinstance(data.get(name, ""), str):
            raise ValueError("sheet")
    for name in ("elements", "first_lines"):
        entries = data.get(name)
        if not isinstance(entries, list) or not all(
                isinstance(entry, str) for entry in entries):
            raise ValueError("sheet")
    problems = data.get("problems", [])
    if not isinstance(problems, list) or not all(
            isinstance(entry, str) for entry in problems):
        raise ValueError("sheet")
    return Sheet(
        angle=str(data.get("angle", "")),
        elements=tuple(data["elements"]),
        moment=str(data.get("moment", "")),
        conviction=str(data.get("conviction", "")),
        first_lines=tuple(data["first_lines"]),
        problems=tuple(problems),
        state=data["state"],
        proposed=str(data.get("proposed", "")),
        approved=str(data.get("approved", "")))


def _check_draft(data) -> Draft | None:
    """The draft, refused when it does not hold one.

    Refused whole rather than half read, like the sheet: a body that is not a
    string reaches the screen that paints it, and an anchor missing its quote
    would silently become a claim backed by nothing.
    """
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("draft")
    if not isinstance(data.get("body"), str) or not data["body"].strip():
        raise ValueError("draft")
    if not isinstance(data.get("written", ""), str):
        raise ValueError("draft")
    problems = data.get("problems", [])
    if not isinstance(problems, list) or not all(
            isinstance(entry, str) for entry in problems):
        raise ValueError("draft")
    try:
        anchors = _anchor_pairs(data)
        photos = _notes(data, "photos", PHOTO_KINDS)
        tips = _notes(data, "tips", TIP_KINDS)
    except InterviewError:
        raise ValueError("draft") from None
    if not isinstance(data.get("restored", ""), str):
        raise ValueError("draft")
    return Draft(body=data["body"], anchors=anchors, photos=photos, tips=tips,
                 problems=tuple(problems),
                 written=str(data.get("written", "")),
                 restored=str(data.get("restored", "")))


def _check_earlier(data) -> list:
    """The versions this draft replaced, refused whole rather than half read.

    Same strictness as the draft in front of them, and read by the same
    function: one of these is the post the moment somebody goes back, and a
    body silently dropped for being the wrong shape is a version that
    disappears from the count and from the way back.
    """
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("earlier")
    found = []
    for entry in data:
        draft = _check_draft(entry)
        if draft is None:
            raise ValueError("earlier")
        found.append(draft)
    return found


def _check_revisions(data) -> list:
    """The requests, refused whole rather than half read.

    Same strictness as the sheet and the draft, and for a sharper reason than
    either: this list is an anchoring source. An entry silently dropped for
    being the wrong shape takes a sentence out of what somebody said, and the
    panel would then call a real quote of it fabricated.
    """
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("revisions")
    found = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("revisions")
        text, asked = entry.get("text"), entry.get("asked", "")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("revisions")
        if not isinstance(asked, str):
            raise ValueError("revisions")
        passage = entry.get("passage", "")
        index = entry.get("passage_index", -1)
        if not isinstance(passage, str) or isinstance(index, bool) \
                or not isinstance(index, int):
            raise ValueError("revisions")
        found.append(Revision(text=text, asked=asked, passage=passage,
                              passage_index=index))
    return found


def _check_message(message) -> None:
    """One message, one level deeper than "it is a map".

    Everything that reads a conversation walks these blocks: the transcript,
    the screen, and the anchoring source. A block whose `text` is a number
    reaches `str.strip` and takes down the screen that lists every interview,
    which is the one screen a corrupt interview can be discarded from. Refusing
    the file here is what keeps that screen up.
    """
    if not isinstance(message, dict):
        # Dropping the odd one silently would quietly lose somebody's turn,
        # which is the thing this whole file exists not to do.
        raise ValueError("messages")
    content = message.get("content")
    if isinstance(content, str):
        return
    if not isinstance(content, list):
        raise ValueError("content")
    for block in content:
        if not isinstance(block, dict):
            raise ValueError("block")
        if "text" in block and not isinstance(block["text"], str):
            raise ValueError("text")
        if block.get("type") == "tool_result":
            answer = block.get("content")
            if not isinstance(answer, (str, list, type(None))):
                raise ValueError("tool_result")
            if isinstance(answer, list) and not all(
                    isinstance(part, dict)
                    and isinstance(part.get("text", ""), str)
                    for part in answer):
                raise ValueError("tool_result")


def _front_matter_value(value) -> str:
    text = str(value)
    if text == "":
        return ""
    if text[0] in "\"'[{&*!|>%@`#-?," or ": " in text or text[-1] == ":":
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def render(conversation: Conversation) -> str:
    """The transcript as a human reads it. Written on every save, parsed back
    never: `references/instance.md` says which of the two files is the truth,
    and it is not this one."""
    fields = [
        ("state", conversation.state),
        ("id", conversation.id),
        ("skill", conversation.skill),
        ("started", conversation.started),
        ("updated", conversation.updated),
        ("interface_language", conversation.interface_language),
        ("output_language", conversation.output_language),
        ("provider", conversation.provider),
        ("model", conversation.model),
        ("input_tokens", conversation.usage.input_tokens),
        ("output_tokens", conversation.usage.output_tokens),
        ("spent", "" if conversation.spent is None
                  else f"{conversation.spent:.4f}"),
        ("post", conversation.post),
    ]
    lines = ["---"]
    for key, value in fields:
        rendered = _front_matter_value(value)
        lines.append(f"{key}: {rendered}" if rendered else f"{key}:")
    lines += ["---", "", f"# Interview {conversation.id}", ""]
    for heading, text in _sides(conversation):
        lines += [f"## {heading}", "", _not_a_heading(text.strip()), ""]
    return "\n".join(lines).rstrip() + "\n"


def _not_a_heading(text: str) -> str:
    """Indent a line that would read as one of this file's own headings.

    `conversation.json` is the truth and the anchoring source, so nothing here
    can forge a quote. But a human reads this file, and a model that writes
    `## Said` into its own answer would otherwise appear to have a section of
    somebody else's words. One leading space, the text unchanged.
    """
    return "\n".join(" " + line if line.lstrip().startswith("#") else line
                      for line in text.splitlines())


def _sides(conversation: Conversation):
    """The conversation as alternating sides, in message order. Tool traffic
    is skipped: a file the engine read is not a thing anybody said.

    The revision requests follow, on the `Said` side they belong to. They come
    last because that is when they happened: an approved sheet ends the
    questions, so nothing is asked after the first one.
    """
    for moment in timeline(conversation):
        if moment.kind == SAID:
            yield "Said", moment.text
        elif moment.kind == ASKED:
            yield "Asked", moment.text
    for revision in conversation.revisions:
        yield "Said", revision.text
