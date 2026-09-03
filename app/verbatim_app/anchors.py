"""The shape that carries anchoring, and the literal check over it.

references/anchoring.md is the contract; this file is its machine side. A
draft can be in another language than the interview, so nothing anchors the
post byte to byte: the model quotes its source in the interview language,
and this code checks that the quote exists in the transcript. It checks
presence, never truth, and it forgives typography, never words.

Since the sheet seam, a quote also names where it lives: `SAID:` is the
transcript, `SHEET:` is the sheet the person approved, and each one is looked
for in the source it names and nowhere else. The label a screen shows over a
backing is derived from that provenance, never written into a template; the
`Provenance` section of the contract says why, and the two provenances that
have no seam here, the profile and the engine's own speech, are the reason.

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
from dataclasses import dataclass, replace

MARKER = "ANCHORS"

#: Where a backing lives: the provenances of `references/anchoring.md` that
#: have a seam. The transcript is every word the person typed; the sheet is
#: the one they approved. The profile and the engine's own speech have no
#: seam here, on purpose and for good: a quote of either wears one of these
#: two labels and comes back fabricated, because it is looked for in the
#: source the label names and nowhere else.
TRANSCRIPT = "transcript"
SHEET = "sheet"

#: The seam label of each provenance, as the block spells it. One table, and
#: the key the same pair travels under in a tool call and on disk is the
#: label in lower case, so the three spellings of one provenance cannot
#: drift apart.
SEAMS = {"SAID": TRANSCRIPT, "SHEET": SHEET}
LABEL_OF = {provenance: label for label, provenance in SEAMS.items()}
KEYS = {label.lower(): provenance for label, provenance in SEAMS.items()}
KEY_OF = {provenance: key for key, provenance in KEYS.items()}

_ENTRY = "|".join(["POST", *SEAMS])

ITEM = re.compile(rf"^(?:[-*]|\d+[.)])?\s*({_ENTRY})\s*:\s*(.*)$",
                  re.IGNORECASE)

#: Outside a block the seam is read strictly, capitals and all, because a
#: draft has every right to open a line with "Said:" in its own prose. The
#: tolerance of ITEM is for entries already inside a block, nowhere else.
STRAY = re.compile(rf"^(?:[-*]|\d+[.)])?\s*(?:{_ENTRY}):")

#: Looser still, colon not required: the shape of an entry a model mangled.
#: Only ever used to say that a decorated marker left residue behind, never
#: to split anything.
RESIDUE = re.compile(rf"^(?:[-*]|\d+[.)])?\s*(?:{_ENTRY})\b")

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
class Piece:
    """One claim of the draft, and which anchors cover it.

    The positions rather than a bare flag, because a claim covered by a
    fabricated quote is not a claim in good standing: whoever paints this
    has to be able to ask what backs it, not only whether anything does.
    `uncovered` asks the weaker question, which is the contract's.
    """
    text: str
    #: The anchors covering this claim, themselves and not their positions:
    #: a position would have to stay in step with a verdict list built
    #: somewhere else, and two functions apart is exactly where that stops
    #: being true.
    by: tuple = ()

    @property
    def covered(self) -> bool:
        return bool(self.by)


@dataclass(frozen=True)
class Anchor:
    fragment: str  # POST: a piece of the draft, copied exactly
    quote: str     # the line backing it, word for word: SAID: or SHEET:
    #: Which source the quote is claimed from, one of the provenances above.
    #: The transcript by default: it was the only provenance the block knew
    #: before the sheet seam landed, so every pair written that way still
    #: means what it meant.
    provenance: str = TRANSCRIPT


@dataclass(frozen=True)
class Output:
    """A model answer split into the draft and its anchors block.

    `block` says whether a block was found at all, which no other field can
    answer: a block holding nothing readable and no block at all both come
    back with empty anchors, and only one of the two is an answer somebody
    meant as a draft.
    """
    draft: str
    anchors: tuple
    problems: tuple
    block: bool = False


@dataclass(frozen=True)
class Verdict:
    anchor: Anchor
    in_draft: bool
    #: Whether the quote is in the source its provenance names. That one and
    #: no other: a sheet line found in the transcript is not a sheet backing,
    #: and an interview sentence found only in the sheet was never said.
    in_source: bool

    @property
    def status(self) -> str:
        if not self.in_draft:
            return "dangling"
        if not self.in_source:
            return "fabricated"
        return "anchored"


def split_output(text: str) -> Output:
    """Split a model answer at the last `ANCHORS` line and parse the block.

    No block means no anchors, which is an answer too: the caller sees an
    empty tuple and treats the whole draft as unanchored.
    """
    raw = text.splitlines()
    start = None
    passed_over = []
    for index, line in enumerate(raw):
        kind = _marker(line)
        if kind == "exact":
            start = index
        elif kind == "decorated" and any(
                STRAY.match(later.strip()) for later in raw[index + 1:]):
            # A decorated spelling only counts when strictly readable
            # entries actually follow: a post is allowed to put the bare
            # word on a line of its own, prose below included, and eating
            # its closing paragraphs would lose somebody's text.
            start = index
        elif kind == "decorated":
            passed_over.append(index)
    if start is None:
        problems = list(_strays(raw))
        for index in passed_over:
            if any(RESIDUE.match(later.strip())
                   for later in raw[index + 1:]):
                # Not read as a block, not passed over in silence either:
                # the draft keeps every line, and the reader is told the
                # marker shaped line left entry shaped residue behind it.
                problems.append(
                    "a line that reads like an anchors marker is not "
                    "followed by readable entries: "
                    f"{raw[index].strip()[:80]}")
        return Output(draft=text, anchors=(), problems=tuple(problems))
    draft = "\n".join(raw[:start]).rstrip()
    anchors, problems = [], list(_strays(raw[:start]))
    pending = None
    swallowed = False  # the last POST was already reported, eat its SAID

    def unpaired(fragment):
        problems.append(
            f"POST entry has no SAID or SHEET quote: {fragment[:80]}")

    for line in raw[start + 1:]:
        line = line.strip()
        if not line:
            continue
        match = ITEM.match(line)
        if match is None:
            problems.append(
                f"line in the anchors block is not a POST, SAID or SHEET "
                f"entry: {line[:80]}")
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
                # One fault, one complaint: a quote whose POST was already
                # reported is part of that finding, not a second one.
                if not swallowed:
                    problems.append(
                        f"{kind} entry has no POST claim: {value[:80]}")
                swallowed = False
            elif not value:
                unpaired(pending)
                pending = None
            elif not anchorable(value):
                problems.append(
                    f"{kind} entry too short to identify a quote: {value[:80]}")
                pending = None
            else:
                anchors.append(Anchor(fragment=pending, quote=value,
                                      provenance=SEAMS[kind]))
                pending = None
    if pending is not None:
        unpaired(pending)
    return Output(draft=draft, anchors=tuple(anchors),
                  problems=tuple(problems), block=True)


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


def _strays(raw) -> list:
    """Entry shaped lines sitting in the draft, outside any block. A marker
    the parser could not read leaves its entries stranded up here, and a
    stranded entry reported is a mangled block made visible instead of a
    post shipping with POST and SAID lines in its body."""
    return [f"entry shaped line outside the anchors block: "
            f"{line.strip()[:80]}"
            for line in raw if STRAY.match(line.strip())]


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


def verify(draft: str, anchors, sources) -> list:
    """One verdict per anchor. Two of the three alarm states live here,
    dangling and fabricated; the third, unanchored, belongs to the draft
    rather than to any anchor and is read off it by `uncovered`.

    `sources` maps a provenance to the text a quote of that provenance is
    looked for in, and it is looked for there and nowhere else. A sheet line
    found in the transcript, or an interview sentence found only in the
    sheet, is a quote claimed from a source that does not hold it, which is
    what fabricated means. A provenance the mapping does not name is a
    source that said nothing, so every quote claimed from it is fabricated
    too; `interview.sources` leaves the sheet out until it is approved.
    """
    return [Verdict(anchor=anchor,
                    in_draft=anchorable(anchor.fragment)
                    and contains(draft, anchor.fragment),
                    in_source=anchorable(anchor.quote)
                    and contains(sources.get(anchor.provenance, ""),
                                 anchor.quote))
            for anchor in anchors]


def sentences(draft: str) -> list:
    """The draft cut into rough sentences: line breaks first, then sentence
    punctuation. Rough is enough, this feeds a highlight, not a rewrite."""
    return [piece.text for row in _rows(draft) for piece in row]


def _rows(draft: str) -> list:
    """The same cut, keeping the lines. A screen shows paragraphs, and a
    draft flattened to a sentence list cannot be given back its shape."""
    found = []
    for line in draft.splitlines():
        found.append([Piece(text=piece.strip())
                      for piece in re.split(r"(?<=[.!?])\s+", line.strip())
                      if piece.strip()])
    return found


def lines(draft: str, anchors) -> list:
    """The draft as a screen shows it: one list per line, one piece per
    claim, each piece saying whether an anchor covers it.

    A claim is covered when a fragment that really is in the draft contains
    it or sits inside it. A dangling fragment covers nothing, which is the
    point of checking it against the draft first.

    This is the one place coverage is decided. `uncovered` reads it rather
    than deciding again: two implementations of the same rule drift, and the
    direction they drift in is the one that flatters the engine.
    """
    fragments = [(anchor, normalize(anchor.fragment)) for anchor in anchors
                 if anchorable(anchor.fragment)
                 and contains(draft, anchor.fragment)]
    drawn = []
    for row in _rows(draft):
        drawn.append([replace(piece, by=tuple(
            anchor for anchor, fragment in fragments
            if fragment in normalize(piece.text)
            or normalize(piece.text) in fragment)) for piece in row])
    return drawn


def uncovered(draft: str, anchors) -> list:
    """The unanchored claims: draft sentences no anchor fragment touches."""
    return [piece.text for row in lines(draft, anchors)
            for piece in row if not piece.covered]
