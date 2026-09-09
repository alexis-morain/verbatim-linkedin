# The material

One file, held by the person, attached to a conversation. It holds everything
the engine is allowed to draw a fact from about them, and it replaces the four
files and two directories an earlier version spread across a folder.

**The rule that makes the rest work.** If a fact is not in this file, in the
corpus the person pasted, or in the transcript of the interview happening right
now, it does not exist and it is not invented.

## Read this before migrating anything

This document is a checklist before it is a format. The list below exists so a
migration can be compared against something: this repository has already lost a
signature block in a hand migration, silently, because there was nothing to
compare the result to. Fill the table, then check the table.

Every row is one field. A row marked **required** means the engine changes its
behaviour when the field is missing, and the *If it goes missing* column says
how. A row that is not required can be empty, and empty is different from
absent: keep the heading with nothing under it, so a reader can tell "nothing
to say here" from "nobody wrote this yet".

## Section order

The file is read top to bottom by a person, so it is ordered the way a person
needs it, not the way the engine indexes it.

| # | Section | Was |
|---|---|---|
| 1 | Status | `profile.md`, Status block |
| 2 | Profile | `profile.md`, the rest |
| 3 | Voice | `voice.md` |
| 4 | Pillars | `pillars.md` |
| 5 | Ideas | `ideas.md` |
| 6 | Ledger | the front matter of every file in `posts/` |

The corpus stays out. A hundred published posts inside an attached file is the
one thing that does not scale, and by ADR 0001 losing a post body costs a voice
reference rather than a measurement. The person pastes three to five posts at
setup, and the engine reads them from the transcript.

## 1. Status

Five fields, and the engine reads all five before it does anything else.

| Field | Required | Values | If it goes missing |
|---|---|---|---|
| `filled` | yes | `yes` / `no` | Treated as `no`: every skill falls back to generic rules and offers to run setup rather than pretending it knows the person. |
| `source` | yes | `template` / `interview` | Same fallback as `filled: no`. |
| `updated` | no | date | Nothing breaks. A stale date is a prompt to re-run the voice rewrite. |
| `interview_language` | yes | language code or name | The engine asks in English, which is the wrong language for most people. |
| `output_language_default` | yes | language code or name | Posts come out in the interview language, which is a different decision. |

**The three language axes stay independent.** The engine is written in English,
the interview happens in `interview_language`, and the post is written in
`output_language_default` with a per post override. Someone interviewed in
French who publishes in English is the normal case, not an edge case.

> **Open naming decision, carried over rather than settled here.** The old
> template called the second field `interface_language` while describing it as
> "the language you are interviewed in". The name and the meaning disagree.
> Renaming it is a decision for the person doing 1.4, not something to change
> quietly inside a migration, which is exactly the class of loss this document
> exists to prevent. Both names are recorded here so neither is lost.

## 2. Profile

Eleven prose sections and one verbatim block. None of them is a field with a
value: each is a heading with prose under it, and the engine reads the prose.

| Section | Required | Holds | If it goes missing |
|---|---|---|---|
| What I sell | yes | The thing, end to end, plus what separates it from the nearest adjacent role. | The engine has no idea what a post is arguing for. |
| Who I write to | yes | Priority 1, Priority 2, Out of scope on this channel, Abandoned. | Posts get written to a target the person already walked away from. |
| What this channel is for | yes | What it produces, ordered, and what it is not for. | Every post drifts toward whatever the format rewards. |
| Objective and cadence | yes | Posts per period, business objective, decision threshold. | The pillar ratio has nothing to derive itself from. |
| Core conviction | yes | What they hold true that their field does not. | The engine produces tutorials instead of stances. |
| What I fight | yes | Named, concrete, arguable. | Same failure as an empty conviction. |
| What I can prove | yes | One bullet per fact, each with its source. | Every angle is unanchorable and the interview has nothing to stand on. |
| True, but needs a call | no | Rates, margins, anything under NDA. | It leaks into a draft by accident. |
| Names I must never cite | no | Clients and partners who have not agreed. | A name reaches a published post. |
| What I never say | yes | The four defaults plus their own additions. | The engine writes a promise the person does not make. |
| Signature block | no | Verbatim text, appended after a blank line. | **The failure this document was written after.** It is concatenated, never shown to the model and never regenerated: a generated signature drifts on every post until it belongs to someone else. Empty is a valid answer; absent is a loss. |

## 3. Voice

| Part | Required | Holds | If it goes missing |
|---|---|---|---|
| Confidence banner | yes, while under five posts | How many published posts the traits were built on. | Traits read from three posts get treated as rules. |
| Hard rules | yes | The pack's style rules, which are authoritative. | The observed traits win an argument they should lose. |
| Traits observed | no | One trait per entry, **each followed by the sentence it was read from.** | A trait without a quote is a guess, and the engine cannot tell the two apart. |
| What the corpus does not say yet | yes | Which pillars and registers are unobserved. | Traits from one pillar get extrapolated onto every other. |
| Rewrite | no | The condition for redoing this section. | The provisional banner never comes off, or comes off unearned. |

**A trait carries its quote or it is not a trait.** This is the plainest case of
the visible guard rule: the engine cannot verify that a trait was really read
from the corpus, so the quote sits next to it where a person can check.

## 4. Pillars

Three pillars, each with the same shape, plus two blocks around them.

| Part | Required | Holds | If it goes missing |
|---|---|---|---|
| Objective | yes | What the ratio is derived from, so it can be argued with. | The ratio looks arbitrary and gets ignored. |
| Pillar title | yes | One line, the claim, not the topic. | |
| Ratio | yes | `n of <posts per period>`. The three sum to the cadence. | Balancing has nothing to count against. |
| Effect on the reader | yes | authority / trust / connection. | |
| Description and material | yes | What it covers, and what the person already has to prove it. | The pillar runs on opinion. |
| Verifiability requirement | no | Per pillar. | A pillar that needs a measured element per post quietly stops having one. |
| Balancing | yes | Count the last posts, offer from the pillar that is behind. | The cadence holds and the mix drifts. |

## 5. Ideas

| Part | Required | Holds | If it goes missing |
|---|---|---|---|
| Next session | no | The angle already chosen for next time. | A session opens on a blank page. |
| Angles, by pillar | yes | `[pillar] LABEL angle, and the material that already exists`. **An angle contains a position; a subject does not.** | The bank fills with topics, and a topic cannot be written from. |
| Used | yes | date, pillar, angle, where the post went. | The same angle gets written twice. |

## 6. Ledger

One entry per post, replacing the front matter that used to sit on top of each
post file. **The ledger is the store** (ADR 0001): it is written to directly,
and nothing is derived from post bodies any more.

Thirteen fields. **Nine are read by the loops and go in the table. Four are
descriptive and go in a free text tail nothing parses.**

### The nine parsed columns

| Column | Holds | Read by |
|---|---|---|
| `date` | Publication date, not drafting date. | Ordering, and the J+7 reminder. |
| `pillar` | Index into the pillars section. | Balancing, and every per pillar guard. |
| `format` | One of `references/formats.md`. | The format effect guard, and the per format register. |
| `label` | `VISIBILITY` / `TRUST` / `ACTION`. | The mix across recent posts. |
| `state` | `draft` / `scheduled` / `published`. | **Every count in measurement is over `published` only.** Without it a list of drafts is indistinguishable from a list of published posts. |
| `measured` | Date the three numbers were filled, empty until then. | Spotting posts nobody measured. A post measured late records the real date rather than pretending. |
| `inbound_connections` | Connection requests from target profiles only. | Confidence thresholds. |
| `inbound_dms` | Messages naming a project, budget, mandate or specific problem. | Confidence thresholds. |
| `meeting_mentions` | Times the post came up unprompted in a call. | Confidence thresholds. |

None of the three numbers is a like. Impressions, likes and comments are never
the decision variable, and a post can do all three of these on two hundred
impressions and none of them on twenty thousand.

### The four in the free text tail

| Field | Holds | Why it is not a column |
|---|---|---|
| `hook` | The first line, verbatim, as published. | Multi line, and it is how a person recognises which post a row is. |
| `chars` | Length of the published body. | Descriptive. Nothing decides on it. |
| `published_ref` | Id in whatever tool scheduled it, empty at the floor. | Opaque string. It is the difference between "I scheduled that" and "did I?". |
| `note` | One line, free text, what happened. | Nothing parses it, on purpose. Impressions and likes live here when they are interesting. |

### Confidence thresholds, unchanged

Two to three measured posts is **provisional**, four to six **emerging**, seven
or more **confirmed**. Nothing concludes under two measured posts, a pattern
from a single pillar does not generalise to the others, and a pattern that only
appears with one format is a format effect until proven otherwise.

## The comparison, after any migration

Count these before declaring a migration done. The numbers are the point of
this document.

- **5** status fields, none dropped, `output_language_default` included.
- **11** profile sections, **plus the signature block**, present even when empty.
- **5** voice parts, and **every trait carries its quote**.
- **3** pillars, each with title, ratio, effect, description and material. The
  ratios sum to the cadence in Objective and cadence.
- **3** ideas parts, and Used keeps every line it had.
- **13** ledger fields per entry: **9** columns, **4** in the tail.
