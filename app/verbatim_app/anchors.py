"""The shape that carries anchoring, and the literal check over it.

references/anchoring.md is the contract; this file is its machine side. A
draft can be in another language than the interview, so nothing anchors the
post byte to byte: the model quotes its source in the interview language,
and this code checks that the quote exists in the transcript. It checks
presence, never truth, and it forgives typography, never words.

The parse is deliberately tolerant of list markers and letter case, because
a weaker model decorates, and a decorated block that still parses is worth
more than a strict one thrown away. What it does not tolerate is silence:
every line it could not read comes back as a problem, and an unpaired entry
does too, so a sloppy block is visible instead of half counted.

Standard library only, like the rest of the engine seam.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MARKER = "ANCHORS"

ITEM = re.compile(r"^(?:[-*]|\d+[.)])?\s*(POST|SAID)\s*:\s*(.*)$",
                  re.IGNORECASE)

#: Outside a block the seam is read strictly, capitals and all, because a
#: draft has every right to open a line with "Said:" in its own prose. The
#: tolerance of ITEM is for entries already inside a block, nowhere else.
STRAY = re.compile(r"^(?:[-*]|\d+[.)])?\s*(?:POST|SAID):")

#: Looser still, colon not required: the shape of an entry a model mangled.
#: Only ever used to say that a decorated marker left residue behind, never
#: to split anything.
RESIDUE = re.compile(r"^(?:[-*]|\d+[.)])?\s*(?:POST|SAID)\b")

#: An entry shorter than this, typography folded, identifies nothing: one
#: letter is found in any draft and any transcript, and an anchor that
#: cannot miss is an alarm that cannot ring.
MIN_ANCHOR = 10

#: Typography that varies between keyboards and languages, folded before
#: comparison. Words are never touched.
TYPOGRAPHY = {
    "’": "'", "ʼ": "'", "‘": "'",
    "“": '"', "”": '"', "«": '"', "»": '"', "„": '"',
    " ": " ", " ": " ",
}

QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("“", "”"), ("«", "»"), ("‘", "’"))


@dataclass(frozen=True)
class Anchor:
    fragment: str  # POST: a piece of the draft, copied exactly
    quote: str     # SAID: the interview sentence backing it, word for word


@dataclass(frozen=True)
class Output:
    """A model answer split into the draft and its anchors block."""
    draft: str
    anchors: tuple
    problems: tuple


@dataclass(frozen=True)
class Verdict:
    anchor: Anchor
    in_draft: bool
    in_transcript: bool

    @property
    def status(self) -> str:
        if not self.in_draft:
            return "dangling"
        if not self.in_transcript:
            return "fabricated"
        return "anchored"


def split_output(text: str) -> Output:
    """Split a model answer at the last `ANCHORS` line and parse the block.

    No block means no anchors, which is an answer too: the caller sees an
    empty tuple and treats the whole draft as unanchored.
    """
    lines = text.splitlines()
    start = None
    passed_over = []
    for index, line in enumerate(lines):
        kind = _marker(line)
        if kind == "exact":
            start = index
        elif kind == "decorated" and any(
                STRAY.match(later.strip()) for later in lines[index + 1:]):
            # A decorated spelling only counts when strictly readable
            # entries actually follow: a post is allowed to put the bare
            # word on a line of its own, prose below included, and eating
            # its closing paragraphs would lose somebody's text.
            start = index
        elif kind == "decorated":
            passed_over.append(index)
    if start is None:
        problems = list(_strays(lines))
        for index in passed_over:
            if any(RESIDUE.match(later.strip())
                   for later in lines[index + 1:]):
                # Not read as a block, not passed over in silence either:
                # the draft keeps every line, and the reader is told the
                # marker shaped line left entry shaped residue behind it.
                problems.append(
                    "a line that reads like an anchors marker is not "
                    "followed by readable entries: "
                    f"{lines[index].strip()[:80]}")
        return Output(draft=text, anchors=(), problems=tuple(problems))
    draft = "\n".join(lines[:start]).rstrip()
    anchors, problems = [], list(_strays(lines[:start]))
    pending = None
    swallowed = False  # the last POST was already reported, eat its SAID

    def unpaired(fragment):
        problems.append(f"POST entry has no SAID quote: {fragment[:80]}")

    for line in lines[start + 1:]:
        line = line.strip()
        if not line:
            continue
        match = ITEM.match(line)
        if match is None:
            problems.append(
                f"line in the anchors block is not a POST or SAID entry: "
                f"{line[:80]}")
            continue
        kind, value = match.group(1).upper(), _unquote(match.group(2).strip())
        if kind == "POST":
            if pending is not None:
                unpaired(pending)
            pending, swallowed = None, False
            if not value:
                problems.append("empty POST entry")
                swallowed = True
            elif not anchorable(value):
                problems.append(
                    f"POST entry too short to identify a claim: {value[:80]}")
                swallowed = True
            else:
                pending = value
        else:
            if pending is None:
                # One fault, one complaint: a SAID whose POST was already
                # reported is part of that finding, not a second one.
                if not swallowed:
                    problems.append(
                        f"SAID entry has no POST claim: {value[:80]}")
                swallowed = False
            elif not value:
                unpaired(pending)
                pending = None
            elif not anchorable(value):
                problems.append(
                    f"SAID entry too short to identify a quote: {value[:80]}")
                pending = None
            else:
                anchors.append(Anchor(fragment=pending, quote=value))
                pending = None
    if pending is not None:
        unpaired(pending)
    return Output(draft=draft, anchors=tuple(anchors),
                  problems=tuple(problems))


def _marker(line: str):
    """Whether this line opens the block: "exact" for the bare marker,
    "decorated" for the spellings a model dresses a title in, a heading
    prefix, bold stars, a trailing colon, any case. Other words on the
    line make it prose, never the marker."""
    stripped = line.strip()
    if stripped == MARKER:
        return "exact"
    bare = stripped.lstrip("#").strip().strip("*").strip()
    if bare.endswith(":"):
        bare = bare[:-1].strip().strip("*").strip()
    return "decorated" if bare.casefold() == "anchors" else None


def _strays(lines) -> list:
    """Entry shaped lines sitting in the draft, outside any block. A marker
    the parser could not read leaves its entries stranded up here, and a
    stranded entry reported is a mangled block made visible instead of a
    post shipping with POST and SAID lines in its body."""
    return [f"entry shaped line outside the anchors block: "
            f"{line.strip()[:80]}"
            for line in lines if STRAY.match(line.strip())]


def _unquote(value: str) -> str:
    for opening, closing in QUOTE_PAIRS:
        if (len(value) >= 2 and value.startswith(opening)
                and value.endswith(closing)):
            return value[1:-1].strip()
    return value


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for varied, folded in TYPOGRAPHY.items():
        text = text.replace(varied, folded)
    return re.sub(r"\s+", " ", text).strip().casefold()


def contains(haystack: str, needle: str) -> bool:
    """Whether the needle occurs in the haystack, typography folded. An
    empty needle matches nothing: it proves nothing was said."""
    wanted = normalize(needle)
    return bool(wanted) and wanted in normalize(haystack)


def anchorable(text: str) -> bool:
    """Whether an entry is substantial enough to anchor anything. Below
    MIN_ANCHOR folded characters a match proves nothing, so the entry is
    treated as absent everywhere a match would count in its favour."""
    return len(normalize(text)) >= MIN_ANCHOR


def verify(draft: str, anchors, transcript: str) -> list:
    """One verdict per anchor. Two of the three alarm states live here,
    dangling and fabricated; the third, unanchored, belongs to the draft
    rather than to any anchor and is read off it by `uncovered`."""
    return [Verdict(anchor=anchor,
                    in_draft=anchorable(anchor.fragment)
                    and contains(draft, anchor.fragment),
                    in_transcript=anchorable(anchor.quote)
                    and contains(transcript, anchor.quote))
            for anchor in anchors]


def sentences(draft: str) -> list:
    """The draft cut into rough sentences: line breaks first, then sentence
    punctuation. Rough is enough, this feeds a highlight, not a rewrite."""
    found = []
    for line in draft.splitlines():
        for piece in re.split(r"(?<=[.!?])\s+", line.strip()):
            if piece.strip():
                found.append(piece.strip())
    return found


def uncovered(draft: str, anchors) -> list:
    """The unanchored claims: draft sentences no anchor fragment touches.

    A sentence is covered when a fragment that really is in the draft
    contains it or sits inside it. A dangling fragment covers nothing,
    which is the point of checking it against the draft first.
    """
    fragments = [normalize(anchor.fragment) for anchor in anchors
                 if anchorable(anchor.fragment)
                 and contains(draft, anchor.fragment)]
    found = []
    for sentence in sentences(draft):
        folded = normalize(sentence)
        if not folded:
            continue
        if any(fragment in folded or folded in fragment
               for fragment in fragments):
            continue
        found.append(sentence)
    return found
