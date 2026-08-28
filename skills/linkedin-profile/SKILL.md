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
of them. The editorial profile, `profile.md`, is the instance file that feeds
every skill; `linkedin-setup` owns it. The **public page** is what LinkedIn
shows the world; this skill owns that.

## Before anything

1. Read the profile's `## Status` block. If `filled: no`, stop and offer
   `linkedin-setup`. A page rewritten without a source of proven facts is
   copywriting, and this bundle does not do copywriting.
2. Read `profile.md`, `pillars.md`, `voice.md`.
3. Read `locales/<interface_language>/style.md` and `interview.md`. Fall back
   to `locales/en` and say so.
4. Ask the person to paste their current page, section by section, or export
   it (LinkedIn offers a PDF of the full profile). **The engine never scrapes
   and never touches the platform.** The person pastes, the person applies.
5. If the instance has a `linkedin-page.md` from a previous run, read it and
   diff: what was adopted, what drifted since.

## The audit

Run the promise in reverse. Every claim currently on the page gets one of
three verdicts:

- **Traces**: backed by `profile.md`, `corpus/`, or something the person says
  right now. Keep, maybe sharpen.
- **Provable but absent from the profile**: true, but `profile.md` does not
  carry it. Add it to `profile.md` first, with its source. The page never
  holds facts the profile does not.
- **Traces to nothing**: the inherited superlative, the borrowed metric, the
  "passionate about" filler. Flag it, quoted, and propose removal. A page is
  the one place a stale exaggeration sits in public for years.

Announce the verdicts in one compact list before touching anything.

## The interview

Three intents, `references/interview-intents.md`, set C. Wording in
`locales/<interface_language>/interview.md`. One question at a time, and skip anything
`profile.md` already answers, which is most things. This interview is short
on purpose: the material is supposed to exist already.

## The nine sections

Worked in this order. The first three carry the argument; the rest follow
from them.

| # | Section | Its one job |
|---|---|---|
| 1 | Headline | Travels with the name into every feed, comment and search result. Who it serves plus one provable claim, in the buyer's words. Not a stack of job titles, not a string of pipes and keywords. |
| 2 | About | The three lines above the fold decide whether anyone expands. Open on the thesis, then the two or three facts the `proof-pick` intent selected, then who this is for, then the next step from the `reader-next-step` intent. First person, in the output language, in the voice `voice.md` describes. |
| 3 | Featured | Two or three items, each one a proof, not a decoration. Built from the `proof-pick` selection; the best measured post from `corpus/` or `posts/` belongs here. |
| 4 | Experience | The current role written as outcomes with sourced numbers, consistent with "what I sell". Past roles compressed to what explains the present one. |
| 5 | Skills | The terms from the `buyer-words` intent, the ones clients actually type and say. A skills list is a search surface, not a trophy shelf. |
| 6 | Recommendations | Requested from the public, named references in `profile.md` only. "Names I must never cite" applies here exactly as it does in a post. Draft the ask in the output language if the person wants one. |
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
2. **About: one draft**, structured as above, every factual sentence traceable.
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

Write the adopted result to `linkedin-page.md` at the instance root: a front
matter block with `updated: YYYY-MM-DD`, then one heading per section holding
the text as applied. The instance contract in `references/instance.md`
documents the file. Next run starts by diffing against it.

The person applies the changes on LinkedIn by hand. When they say it is done,
update `updated`. If they adopted a variant of a proposal, archive what they
actually applied, not what was proposed.

## Hard rules

- **No invented number, no borrowed client, no inherited superlative.** Every
  claim traces to `profile.md` or to this conversation, and what traces only
  to this conversation gets written into `profile.md` with its source.
- **Names that are not public stay off the page.** Same list as everywhere
  else.
- **The page never contradicts the posts.** If the headline promises what the
  pillars never deliver, the fix is the headline, not a new pillar.
- **Do not fill a section on the person's behalf and move on.** Proposals,
  then their call. The page carries their name in a way a post does not: a
  post scrolls away, the page stays.
- **Style**: `locales/<lang>/style.md` applies to the About in full.
