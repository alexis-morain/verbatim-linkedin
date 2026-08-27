# Measurement

## The store

**One store, and it is the posts themselves.**

Every post file in the profile's `posts/` directory carries a front matter
block. That block is the source of truth. Any table, count or trend is derived
from it at read time and never written back anywhere.

```yaml
---
date: 2026-08-29          # publication date, not drafting date
pillar: 1                 # index into the profile's pillars
format: post-mortem       # one of references/formats.md
label: TRUST              # VISIBILITY | TRUST | ACTION
hook: |
  The first line, verbatim, as published.
chars: 2214
state: published          # draft | scheduled | published
published_ref: ""         # id in whatever tool scheduled it, empty for tier 0
measured: 2026-09-05      # date the line below was filled, empty until then
inbound_connections: 0    # from target profiles only
inbound_dms: 0            # messages that mention a project or a mandate
meeting_mentions: 0       # times the post came up in a call
note: ""                  # one line, free text, what happened
---
```

Two reasons for keeping it here rather than in a separate spreadsheet.

**Drift.** A second file has to be kept in sync with the first, and it never is.
The moment the aggregate disagrees with the posts, the aggregate wins by being
easier to read, and the record is quietly wrong.

**Editing.** The person filling this in is the author, seven days after
publishing, in thirty seconds. They are already in the post file, or they can be.
Nothing to open, nothing to import.

The cost is real and worth naming: computing a trend means reading every post
file. At the scale this operates on, a hundred posts a year, that is free.

> **Open decision.** If a future version needs a queryable store (a dashboard,
> a UI, cross-account comparison), this is the point where a derived index gets
> written. The rule to keep is that the index is regenerated from the posts and
> never edited directly.

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

**`state` is not decoration.** A file exists as soon as a post is drafted, and
without this field a directory of drafts is indistinguishable from a directory
of published posts. Every count in this document is over `state: published`
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

A profile whose `voice.md` was built from a single published post says so, at
the top of the file, and every skill that reads it defers to the hard style
rules instead of to the observed traits. The banner comes off when the corpus
is real, not when it feels awkward.

## The platform export

LinkedIn exports a spreadsheet of post performance over the trailing 365 days,
from the analytics section of the profile. It is the only place where
impressions per post are available without a third party.

Use it for one thing: filling in `note` in bulk after the fact, and spotting
posts you forgot to measure. It does not contain any of the three fields that
matter, because none of them are visible to the platform.
