"""Cut a post into the blocks a reader sees, and rewrite one of them.

This is `sections.py` for prose. A profile is addressed by its `## `
headings; a post has none, so the unit here is the block between blank
lines, which is what a reader scrolls past and what somebody points at when
they say this bit is too vague.

The span is the whole point, and it is the same reason `sections.py` has
one. A revision addressed to one block rewrites those characters and leaves
every other byte of the post where it was. That is a guarantee by
construction, not a diff inspected afterwards and hoped about.

Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from .shown import shown


class PassageGone(Exception):
    """The block a screen was addressing is not the block on disk any more,
    or the rewrite offered for it is not one."""


@dataclass(frozen=True)
class Passage:
    """One block of a post, and the span it occupies."""
    text: str
    start: int
    end: int
    digest: str
    index: int
    #: The digest of the whole post this block was read out of. A rewrite
    #: lands in that post and in no other, whatever the block at its index
    #: says. Everything that tried to infer "has a rewrite already landed"
    #: from the block alone missed a case: the block can be untouched while
    #: the post around it is not the post any more. Required, with no
    #: default, so nothing can build a passage that does not say where it
    #: came from and slip past the check below.
    of: str


#: A blank line, whitespace included, and the carriage return a file that
#: came off another machine carries. One or more blank lines is one break: a
#: person who left three between two paragraphs did not write an empty one.
#: Without the `\r` a CRLF post is one single block, the picker never
#: appears, and nothing says why.
BREAK = re.compile(r"\r?\n[ \t]*(?=\r?\n)\r?\n")


def passages_of(body: str) -> list:
    """Every block of a post, in order, with the span it occupies."""
    of = shown(body)
    bounds, opens = [], 0
    for gap in BREAK.finditer(body):
        bounds.append((opens, gap.start()))
        opens = gap.end()
    bounds.append((opens, len(body)))

    found = []
    for opens, closes in bounds:
        block = body[opens:closes]
        text = block.strip()
        if not text:
            continue
        lead = len(block) - len(block.lstrip())
        found.append(Passage(text=text, start=opens + lead,
                             end=opens + lead + len(text),
                             digest=shown(text), index=len(found), of=of))
    return found


def passage_at(body: str, index: int, digest: str) -> Passage:
    """The block a screen was addressing, or a refusal.

    Two keys, because each answers a different question. The index says
    which block, and it is the only thing that separates two that read
    alike, which is why there is no refusal for a repeated paragraph: the
    digest cannot tell them apart and does not have to. The digest says the
    screen was not stale: a turn can rewrite the post behind a page already
    drawn, and a revision aimed at what used to be the third paragraph must
    not land on whatever is there now.
    """
    found = passages_of(body)
    if not 0 <= index < len(found):
        raise PassageGone(
            f"this post has no passage {index}; there are {len(found)}")
    passage = found[index]
    if passage.digest != digest:
        raise PassageGone(
            "that passage has changed since the screen was drawn; read it "
            "again before asking for a rewrite of it")
    return passage


def replace_passage(body: str, passage: Passage, text: str) -> str:
    """Rewrite one block and leave every other byte where it was.

    The replacement is trimmed, since it arrives from a model that may have
    wrapped it in the blank lines it saw around the original, and those
    blank lines are the span's neighbours rather than part of it. An empty
    one is refused: taking a passage out is a decision somebody makes, and a
    model that answered with nothing must not silently shorten a post.

    **The block is found again in this body rather than trusted.** Offsets
    are only true of the text they were read from, and this function is
    reached twice from one turn the moment a model puts two calls in one
    message, which both wired providers do and neither forbids:
    `tool_choice` asks for at least one call, never at most one. The second
    call arrives holding the first call's offsets, and splicing those into
    the body the first one rewrote eats the block after it and cuts the one
    after that mid-word.

    **What is checked is the post, not the block.** Twice this guard was
    written as a proof about the block and twice it missed a case, because
    a block can be untouched while the post around it is not the post any
    more. An additive revision leaves the old bytes at the old span. A
    revision that answers with the block, a blank line and an added
    sentence splits it in two and leaves the first half byte-identical, so
    its index and its digest both still match while everything after it has
    moved. Neither is detectable from the block.

    So a passage carries the digest of the post it was read out of, and a
    rewrite lands in that post and in no other. The second call of a message
    is refused because the first one changed the post, whatever it changed.
    A first call that changed nothing, an identity rewrite, leaves the body
    it was read from, so a second one still lands: that is not the same
    thing as one rewrite per body, and it is right. The offsets are true of
    that body and the chain ends at the first call that actually writes.
    """
    written = text.strip()
    if not written:
        raise PassageGone(
            "an empty rewrite would delete the passage; removing it is a "
            "decision, and not this one")
    if shown(body) != passage.of:
        raise PassageGone(
            "this post is not the one that passage was read out of: it has "
            "been rewritten since, and a rewrite may already have landed. "
            "Ask for the post again rather than sending a second rewrite "
            "into it")
    return body[:passage.start] + written + body[passage.end:]


def changed(before: str, after: str) -> set:
    """The blocks of `after` that are not the blocks of `before`.

    By digest and by position, over the same cut everything else here uses,
    so what comes back is about the text a reader sees. Offsets cannot
    answer this: they are true of one body and mean nothing in the other.

    `SequenceMatcher` rather than a set difference, because the question is
    which block on the screen moved, not which texts are new. A set
    difference marks both copies of a repeated paragraph when one of them is
    edited, and it marks nothing at all when a block is only moved, which is
    the opposite mistake. The matcher answers by position and gets both.

    An empty `before` marks nothing on purpose. A first draft is not a
    change, and every rule that answers this from the post alone paints the
    whole of it.
    """
    if not before.strip():
        return set()
    was = [passage.digest for passage in passages_of(before)]
    now = [passage.digest for passage in passages_of(after)]
    moved = set()
    for kind, _, _, opens, closes in SequenceMatcher(
            a=was, b=now, autojunk=False).get_opcodes():
        if kind != "equal":
            moved.update(range(opens, closes))
    return moved


def line_blocks(body: str) -> list:
    """Which block each line of the post belongs to, in the order of
    `splitlines`, with `None` for the blank ones.

    The bridge between the two cuts of one post. A screen paints it line by
    line, which is what `anchors.lines` hands over, and a version marker is
    about blocks. Both walk `splitlines`, so an index in this list is an
    index in that one, and nothing has to be recut to paint a block.
    """
    spans = []
    at = 0
    for line in body.splitlines(keepends=True):
        bare = line.rstrip("\r\n")
        spans.append((at, at + len(bare)))
        at += len(line)
    found = passages_of(body)
    placed = []
    for opens, closes in spans:
        if opens == closes:
            placed.append(None)
            continue
        placed.append(next(
            (passage.index for passage in found
             if passage.start <= opens and closes <= passage.end), None))
    return placed
