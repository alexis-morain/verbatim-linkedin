---
name: linkedin-setup
description: "Onboards a person: builds their editorial profile, their pillars and their idea bank from a short interview, then hands over to the first post. Triggers: set up my LinkedIn profile, define my pillars, I want to start posting. Not for writing a post (use linkedin-post)."
version: 0.1.0
---

# Setup

> **Paths in this file are relative to the bundle root**, the directory holding
> the router `SKILL.md`, not to this skill's own directory. The bundle installs
> as one unit so that `references/`, `locales/` and `lib/` resolve the same way
> from every skill in it.

This is the entry point, and for anyone who did not write this engine it is the
actual product. Without it, a published bundle is a folder of prompts.

It takes about twenty minutes and it ends on a written post, not on a folder.

## What it produces

In a directory the person chooses, on their machine:

```
profile.md    who they are, who they write to, what they can prove, what they never say
voice.md      style and structures, drawn from their own published posts
pillars.md    three pillars, with a ratio
ideas.md      the angle bank, three per pillar to start
corpus/       their reference posts
posts/        empty for now
```

None of it is ever committed to this repository. `.gitignore` enforces that.
The full contract for these files, format by format, is
`references/instance.md`; what this skill produces has to conform to it.

## Step 0. Where it lives, and in what language

Ask where the profile goes, and create it there. **Do not assume a path.**
Write the chosen path back into the conversation so the other skills can find
it.

Then settle the three language axes from `SKILL.md`, in one exchange:

- **Interview language.** The one they want to be talked to in.
- **Output language.** Defaults to the same. Ask explicitly, because plenty of
  people work in one language and publish in another, and this is the single
  most common reason a bundle feels foreign.

If no pack exists for the interview language, say so plainly, fall back to
`locales/en`, and offer the pack template as a contribution. Do not machine
translate a pack on the fly and present it as one.

## Step 1. The basics, fast

Copy `references/profile.template.md` and fill the top of it with short
answers: what they sell, who they write to, what this channel is for. Two
minutes. These are facts, not reflection, and dwelling on them is how an
onboarding loses people before the part that matters.

Two fields deserve their own attention because nothing else in a profile
captures them and their absence produces tutorials:

- **What they can prove.** One bullet per fact, each with a source. A number
  without a source is a memory, not a fact. Push for the unflattering ones:
  they are the most publishable material anyone has.
- **Names that must never be cited.** Explicit list. Everything not on it and
  already public is free to use.

## Step 2. The interview

Ten intents, in `references/interview-intents.md`, set A. Wording in
`locales/<lang>/interview.md`.

**Every question announces what the answer becomes.** Not afterwards, in the
question itself. A person who knows they are feeding their public positions
answers differently from a person filling a field called "beliefs".

**Match the affordance to the question**, per the three shapes in the intents
file. This is the part that decides whether a stranger finishes.

| Question asks for | Give them |
|---|---|
| An opinion or a stance | Three propositions to pick from, built from what they already said, plus "or write your own" |
| A lived scene | Three memory prompts, as triggers and not as answers, above a free field |
| A thesis or a formulation | Three editable drafts to combine, edit, or overwrite |

Ticking a box costs three seconds and yields a usable sentence. "What is your
deepest conviction?" in an empty field costs ten minutes and usually yields a
platitude. **Constraint produces more than a blank page.**

Build the propositions from what this person has already said, never from a
template of what a good answer looks like. Otherwise they end up agreeing to
someone else's opinion, and every post afterwards is written on top of it.

## Step 3. The pillars

Three. Assembled from the interview, not chosen from a list.

**Write them as postures, not as subjects.** A subject says what a post is
about. A posture says what it does to the person reading. This is the
difference between a ratio that can be argued about and a ratio that is
arbitrary.

Each pillar carries:

- A definition, one or two sentences, specific to this person's market.
- **An effect label**: what the reader leaves with. Authority, trust, or
  connection.
- **A verifiability requirement**, if the person has one. A pillar built on
  numbers dies quietly if it is allowed to run on opinion.

Then the ratio, out of the monthly count from the `cadence` intent. Derive it
from the business objective and say the derivation out loud, so it can be
disagreed with:

| Objective | Leans on |
|---|---|
| Build authority | the market and stance pillar |
| Earn trust | the expertise and evidence pillar |
| Fill open slots | the personal and in-public pillar, with more `ACTION` |

Write `pillars.md` with the counter rule: at the start of every session, count
the pillars of the last N posts, and if one is more than two behind, offer it
first.

## Step 4. Voice

Ask for three published posts, up to six. Their own, not ones they admire.

Read them and write `voice.md`: the traits actually present, quoted. Form of
address, hook shape, paragraph rhythm, how they close, real length. Quote the
evidence for every trait. **A trait without a quote is a guess and does not go
in the file.**

If there are fewer than five posts, put a banner at the top of `voice.md`
saying the file is provisional and built on N posts, and instruct every skill
reading it to defer to the hard style rules instead of to the observed traits.
The banner comes off when the corpus is real, not when it feels awkward.

If there are no posts at all, say so, write `voice.md` with the hard rules
only, and note that it gets rewritten after five to ten published posts.

**Never build a voice from a scraped corpus of high performing posts.** It
produces the average of a niche, which is the opposite of a voice. Studying
five people they actually respect, by hand, for structures and never for turns
of phrase, is a different activity and is fine.

## Step 5. The idea bank

Nine ideas, three per pillar. Each one is an **angle**, which already contains
a position, not a subject.

Each carries:

- A title.
- **A funnel label**: `VISIBILITY`, `TRUST` or `ACTION`. See
  `references/formats.md`.
- Two lines of pitch.
- **The material that already exists for it**, named. An angle with no material
  behind it is a wish, and it will be the one that stalls a session.

**The dosage of the labels follows the business objective**, not taste. Someone
building authority runs heavy on `VISIBILITY`. Someone with open slots inverts
it. Say the dosage out loud when you write the bank.

Two ergonomic rules worth copying:

- **Regenerate one slot, not the whole grid.** Nobody should have to choose
  between keeping everything and throwing everything away.
- **Go straight from an idea into the interview.** No copying a title into
  another screen. The gap between having an idea and starting to write is where
  sessions die.

## Step 6. Publishing

Settle the tier now, while they are here, not at the end of the first post when
they are tired.

`copy` is the default and needs nothing. `postiz` needs an integration id, and
the id must be checked against the channel list first: a personal profile and a
company page are two lines in a config file and two very different things in a
feed. `command` runs their own binary. See `lib/publish.py`.

## Step 7. Do not end on a folder

**Hand straight over to `linkedin-post` and write one.** Right now, with an
idea from the bank that was just built.

A setup that ends on a finished profile has produced a folder. A setup that
ends on a published post has produced a habit. The difference between those two
outcomes is the difference between this working and not.

Then set the next session, with a date and an idea attached to it.

## Rules

- **Nothing in this skill writes into this repository.** The profile lives on
  the person's machine, at the path they chose.
- **Never fill a field on someone's behalf and move on.** Proposing three
  options is help. Picking one for them and continuing is authorship.
- **Do not translate a language pack on the fly.** Fall back, announce the
  fallback, and offer the template.
- **`filled: yes` only when the sections are real.** The flag is what every
  other skill trusts. Setting it early makes every downstream skill lie
  confidently.
