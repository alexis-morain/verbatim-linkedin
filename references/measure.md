# Measurement

## The store

**One store, and it is the ledger inside the material.** One row per post,
carrying the nine columns the loops read, plus four descriptive fields nothing
parses. The format is [`material.md`](material.md), section 6, and
[`../docs/adr/0001-the-ledger-is-the-store.md`](../docs/adr/0001-the-ledger-is-the-store.md)
records why.

This file used to say the opposite: that the store was a front matter block on
top of each post file, and that any table was derived from those at read time.
That rule assumed a consumer with a filesystem. The engine is written against
a floor that cannot write a file, so the person carries one attachable
`material` and the ledger inside it is the record.

Two reasons it is one store and not two.

**Drift.** A single store cannot disagree with itself. At the floor a second
store would be kept in step by hand, or not at all, which is the drift the old
rule was written to prevent and would now cause.

**Editing.** Filling a row at J+7 is a thirty second job in a file already
open, and several posts get filled in one pass instead of one file at a time.

What is genuinely lost is per post provenance of the measurement: a ledger row
can be edited without touching the text it describes, where a front matter
block sat next to its own. The thresholds below are unchanged and still refuse
to conclude under two measured posts.

**Post bodies live in the corpus**, not here. Losing one costs a voice
reference rather than a measurement.

## What gets counted

Three numbers. None of them is a like.

| Field | Counts | Does not count |
|---|---|---|
| `inbound_connections` | Connection requests from profiles that match the target defined in the profile. | Everyone else. A recruiter, a student and a competitor are not signal. |
| `inbound_dms` | Messages that mention a project, a budget, a mandate, or a specific problem. | "Great post", "let's connect", automated pitches. |
| `meeting_mentions` | Times a post came up unprompted in a call or a meeting. | Times you brought it up yourself. |

Impressions, likes and comments can be recorded in `note` if they are
interesting. They are never the decision variable. A post can do all three of
the above with two hundred impressions, and none of them with twenty thousand.

**`state` is not decoration.** A row exists as soon as a post is drafted, and
without this field a list of drafts is indistinguishable from a list of
published posts. Every count in this document is over `state: published`
only. `published_ref` is what lets you find the thing again in the tool that
holds it, and it is the difference between "I scheduled that" and "did I?".

**Seven days.** Fill the line at J+7. Earlier and the number is still moving,
later and nobody remembers. If a post is measured late, record the real date in
`measured` rather than pretending.

## Confidence thresholds

The point of this section is to stop three data points from becoming a theory.
When a pattern is claimed across posts, it carries a status, and the status is
determined by how many measured posts support it:

| Measured posts supporting it | Status | What it authorises |
|---|---|---|
| 2 to 3 | **provisional** | A hypothesis, stated as one. Worth one deliberate test. Never a rule in the profile. |
| 4 to 6 | **emerging** | Worth acting on, worth writing down, still worth contradicting. |
| 7 or more | **confirmed** | Goes into the profile as a rule. |

Two guards on top:

- **A pattern from a single pillar does not generalise to the others.** Six
  post-mortems that outperform say something about post-mortems, not about the
  author's voice.
- **A pattern that only ever appears with one format is a format effect until
  proven otherwise.**

A Voice section built from a single published post says so, in a banner at
the top of it, and every skill that reads it defers to the hard style rules
instead of to the observed traits. The banner comes off when the corpus
is real, not when it feels awkward.

## The platform export

LinkedIn exports a spreadsheet of post performance over the trailing 365 days,
from the analytics section of the profile. It is the only place where
impressions per post are available without a third party.

Use it for one thing: filling in `note` in bulk after the fact, and spotting
posts you forgot to measure. It does not contain any of the three fields that
matter, because none of them are visible to the platform.
