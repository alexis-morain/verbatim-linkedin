---
name: verbatim
description: "Router for Verbatim, the LinkedIn post bundle. Interviews a person to extract real material, then writes, checks and publishes a post in their own voice. Triggers: write a LinkedIn post, I have an idea for a post, set up my LinkedIn profile, rework my LinkedIn page. Not for advertising campaigns (use an ads skill), not for outbound messaging (use an outreach tool)."
version: 0.2.0
---

# Verbatim

An engine and a profile. The engine ships in this repository. The profile is
one person's material and never leaves their machine.

**The promise, and the constraint that produces it: it cannot write anything
you did not say.** Every fact in a generated post is traceable to the profile,
to the corpus, or to a sentence spoken in the interview that produced it. When
nothing traces, nothing gets written.

## Route

| The person wants | Skill | Precondition |
|---|---|---|
| To write a post | `skills/linkedin-post` | A filled profile. Without one, it offers setup first. |
| To set up, or to redo their pillars | `skills/linkedin-setup` | None. This is the entry point. |
| To rework their public LinkedIn page | `skills/linkedin-profile` | A filled profile. The page only ever claims what the profile can prove. |

Read `references/` on demand, not up front. Each skill names the files it
needs.

## First thing, every time: the status flag

Find the profile directory, then read the `## Status` block at the top of its
`profile.md`:

```
## Status
- filled: no
- source: template
- updated: --
- interface_language: --
- output_language_default: --
```

**While `filled: no`, no skill pretends to know the person.** Fall back to
generic rules, say so in one line, and offer `linkedin-setup`. This three line
block is the whole seam between the engine and a profile.

The profile directory is whatever the person points at. `linkedin-setup`
creates it and writes its path into the conversation. There is no default path
in this repository, on purpose: a hard coded path is how an engine stops being
portable.

## The three language axes

Independent, and this is what multilingual projects usually get wrong.

| Axis | Who decides | Where it lives |
|---|---|---|
| Engine language | the maintainer, once, English | this repository |
| Interview language | the profile | `interface_language` |
| Output language | per post, defaults to the interview language | `output_language_default` |

The last two really are independent. Plenty of people want to be interviewed in
their own language and publish in English.

**Language leak is the failure mode to watch.** If a template in this engine
carries a label like `FIRST LINE`, a model will echo it in English inside a
French post. Two guards, both mandatory:

1. **No user-facing string lives in the engine.** Wording lives in
   `locales/<lang>/interview.md`. The engine holds intents, never sentences to
   say.
2. **Every generation opens with an explicit output-language directive.** State
   it, in one line, before writing anything.

If the pack has no wording for an intent, generate one and announce it:
degradation is visible, never silent.

## Language packs

`locales/en` and `locales/fr` ship. `locales/_template` is the contract, and
its README carries the acceptance criteria for a new one.

A pack is never a translation of another pack. The ten categories in
`references/style-taxonomy.md` are shared; the lists that fill them are not.

## Layout

```
SKILL.md                    this router
skills/linkedin-post/       interview, sheet, draft, check, publish, measure
skills/linkedin-setup/      onboarding, pillars, idea bank
skills/linkedin-profile/    the public page, nine sections, audit then rewrite
references/                 mechanism, shared across languages
locales/<lang>/             wording, style lists, market rules
lib/lint.py                 deterministic style pass, no model
lib/publish.py              the three publishing tiers
examples/                   a fictional persona, to read before running this
```

## What this bundle will not do

- **No hook formulas calibrated on a viral corpus.** They invert the mechanism:
  the angle would descend from a template instead of from something the person
  said. See `references/formats.md`.
- **No writing against an AI detector.** Optimising for a classifier is writing
  for the classifier. The deterministic pass in `lib/lint.py` is the whole of
  it.
- **No engagement pods, no comment gates by default.** See
  `references/platform.md`.
- **No invented facts, ever**, including in a revision. That is the promise.
