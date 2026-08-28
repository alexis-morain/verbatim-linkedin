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

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .instance import atomic_write
from .providers import Usage

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

#: The step of the bundle this screen drives. Structure, not text: the app
#: names which part of the skill applies here, the skill holds every word.
#: A section renamed in `skills/` fails the test that pins these names rather
#: than reaching somebody's first question.
STEP_SKILL = "linkedin-post"
STEP_SECTIONS = ("Before anything", "The interview",
                 "The break: format and angle", "The validation sheet")

#: The contract's name format, and the whole path guard: an id that is not a
#: timestamp cannot address anything, inside this directory or out of it.
ID = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}(?:-[0-9]+)?\Z")

#: A skill name is a directory under the bundle, so it is checked like an id.
SKILL_NAME = re.compile(r"\A[a-z0-9][a-z0-9-]{0,63}\Z")

ID_STAMP = "%Y-%m-%d-%H%M"
STAMP = "%Y-%m-%dT%H:%M:%S"


class InterviewError(Exception):
    pass


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

    def digest(self) -> str:
        """What identifies this sheet: its content, nothing else.

        An approval must sign the sheet the person read, and the form that
        carries the click can be older than the disk: a turn still streaming
        can replace a proposed sheet behind a screen already drawn. So the
        page carries this digest and `approve` refuses a mismatch. Content
        only, no timestamp: two proposals with the same five fields are the
        same decision, and a turn can propose twice inside one second.
        """
        payload = json.dumps(
            [self.angle, list(self.elements), self.moment, self.conviction,
             list(self.first_lines)], ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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
    messages: list = field(default_factory=list)

    # -- what the person said, and nothing else

    def person_turns(self) -> list:
        return [moment.text for moment in timeline(self) if moment.kind == SAID]

    def said(self) -> str:
        """The anchoring source: every word the person typed, and no other."""
        return "\n\n".join(self.person_turns())

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


def propose(conversation: Conversation, arguments: dict,
            now: datetime | None = None) -> Sheet:
    """The engine's half of the sheet: propose, never decide.

    Raised messages address the model, because they travel back as the tool
    result. A proposal on a conversation whose sheet is already approved is
    refused rather than replacing it: the approved sheet is what the person
    signed, and the guard would be worth nothing if the next turn could swap
    what sits under their signature.
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
            "proposed": sheet.proposed,
            "approved": sheet.approved,
        }
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
    return Sheet(
        angle=str(data.get("angle", "")),
        elements=tuple(data["elements"]),
        moment=str(data.get("moment", "")),
        conviction=str(data.get("conviction", "")),
        first_lines=tuple(data["first_lines"]),
        state=data["state"],
        proposed=str(data.get("proposed", "")),
        approved=str(data.get("approved", "")))


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
    is skipped: a file the engine read is not a thing anybody said."""
    for moment in timeline(conversation):
        if moment.kind == SAID:
            yield "Said", moment.text
        elif moment.kind == ASKED:
            yield "Asked", moment.text
