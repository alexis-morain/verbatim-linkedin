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
from pathlib import Path

try:
    import yaml as _yaml
except ImportError:  # the fallback below covers the shipped format
    _yaml = None


class InstanceError(Exception):
    pass


# Files a consumer may write. Everything else in the instance is either
# produced by a dedicated skill (posts/, linkedin-page.md via its owner)
# or is somebody's raw corpus, which is never rewritten.
WRITABLE = ("profile.md", "voice.md", "pillars.md", "ideas.md", "linkedin-page.md")
COMPANIONS = ("voice.md", "pillars.md", "ideas.md")

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

    @property
    def missing_keys(self):
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
        return re.sub(r'\\(["\\])', r"\1", raw[1:-1])
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


def _measurement_line(key: str, value) -> str:
    if value is None:
        return f"{key}:"
    if isinstance(value, int):
        return f"{key}: {value}"
    if key == "note":
        # a YAML double quoted scalar escapes the backslash itself first,
        # otherwise a note holding a path writes an unreadable file
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}: "{escaped}"'
    return f"{key}: {value}"


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
        return path.read_text(encoding="utf-8")

    def write(self, name: str, text: str) -> None:
        if name not in WRITABLE:
            raise InstanceError(f"{name} is not a file this consumer may write")
        path = self._child(self.root, name)
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=f".{name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

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

    # -- posts

    def posts(self) -> list[PostMeta]:
        directory = self.root / "posts"
        if not directory.is_dir():
            return []
        result = []
        for path in sorted(directory.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            block, _ = split_front_matter(raw)
            data = parse_front_matter(block) if block else {}
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
        return path.read_text(encoding="utf-8")

    def post_body(self, filename: str) -> str:
        path = self._child(self.root / "posts", filename)
        if not path.is_file():
            raise InstanceError(f"no such post: {filename}")
        _, body = split_front_matter(path.read_text(encoding="utf-8"))
        return body

    def pillar_counter(self) -> dict:
        counter: dict = {}
        for post in self.posts():
            if post.state == "published" and post.pillar is not None:
                counter[post.pillar] = counter.get(post.pillar, 0) + 1
        return counter

    def update_post_measurement(self, filename: str, *, measured,
                                inbound_connections, inbound_dms,
                                meeting_mentions, note) -> None:
        """Rewrite only the measurement lines of the front matter, textually,
        so the rest of the block and the body stay byte for byte."""
        path = self._child(self.root / "posts", filename)
        if not path.is_file():
            raise InstanceError(f"no such post: {filename}")
        raw = path.read_text(encoding="utf-8")
        block, _ = split_front_matter(raw)
        if block is None:
            raise InstanceError(f"{filename} has no front matter to update")
        updates = {
            "measured": measured,
            "inbound_connections": inbound_connections,
            "inbound_dms": inbound_dms,
            "meeting_mentions": meeting_mentions,
            "note": note,
        }
        new_block = block
        for key, value in updates.items():
            line = _measurement_line(key, value)
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
        for j in range(i, len(lines)):
            line = lines[j]
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            m = re.match(r"^-\s+\[P(\d+)\]\s+(?:`(\w+)`|(\w+))\s+(.*)$", line)
            if m and section.lower() != "used":
                label = m.group(2) or m.group(3)
                angles.append(Angle(pillar=int(m.group(1)), label=label,
                                    text=m.group(4).strip(), section=section))
                continue
            if angles and (line.startswith("  ") and line.strip()
                           and not line.strip().startswith("-")):
                angles[-1].text += " " + line.strip()
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
        return path.read_text(encoding="utf-8")

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
        if not re.search(r"^## Signature block\s*$",
                         self.read("profile.md"), re.MULTILINE):
            gaps.append(Gap("signature-missing"))
        for name in COMPANIONS:
            if not (self.root / name).is_file():
                gaps.append(Gap("file-missing", name))
        for post in self.posts():
            if post.missing_keys:
                gaps.append(Gap("post-keys-missing",
                                f"{post.filename}: {' '.join(post.missing_keys)}"))
        return gaps


def _section(text: str, heading: str) -> str | None:
    m = re.search(rf"^## {re.escape(heading)}\s*$", text, re.MULTILINE)
    if m is None:
        return None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    return rest[:nxt.start()] if nxt else rest
