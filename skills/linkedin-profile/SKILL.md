---
name: linkedin-profile
description: "Audits and rewrites the nine sections of a person's public LinkedIn page from material they can prove, headline and About first. Triggers: optimize my LinkedIn profile page, rewrite my headline, my About section reads flat. Not for building the editorial profile file (use linkedin-setup), not for writing a post (use linkedin-post)."
version: 0.1.1
---

# The public page

> **Paths in this file are relative to the bundle root**, the directory holding
> the router `SKILL.md`, not to this skill's own directory. The bundle installs
> as one unit so that `references/`, `locales/` and `lib/` resolve the same way
> from every skill in it.

Every post this engine writes sends readers to one place: the person's public
LinkedIn page. A reader who liked a post lands there and decides in a few
seconds whether the author is somebody or noise. This skill makes the page
carry the same argument as the posts, under the same constraint: **it cannot
claim anything the person cannot prove.**

Two different things share the word "profile" and this skill touches only one
of them. The editorial profile is the Profile section of the material, which feeds
every skill; `linkedin-setup` owns it. The **public page** is what LinkedIn
shows the world; this skill owns that.

## Before anything

1. Read the material's `## Status` block. If `filled: no`, stop and offer
   `linkedin-setup`. A page rewritten without a source of proven facts is
   copywriting, and this bundle does not do copywriting.
2. Read its Profile, Pillars and Voice sections.
3. Read `locales/<interview_language>/style.md` and `interview.md`. Fall back
   to `locales/en` and say so.
4. Ask the person to paste their current page, section by section, or export
   it (LinkedIn offers a PDF of the full profile). **The engine never scrapes
   and never touches the platform.** The person pastes, the person applies.
5. If a page from a previous run was kept, read it and
   diff: what was adopted, what drifted since.

## The audit

Run the promise in reverse. Every claim currently on the page gets one of
three verdicts:

- **Traces**: backed by the material, by a pasted post, or by something the person says
  right now. Keep, maybe sharpen.
- **Provable but absent from the material**: true, but the material does not
  carry it. It goes into the material first, with its source. The page never
  holds facts the profile does not.
- **Traces to nothing**: the inherited superlative, the borrowed metric, the
  "passionate about" filler. Flag it, quoted, and propose removal. A page is
  the one place a stale exaggeration sits in public for years.

Announce the verdicts in one compact list before touching anything.

## The interview

Three intents, `references/interview-intents.md`, set C. Wording in
`locales/<interview_language>/interview.md`. One question at a time, and skip anything
the material already answers, which is most things. This interview is short
on purpose: the material is supposed to exist already.

## The nine sections

Worked in this order. The first three carry the argument; the rest follow
from them.

| # | Section | Its one job |
|---|---|---|
| 1 | Headline | Travels with the name into every feed, comment and search result. Who it serves plus one provable claim, in the buyer's words. Not a stack of job titles, not a string of pipes and keywords. |
| 2 | About | The three lines above the fold decide whether anyone expands. Open on the thesis, then the two or three facts the `proof-pick` intent selected, then who this is for, then the next step from the `reader-next-step` intent. First person, in the output language, in the voice the Voice section describes. |
| 3 | Featured | Two or three items, each one a proof, not a decoration. Built from the `proof-pick` selection; the best measured post in the ledger belongs here. |
| 4 | Experience | The current role written as outcomes with sourced numbers, consistent with "what I sell". Past roles compressed to what explains the present one. |
| 5 | Skills | The terms from the `buyer-words` intent, the ones clients actually type and say. A skills list is a search surface, not a trophy shelf. |
| 6 | Recommendations | Requested from the public, named references from the material only. "Names I must never cite" applies here exactly as it does in a post. Draft the ask in the output language if the person wants one. |
| 7 | Photo | A recent face, framed close enough to read in a feed avatar. Mechanism only; this skill has no opinion on style. |
| 8 | Banner | The one static surface for a stated promise or a number the person can prove. Text content is this skill's job; design is not. |
| 9 | Activity | Not written here at all. The page inherits it from the posting loop, and a strong page above a dead feed reads as abandoned. If cadence is the weak point, say so and route to `linkedin-post`. |

## Writing

Open the generation with an explicit output-language directive, one line,
before anything else. Note that headline and About may be in a different
language from the interview; the `output_language_default` axis applies to the
page too.

Then, per section worked:

1. **Headline: three proposals, three different leads.** Each anchored to a
   fact, with the fact named underneath. Not three phrasings of one idea.
2. **About: one draft**, structured as above. **Every factual sentence prints
   its source beside it**, in a list under the draft: the sentence, then the
   line of the material or of this conversation it came from, quoted. A
   sentence with nothing under it is one nobody can check, and it comes out
   of the draft rather than into the page.
   Run the deterministic pass on it, it is prose:

   ```bash
   python3 lib/lint.py --lang <lang> - < about.txt
   ```

3. **The rest as concrete edits**: current text, proposed text, one line of
   why. Small diffs get applied; rewrites get postponed.

**No keyword stuffing, anywhere.** A headline written for an algorithm reads
like one, and the reader it costs is worth more than the search impression it
buys. The `buyer-words` intent puts real search terms in naturally or they
stay out.

## Archive

Emit it the way every session in this bundle ends, as one block of the lines
that changed, for the person to paste and keep:

```
PAGE UPDATE
updated: 2026-09-09
Headline:  <the text as applied>
About:     <the text as applied>
```

Nothing is written here. A tier that holds files may store it, and the next
run starts by diffing against whatever the person brings back. One mechanism
across the three skills, so somebody who has closed one session already knows
how this one ends.

The person applies the changes on LinkedIn by hand. When they say it is done,
update `updated`. If they adopted a variant of a proposal, archive what they
actually applied, not what was proposed.

## Hard rules

- **No invented number, no borrowed client, no inherited superlative.** Every
  claim traces to the material or to this conversation, **and the trace is
  printed, not asserted**: name the source next to the claim so the person can
  check it. What traces only to this conversation goes back into the material
  with its source.
- **Names that are not public stay off the page.** Same list as everywhere
  else.
- **The page never contradicts the posts.** If the headline promises what the
  pillars never deliver, the fix is the headline, not a new pillar.
- **Do not fill a section on the person's behalf and move on.** Proposals,
  then their call. The page carries their name in a way a post does not: a
  post scrolls away, the page stays.
- **Style**: `locales/<lang>/style.md` applies to the About in full.
