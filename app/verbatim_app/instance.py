"""Read and write a Verbatim instance directory.

The contract implemented here is references/instance.md. If a behaviour in
this file is not backed by a clause there, the contract gets the clause
first. Aggregates (pillar counter, measurement views) are recomputed from
the post files at read time and never written back.

Standard library only; PyYAML is used when present, with a fallback parser
covering the front matter subset the contract actually uses.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .measure import view as _measure_view
from .sections import _status_line, sections_of

try:
    import yaml as _yaml
except ImportError:  # the fallback below covers the shipped format
    _yaml = None


class InstanceError(Exception):
    pass


class UnreadableError(InstanceError):
    """The file is there and its bytes will not come back as text.

    Separate from "it is not there" because the two want different screens:
    one is a file to create, the other is a file to repair, and a consumer
    that cannot tell them apart shows the wrong one.
    """


class SectionChanged(InstanceError):
    """The section on disk is not the one the screen showed.

    Its own type because the caller has something to say about it that no
    other refusal shares: nothing was written, and what is on disk now is
    what has to be read again before deciding.
    """


class NameTaken(InstanceError):
    """The file is already there and this write would replace it.

    Its own type for the reason `UnreadableError` has one: a caller that
    cannot tell it apart from "the directory will not take a file" shows the
    wrong screen, and here the two fixes are pick another name and repair
    your disk.
    """


# Files a consumer may write. Everything else in the instance is either
# produced by a dedicated skill (posts/, linkedin-page.md via its owner)
# or is somebody's raw corpus, which is never rewritten.
WRITABLE = ("profile.md", "voice.md", "pillars.md", "ideas.md", "linkedin-page.md")
COMPANIONS = ("voice.md", "pillars.md", "ideas.md")

#: A language code names a directory under `locales/`, so the Status block
#: takes what a path segment takes. The same shape `skills.py` checks, written
#: again rather than imported: this module is standard library only and does
#: not reach into the bundle loader.
LANGUAGE = re.compile(r"\A[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?\Z")

# The full front matter key set from references/measure.md. A post file
# missing one of these gets reported, never silently completed.
MEASURE_KEYS = (
    "date", "pillar", "format", "label", "hook", "chars", "state",
    "published_ref", "measured", "inbound_connections", "inbound_dms",
    "meeting_mentions", "note",
)

MEASUREMENT_FIELDS = (
    "measured", "inbound_connections", "inbound_dms", "meeting_mentions", "note",
)

#: The three states of `references/measure.md`. Every count in the system runs
#: over `published` alone, which is why a fourth one invented anywhere would be
#: a post counted nowhere. Here rather than beside the archiving step, because
#: two steps write this key now: archiving starts it at `draft` and publishing
#: moves it.
STATES = ("draft", "scheduled", "published")

#: Front matter keys whose value is written as a double quoted scalar. Both
#: hold text somebody pasted: a note holding a Windows path, a reference that
#: is a URL and therefore carries a colon on every call.
QUOTED = ("note", "published_ref")


@dataclass
class Gap:
    code: str
    detail: str = ""


@dataclass
class Status:
    filled: bool
    source: str
    updated: str
    interface_language: str
    output_language_default: str


@dataclass
class PostMeta:
    filename: str
    date: str | None
    pillar: int | None
    format: str | None
    label: str | None
    hook: str
    chars: int | None
    state: str | None
    published_ref: str | None
    measured: str | None
    inbound_connections: int | None
    inbound_dms: int | None
    meeting_mentions: int | None
    note: str | None
    present_keys: tuple = ()
    #: The file is there and its front matter cannot be read. Reported, never
    #: guessed at, and never allowed to take a screen down with it.
    unreadable: bool = False

    @property
    def missing_keys(self):
        if self.unreadable:
            return ()
        return tuple(k for k in MEASURE_KEYS if k not in self.present_keys)


@dataclass
class Angle:
    pillar: int
    label: str | None
    text: str
    section: str


@dataclass
class UsedIdea:
    date: str
    pillar: str
    angle: str
    file: str


@dataclass
class IdeaBank:
    next_session: str
    angles: list = field(default_factory=list)
    used: list = field(default_factory=list)


# ---------------------------------------------------------------- front matter

def split_front_matter(raw: str):
    """Return (front matter text, body) or (None, raw) when there is none."""
    if not raw.startswith("---\n"):
        return None, raw
    end = raw.find("\n---", 4)
    if end < 0:
        return None, raw
    return raw[4:end + 1], raw[end + 4:].lstrip("\n")


def _normalise(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def parse_front_matter(block: str) -> dict:
    if _yaml is not None:
        data = _yaml.safe_load(block) or {}
        return {k: _normalise(v) for k, v in data.items()}
    return parse_front_matter_fallback(block)


def _scalar(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return _unquote(raw[1:-1])
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        return raw[1:-1].replace("''", "'")
    # an unquoted scalar can carry a trailing comment, measure.md shows some
    raw = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
    if raw == "":
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def parse_front_matter_fallback(block: str) -> dict:
    """The subset of YAML the contract uses: flat keys, plain scalars,
    quoted strings, and literal block scalars for the hook."""
    data: dict = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\w+):\s*(.*)$", line)
        if m is None:
            raise InstanceError(f"front matter line not understood: {line!r}")
        key, rest = m.group(1), m.group(2)
        if rest.strip() == "|":
            collected = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith(" ")):
                collected.append(lines[i])
                i += 1
            indent = min((len(l) - len(l.lstrip()) for l in collected if l.strip()),
                         default=0)
            text = "\n".join(l[indent:] for l in collected).rstrip("\n")
            data[key] = text + "\n" if text else ""
        else:
            data[key] = _scalar(rest)
    return data


def read_text(path, name: str) -> str:
    """Every read of an instance file goes through here.

    One place, because the failure is always the same and always widens the
    same way: a file saved in another encoding or with a mode that came across
    wrong is one file, and every screen in this app renders the conformance
    report, so a raw failure anywhere takes the whole app down. Guarding the
    readers one at a time is how this came back three times.
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, ValueError) as unreadable:
        raise UnreadableError(
            f"{name} cannot be read: {type(unreadable).__name__}") from None


def atomic_write(path, text: str) -> None:
    """Write the whole file or leave the previous one untouched.

    Nothing in an instance is ever half a file. A profile caught mid write is
    somebody's material; a conversation caught mid write is a conversation the
    provider rejects on the next request.

    The rename is atomic, so this covers a crash, a kill and a failed write.
    It does not fsync, so it does not cover a power loss: the rename can land
    before the bytes do. Naming the limit rather than implying the stronger
    promise, since a durability claim nobody tested is worse than none.
    """
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _front_matter_line(key: str, value) -> str:
    if value is None:
        return f"{key}:"
    if isinstance(value, int):
        return f"{key}: {value}"
    if key in QUOTED:
        return f'{key}: "{_quote(str(value))}"'
    return f"{key}: {value}"


#: The named escapes of a YAML double quoted scalar, written and read back
#: through the same table so the two sides cannot drift apart.
NAMED = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}

def _quote(value: str) -> str:
    """One value as a YAML double quoted scalar, escaped completely.

    Everything with no named escape and no business appearing raw goes out as
    `\\xNN` or `\\uNNNN`. That covers three separate ways a pasted value used
    to break the file: a line break ends the scalar for the built in reader
    and writes what looks like several keys, `state` and `pillar` being
    exactly the two somebody would forge; a control character stops PyYAML
    reading the file at all, and the post then vanishes from every listing
    instead of being reported; and U+2028 or U+0085, which the two readers
    simply disagree about. The last pair is what an ordinary paste produces,
    out of a PDF or an editor, and `published_ref` is where people paste.

    Escaped character by character rather than by a chain of replacements. A
    chain has to escape the backslash first and then never touch what it
    wrote, so every escape added later is a chance to get that order wrong.
    This walks the string once and there is no order to get wrong. Found by
    review, twice: the first fix stopped at three characters.
    """
    out = []
    for char in value:
        if char in NAMED:
            out.append(NAMED[char])
        elif char < " " or char == "\x7f":
            out.append(f"\\x{ord(char):02x}")
        elif "\x80" <= char <= "\x9f" or char in ("\u2028", "\u2029"):
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return "".join(out)


def _unquote(body: str) -> str:
    """The inverse, for the built in reader. PyYAML does this itself, and the
    two have to agree about a block this engine wrote: a file the app can no
    longer read the way it wrote it is worse than either reader being wrong.
    """
    back = {written[1:]: raw for raw, written in NAMED.items()}
    out, index = [], 0
    while index < len(body):
        char = body[index]
        if char != "\\" or index + 1 >= len(body):
            out.append(char)
            index += 1
            continue
        marker = body[index + 1]
        if marker in back:
            out.append(back[marker])
            index += 2
        elif marker in ("x", "u") and _hex(body, index, marker) is not None:
            width = 2 if marker == "x" else 4
            out.append(chr(int(body[index + 2:index + 2 + width], 16)))
            index += 2 + width
        else:
            # Not an escape this writer produces. Kept as written rather than
            # dropped: what is there is what somebody typed.
            out.append(char)
            index += 1
    return "".join(out)


def _hex(body: str, index: int, marker: str):
    width = 2 if marker == "x" else 4
    digits = body[index + 2:index + 2 + width]
    if len(digits) == width and all(c in "0123456789abcdefABCDEF" for c in digits):
        return digits
    return None


# ------------------------------------------------------------------- instance

class Instance:
    def __init__(self, root):
        self.root = Path(root)

    # -- path discipline

    def _child(self, directory: Path, name: str) -> Path:
        if "/" in name or "\\" in name or name.startswith("."):
            raise InstanceError(f"refusing path {name!r}")
        path = directory / name
        if path.parent != directory:
            raise InstanceError(f"refusing path {name!r}")
        return path

    # -- raw files

    def read(self, name: str) -> str:
        path = self._child(self.root, name)
        if not path.is_file():
            raise InstanceError(f"{name} not found in {self.root}")
        return read_text(path, name)

    def write(self, name: str, text: str) -> None:
        if name not in WRITABLE:
            raise InstanceError(f"{name} is not a file this consumer may write")
        atomic_write(self._child(self.root, name), text)

    # -- sections of a document

    def sections(self, name: str) -> list:
        """The `## ` sections of one contract file, with their spans."""
        if name not in WRITABLE:
            raise InstanceError(f"{name} is not a file this consumer may write")
        return sections_of(self.read(name))

    def replace_section(self, name: str, heading: str, text: str,
                        shown_digest: str, *, today: str) -> None:
        """Rewrite one section and leave every other byte where it was.

        `shown_digest` is the section as the screen showed it. The disk can be
        newer than the screen, one tab or two, and a save that lands on a
        section somebody never read replaces words they did not mean to
        replace. A mismatch writes nothing and the screen says what is there
        now.

        On `profile.md` this also moves the Status line `updated`, because a
        section of the profile is what that date is about. `filled` and
        `source` are not touched by anything here: the first is somebody
        saying the profile is real and the second says which road it came
        down, and neither is a consequence of editing a paragraph.
        """
        if name not in WRITABLE:
            raise InstanceError(f"{name} is not a file this consumer may write")
        raw = self.read(name)
        found = [s for s in sections_of(raw) if s.heading == heading]
        if not found:
            raise InstanceError(f"{name} has no section {heading!r}")
        if len(found) > 1:
            raise InstanceError(
                f"{name} carries {heading!r} more than once, so nothing can "
                "be addressed by it; give the sections different headings")
        section = found[0]
        if section.digest != shown_digest:
            raise SectionChanged(
                f"the section {heading!r} of {name} changed since it was read")
        # The blank line after the heading is the file's own convention, and
        # a save that dropped it would drift every edited section away from
        # the ones nobody touched.
        body = text.strip("\n")
        if not body.strip():
            block = "\n"
        elif section.end < len(raw):
            block = "\n\n" + body + "\n\n"
        else:
            block = "\n\n" + body + "\n"
        new = raw[:section.start] + block + raw[section.end:]
        if name == "profile.md":
            new = _status_line(new, "updated", today)
        self.write(name, new)

    def update_status(self, *, interface_language: str,
                      output_language_default: str, today: str) -> None:
        """The two language axes of the Status block, and the date.

        A language code names a directory under `locales/`, so it is checked
        as the path segment it becomes. Refused before anything is written:
        half a Status block is worse than none.
        """
        for value in (interface_language, output_language_default):
            if not LANGUAGE.match(value):
                raise InstanceError(
                    f"{value!r} is not a language code. It names a directory "
                    "under locales/, so it is two or three letters, "
                    "optionally a region.")
        text = self.read("profile.md")
        text = _status_line(text, "interface_language", interface_language)
        text = _status_line(text, "output_language_default",
                            output_language_default)
        self.write("profile.md", _status_line(text, "updated", today))

    # -- profile

    def status(self) -> Status | None:
        try:
            text = self.read("profile.md")
        except InstanceError:
            return None
        section = _section(text, "Status")
        if section is None:
            return None
        values = {}
        for line in section.splitlines():
            m = re.match(r"^-\s+(\w+):\s*(.*)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2).strip()
        if "filled" not in values:
            return None
        return Status(
            filled=values.get("filled", "no").lower() == "yes",
            source=values.get("source", ""),
            updated=values.get("updated", ""),
            interface_language=values.get("interface_language", "en"),
            output_language_default=values.get("output_language_default", "en"),
        )

    def signature(self) -> str:
        """The signature block, as it is appended to every post.

        Concatenated, never generated: a generated signature drifts a little
        on every post until it belongs to somebody else. The fence around it
        in `profile.md` is markup for a reader, so it comes off here.

        An empty section is an answer, and it means no signature. An absent
        one is not: `references/instance.md` says its absence means the
        migration was incomplete, so reading it as "there is none" would file
        a post without one and call that a decision. This raises instead.
        """
        section = _section(self.read("profile.md"), "Signature block")
        if section is None:
            raise InstanceError(
                "profile.md has no '## Signature block' section. That is a "
                "section to restore, not a signature to do without")
        fenced = re.search(r"^```[^\n]*\n(.*?)^```", section,
                           re.MULTILINE | re.DOTALL)
        return (fenced.group(1) if fenced else section).strip()

    # -- posts

    def posts(self) -> list[PostMeta]:
        directory = self.root / "posts"
        if not directory.is_dir():
            return []
        result = []
        for path in sorted(directory.glob("*.md")):
            try:
                raw = read_text(path, path.name)
                block, _ = split_front_matter(raw)
                data = parse_front_matter(block) if block else {}
            except Exception:
                # One post file nobody can read is one post file, not the whole
                # app. Every screen renders the conformance report, so this
                # loop decides whether a bad byte in one archive takes down the
                # profile screen too. It is reported as a gap, never guessed at.
                result.append(PostMeta(
                    filename=path.name, date=None, pillar=None, format=None,
                    label=None, hook="", chars=None, state=None,
                    published_ref=None, measured=None, inbound_connections=None,
                    inbound_dms=None, meeting_mentions=None, note=None,
                    present_keys=(), unreadable=True))
                continue
            result.append(PostMeta(
                filename=path.name,
                date=data.get("date"),
                pillar=data.get("pillar"),
                format=data.get("format"),
                label=data.get("label"),
                hook=(data.get("hook") or "").strip(),
                chars=data.get("chars"),
                state=data.get("state"),
                published_ref=data.get("published_ref"),
                measured=data.get("measured"),
                inbound_connections=data.get("inbound_connections"),
                inbound_dms=data.get("inbound_dms"),
                meeting_mentions=data.get("meeting_mentions"),
                note=data.get("note"),
                present_keys=tuple(data.keys()),
            ))
        result.sort(key=lambda p: (p.date or "", p.filename), reverse=True)
        return result

    def post_raw(self, filename: str) -> str:
        path = self._child(self.root / "posts", filename)
        if not path.is_file():
            raise InstanceError(f"no such post: {filename}")
        return read_text(path, filename)

    def post_body(self, filename: str) -> str:
        path = self._child(self.root / "posts", filename)
        if not path.is_file():
            raise InstanceError(f"no such post: {filename}")
        _, body = split_front_matter(read_text(path, filename))
        return body

    def write_post(self, filename: str, text: str) -> None:
        """File one post under `posts/`, and never over one.

        `posts/` is deliberately outside `WRITABLE`, which is the set the
        tools hand a model. This method is why it does not need to be there:
        archiving is the person's step, reached from their screen, and a model
        that could write here could write its own measurements.

        A name already taken stops the step. The two files would be two posts
        from one day on one subject, and the one that loses is somebody's.
        """
        directory = self.root / "posts"
        path = self._child(directory, filename)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as broken:
            raise InstanceError(
                f"cannot create posts/: {broken.strerror}") from None
        if path.exists():
            raise NameTaken(
                f"posts/{filename} already exists; pick another slug or "
                "another date rather than writing over it")
        try:
            atomic_write(path, text)
        except OSError as broken:
            # Symmetric with `read_text`, which turns an OSError into an
            # instance failure so no screen has to know what a strerror is.
            # A directory that will not take a file is a repair, and the
            # caller answering it has to be able to tell it from a name that
            # is simply taken.
            raise InstanceError(
                f"cannot write posts/{filename}: {broken.strerror}") from None

    def use_idea(self, angle: str, *, date: str, file: str) -> None:
        """Move one angle out of the bank and into `## Used`.

        The bank is append only on the used side and a session never closes
        leaving it poorer than it found it. The half that is mechanical is
        this one; adding the angles an interview turned up is a judgement and
        stays with the person.
        """
        text = self.read("ideas.md")
        lines = text.splitlines()
        found = [(angle_, start, end)
                 for angle_, start, end in _scan_angles(lines)
                 if angle_.text == angle]
        if not found:
            raise InstanceError(f"no such angle in the bank: {angle!r}")
        entry, start, end = found[0]
        if "|" in entry.text:
            # The used line is four fields split on a pipe. An angle carrying
            # one would write a line nothing can read back, and mangling
            # somebody's own words to fit the format is worse than saying so.
            raise InstanceError(
                PIPE_REASON + "; edit the angle in ideas.md, then archive "
                "again")
        kept = lines[:start] + lines[end:]
        used = f"{date} | P{entry.pillar} | {entry.text} | {file}"
        marker = None
        for index, line in enumerate(kept):
            if line.strip().lower() == "## used":
                marker = index
        if marker is None:
            kept += ["", "## Used", "", "<!-- date | pillar | angle | file -->"]
            kept.append(used)
        else:
            end_of = len(kept)
            for index in range(marker + 1, len(kept)):
                if kept[index].startswith("## "):
                    end_of = index
                    break
            while end_of > marker + 1 and not kept[end_of - 1].strip():
                end_of -= 1
            kept.insert(end_of, used)
        self.write("ideas.md", "\n".join(kept).rstrip("\n") + "\n")

    def add_angle(self, section: str, pillar: int, label: str,
                  text: str) -> None:
        """One more angle in the bank, at the end of its section.

        A section nobody has yet is created rather than refused: the bank is
        the one file a session is never allowed to leave poorer, and a heading
        somebody typed is a heading they meant. It goes above `## Used`, which
        stays the last thing in the file.
        """
        text = _checked_angle(pillar, label, text)
        section = _checked_section(section)
        lines = self.read("ideas.md").splitlines()
        line = _angle_line(pillar, label, text)
        tail = _section_tail(lines, section)
        if tail is not None:
            lines.insert(tail, line)
        else:
            block = [f"## {section}", "", line]
            marker = None
            for index, existing in enumerate(lines):
                if existing.strip().lower() == "## used":
                    marker = index
            if marker is None:
                lines = lines + [""] + block
            else:
                if marker and lines[marker - 1].strip():
                    block = [""] + block
                lines = lines[:marker] + block + [""] + lines[marker:]
        self._write_ideas(lines)

    def edit_angle(self, old_text: str, *, pillar: int, label: str,
                   text: str) -> None:
        """Rewrite one angle in place, addressed by its own text.

        By text and not by position: the screen that offers this was drawn
        before the click, and an index would move an angle somebody never
        looked at.
        """
        text = _checked_angle(pillar, label, text)
        lines, _, start, end = self._angle_span(old_text)
        lines[start:end] = [_angle_line(pillar, label, text)]
        self._write_ideas(lines)

    def remove_angle(self, text: str) -> None:
        """Drop one angle. The used side is append only and is not touched."""
        lines, _, start, end = self._angle_span(text)
        del lines[start:end]
        self._write_ideas(lines)

    def _angle_span(self, text: str):
        lines = self.read("ideas.md").splitlines()
        found = [(angle, start, end)
                 for angle, start, end in _scan_angles(lines)
                 if angle.text == text]
        if not found:
            raise InstanceError(f"no such angle in the bank: {text!r}")
        angle, start, end = found[0]
        return lines, angle, start, end

    def _write_ideas(self, lines) -> None:
        self.write("ideas.md", "\n".join(lines).rstrip("\n") + "\n")

    def pillar_counter(self) -> dict:
        counter: dict = {}
        for post in self.posts():
            if post.state == "published" and post.pillar is not None:
                counter[post.pillar] = counter.get(post.pillar, 0) + 1
        return counter

    def measurement(self, today: date):
        """Everything `references/measure.md` counts, recomputed here and now:
        `measure.view` over the published posts, with `today` passed in so a
        test can pin the day."""
        return _measure_view(self.posts(), today)

    def update_post_measurement(self, filename: str, *, measured,
                                inbound_connections, inbound_dms,
                                meeting_mentions, note) -> None:
        """Rewrite only the measurement lines of the front matter, textually,
        so the rest of the block and the body stay byte for byte."""
        path = self._child(self.root / "posts", filename)
        if not path.is_file():
            raise InstanceError(f"no such post: {filename}")
        self._rewrite_front_matter(path, filename, {
            "measured": measured,
            "inbound_connections": inbound_connections,
            "inbound_dms": inbound_dms,
            "meeting_mentions": meeting_mentions,
            "note": note,
        })

    def update_post_state(self, filename: str, *, state: str,
                          published_ref: str) -> None:
        """Move a post off `draft`, and record what it can be found by.

        The publishing step's half of the front matter, written the way the
        measurement is: textually, so everything else in the file stays byte
        for byte.

        Neither value is checked against a vocabulary here. `state` is checked
        on the form that produces it, which is the only caller: `posts/` is
        outside `WRITABLE` and no tool reaches this, so a second check here
        would be a guard with no case behind it. `published_ref` has no
        vocabulary at all; it is whatever the tool that scheduled the post
        calls it, and an empty one is the honest value until something did.
        """
        path = self._child(self.root / "posts", filename)
        if not path.is_file():
            raise InstanceError(f"no such post: {filename}")
        self._rewrite_front_matter(path, filename,
                                   {"state": state,
                                    "published_ref": published_ref})

    def _rewrite_front_matter(self, path, filename: str, updates: dict) -> None:
        """Replace the named keys of a post's front matter and nothing else.

        A key that is not in the block is appended rather than dropped: a post
        file written before a key existed still gets it, which is the same
        rule `missing_keys` reports on rather than silently completing.
        """
        raw = read_text(path, filename)
        block, _ = split_front_matter(raw)
        if block is None:
            raise InstanceError(f"{filename} has no front matter to update")
        new_block = block
        for key, value in updates.items():
            line = _front_matter_line(key, value)
            pattern = re.compile(rf"^{key}:[^\n]*$", re.MULTILINE)
            if pattern.search(new_block):
                new_block = pattern.sub(line.replace("\\", "\\\\"), new_block, count=1)
            else:
                new_block = new_block.rstrip("\n") + "\n" + line + "\n"
        new_raw = "---\n" + new_block + raw[4 + len(block):]
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{filename}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(new_raw)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    # -- ideas

    def ideas(self) -> IdeaBank:
        text = self.read("ideas.md")
        lines = text.splitlines()
        next_session, angles, used = "", [], []
        section = ""
        i = 0
        # the first paragraph under the title names the next session
        while i < len(lines) and (not lines[i].strip() or lines[i].startswith("#")):
            i += 1
        para = []
        while i < len(lines) and lines[i].strip():
            para.append(lines[i].strip())
            i += 1
        next_session = " ".join(para)
        angles = [angle for angle, _, _ in _scan_angles(lines, start=i)]
        section = ""
        for j in range(i, len(lines)):
            line = lines[j]
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            if section.lower() == "used" and "|" in line and not line.strip().startswith("<!--"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) == 4:
                    used.append(UsedIdea(*parts))
        return IdeaBank(next_session=next_session, angles=angles, used=used)

    # -- corpus

    def corpus(self) -> list[str]:
        directory = self.root / "corpus"
        if not directory.is_dir():
            return []
        return sorted(p.name for p in directory.glob("*.md"))

    def corpus_text(self, name: str) -> str:
        path = self._child(self.root / "corpus", name)
        if not path.is_file():
            raise InstanceError(f"no such corpus file: {name}")
        return read_text(path, name)

    # -- conformance, references/instance.md order

    def conformance(self) -> list[Gap]:
        if not (self.root / "profile.md").is_file():
            return [Gap("profile-missing")]
        gaps = []
        status = self.status()
        if status is None:
            gaps.append(Gap("status-unparsed"))
        elif not status.filled:
            gaps.append(Gap("not-filled"))
        try:
            profile = self.read("profile.md")
        except InstanceError:
            profile = None
            gaps.append(Gap("profile-unreadable"))
        if profile is not None and not re.search(
                r"^## Signature block\s*$", profile, re.MULTILINE):
            gaps.append(Gap("signature-missing"))
        for name in COMPANIONS:
            if not (self.root / name).is_file():
                gaps.append(Gap("file-missing", name))
        for post in self.posts():
            if post.unreadable:
                gaps.append(Gap("post-unreadable", post.filename))
                continue
            if post.missing_keys:
                gaps.append(Gap("post-keys-missing",
                                f"{post.filename}: {' '.join(post.missing_keys)}"))
        return gaps


ANGLE_LINE = re.compile(r"^-\s+\[P(\d+)\]\s+(?:`(\w+)`|(\w+))\s+(.*)$")


def _scan_angles(lines, start: int = 0):
    """Every angle of the bank, with the lines it occupies.

    One walker, because two of them would eventually disagree: reading the
    bank and moving a line out of it have to agree on where an angle starts
    and where its wrapped continuation ends, or a move takes half a line with
    it and leaves the other half behind. `ideas` drops the spans, `use_idea`
    uses them.

    Yields `(Angle, first line, one past the last)`.
    """
    section, found = "", []
    for index in range(start, len(lines)):
        line = lines[index]
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        match = ANGLE_LINE.match(line)
        if match and section.lower() != "used":
            found.append([Angle(pillar=int(match.group(1)),
                                label=match.group(2) or match.group(3),
                                text=match.group(4).strip(), section=section),
                          index, index + 1])
            continue
        if found and (line.startswith("  ") and line.strip()
                      and not line.strip().startswith("-")):
            angle, first, _ = found[-1]
            found[-1] = [Angle(pillar=angle.pillar, label=angle.label,
                               text=angle.text + " " + line.strip(),
                               section=angle.section), first, index + 1]
    return [(angle, first, last) for angle, first, last in found]


def _section(text: str, heading: str) -> str | None:
    m = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    if m is None:
        return None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    return rest[:nxt.start()] if nxt else rest


# -------------------------------------------------------------------- angles

#: The three funnel labels of `references/instance.md`. A fourth one would be
#: an angle nothing counts.
LABELS = ("VISIBILITY", "TRUST", "ACTION")

PILLARS = (1, 2, 3)

#: Why a pipe cannot be in an angle. The advice differs between adding one and
#: archiving one, the reason does not.
PIPE_REASON = ("this angle carries a '|', which is the separator of the used "
               "line")


def _angle_line(pillar: int, label: str, text: str) -> str:
    return f"- [P{pillar}] `{label}` {text}"


def _checked_angle(pillar: int, label: str, text: str) -> str:
    """The three things an angle line cannot be written without.

    Whitespace is collapsed rather than refused: the box somebody types in
    takes a newline, and the bank is one line per angle.
    """
    if pillar not in PILLARS:
        raise InstanceError(f"{pillar!r} is not one of the three pillars")
    if label not in LABELS:
        raise InstanceError(f"{label!r} is not one of {', '.join(LABELS)}")
    text = " ".join(text.split())
    if not text:
        raise InstanceError("an angle with no text is not an angle")
    if "|" in text:
        raise InstanceError(PIPE_REASON + "; write it without one")
    return text


def _checked_section(heading: str) -> str:
    """A section name that can only ever become one heading line.

    Found in review: the text of an angle was checked and the section it
    went into was not, so a name carrying a line break could write a second
    heading, `## Used` included, and forge an archive row nothing archived.
    One line, no heading marker of its own, and never the used side, which
    only archiving writes.
    """
    if "\n" in heading or "\r" in heading or "#" in heading:
        raise InstanceError("a section is one heading line, without its '## '")
    heading = " ".join(heading.split())
    if not heading:
        raise InstanceError("a section needs a name")
    if heading.lower() == "used":
        raise InstanceError("the used side is written by archiving alone")
    return heading


def _section_tail(lines, heading: str):
    """Where a new angle goes in an existing section, or None.

    One past its last line that carries anything, so an added angle lands
    under the ones already there rather than under the blank line separating
    two sections.
    """
    for index, line in enumerate(lines):
        if line.startswith("## ") and line[3:].strip() == heading.strip():
            end = len(lines)
            for after in range(index + 1, len(lines)):
                if lines[after].startswith("## "):
                    end = after
                    break
            while end > index + 1 and not lines[end - 1].strip():
                end -= 1
            return end
    return None
