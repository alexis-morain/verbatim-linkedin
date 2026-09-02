"""Everything `references/measure.md` counts, recomputed at read time.

The contract implemented here is references/measure.md. Nothing in this file
is ever written back to a post: a view is built from the front matter of the
files as they are on disk, the day it is asked for. Sums and counts only, no
mean, because a mean over one measured post is a figure the record does not
hold.

Standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


#: Days between publishing and filling the measurement line. The one number
#: `references/measure.md` fixes: earlier and the count is still moving, later
#: and nobody remembers.
MEASURE_DAYS = 7


def pattern_status(measured: int) -> str:
    """How much a pattern supported by this many measured posts authorises.

    The table of `references/measure.md`, and the whole point of it is that
    three data points do not become a theory. Nothing here averages: the
    status is a count, so a bucket cannot look stronger by having produced a
    bigger number once.
    """
    if measured >= 7:
        return "confirmed"
    if measured >= 4:
        return "emerging"
    if measured >= 2:
        return "provisional"
    return "none"


@dataclass
class Sums:
    """The three numbers added up over a set of measured posts.

    A field is `None` when no measured post carried it, which is not the same
    fact as zero and is never rendered as one. Sums and counts only: no mean
    lives in this file, because a mean over one post is a figure the record
    does not hold.
    """
    connections: int | None = None
    dms: int | None = None
    meetings: int | None = None


@dataclass
class Bucket:
    key: str
    posts: int
    measured: int
    sums: Sums
    status: str


@dataclass
class MeasureView:
    rows: list = field(default_factory=list)
    measured: int = 0
    totals: Sums = field(default_factory=Sums)
    due: list = field(default_factory=list)
    by_pillar: list = field(default_factory=list)
    by_format: list = field(default_factory=list)
    by_label: list = field(default_factory=list)
    #: The two guards of `references/measure.md`, as facts about right now.
    #: They are not applied here: a screen that silently drops a pattern
    #: teaches nothing, so the guard is shown and the reader applies it.
    single_pillar: bool = False
    single_format: bool = False


def view(posts, today: date) -> MeasureView:
    """Everything `references/measure.md` counts, recomputed here and now.

    Over `state: published` alone, like every count in this system. A
    draft and a scheduled post are in no list and no total: a file exists
    as soon as a post is drafted, and counting one would report a channel
    that has not happened yet.

    `today` is passed in rather than read from the clock. What is due
    depends on the day, and a screen whose content changes with the wall
    clock is a screen no test can pin down.
    """
    rows = [p for p in posts if p.state == "published"]
    measured = [p for p in rows if p.measured]
    due = [p for p in rows
           if not p.measured and _is_due(p.date, today)]
    return MeasureView(
        rows=rows,
        measured=len(measured),
        totals=_sums(measured),
        due=due,
        by_pillar=_buckets(rows, lambda p: None if p.pillar is None
                           else str(p.pillar)),
        by_format=_buckets(rows, lambda p: p.format),
        by_label=_buckets(rows, lambda p: p.label),
        single_pillar=_one_of(measured, lambda p: p.pillar),
        single_format=_one_of(measured, lambda p: p.format),
    )


def _is_due(when, today: date) -> bool:
    """Is this post old enough that its line should already be filled.

    A date this cannot read makes the post not due. Guessing at one would put
    a post on the list to act on because of a typo, and the conformance report
    already says which file has an unreadable key.
    """
    try:
        published = date.fromisoformat(str(when))
    except (TypeError, ValueError):
        return False
    return published <= today - timedelta(days=MEASURE_DAYS)


def _sums(posts) -> Sums:
    """The three fields added up, each over the posts that carried it."""
    def total(name):
        values = [getattr(p, name) for p in posts
                  if getattr(p, name) is not None]
        return sum(values) if values else None

    return Sums(connections=total("inbound_connections"),
                dms=total("inbound_dms"),
                meetings=total("meeting_mentions"))


def _buckets(rows, key) -> list:
    """One bucket per value of `key`, ordered by it.

    A row whose key is empty joins no bucket. The front matter of that post
    is incomplete, which the conformance report says by name; inventing a
    bucket for it would put a count under a heading nobody wrote.
    """
    grouped: dict = {}
    for post in rows:
        name = key(post)
        if name:
            grouped.setdefault(name, []).append(post)
    buckets = []
    for name, posts in grouped.items():
        measured = [p for p in posts if p.measured]
        buckets.append(Bucket(key=name, posts=len(posts),
                              measured=len(measured), sums=_sums(measured),
                              status=pattern_status(len(measured))))
    buckets.sort(key=lambda b: b.key)
    return buckets


def _one_of(posts, key) -> bool:
    """Do all these posts share one value of `key`, with at least two of them.

    One post is not a pattern, so it cannot be a pattern trapped in one
    pillar either, and saying a guard bites on a single post would read as a
    finding about a channel that has published once.
    """
    values = {key(p) for p in posts if key(p) is not None}
    return len(posts) >= 2 and len(values) == 1
