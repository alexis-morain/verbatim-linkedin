# Contributing

Two kinds of contribution are wanted, and they need very different things from
you.

**A language pack** needs a native speaker who actually publishes in the
language. No code. Start at
[`locales/_template/README.md`](locales/_template/README.md), which carries the
contract and the acceptance criteria.

**Engine work** needs you to hold one line in your head: the engine holds
mechanism, the profile and the language pack hold content.

## The rule everything else follows

**Anything specific to a person or to a language goes in the profile or in the
language pack. Never in the engine.**

Concretely, none of this belongs in this repository:

- A path on somebody's machine.
- An integration id, an account name, a client name.
- A signature, a set of pillars, a target audience.
- A sentence intended to be read by the end user.

The last one is the one people miss. **The engine stores the intent of a
question, the pack stores its wording.** If an English label lives in the
engine, a model will echo it inside a French post. If a pack has no wording for
an intent, the model generates one and says it did: degradation is visible,
never silent.

## Conventions

**English, engine wide.** File names, headings, `SKILL.md` bodies, code,
comments. This is the one irreversible decision in the project. Content in
`locales/<lang>/` is in that language, obviously.

**Every skill description carries a "Not for X (use Y)" sentence.** It is what
keeps a router from picking the wrong skill. `check.sh` enforces it.

**No em dash, no emoji, anywhere in shipped prose.** Yes, this is the
maintainer's own style rule applied to the repository. It is also dogfooding:
this bundle exists to catch machine cadence, and documentation written by a
model is where it shows up first. Test fixtures are exempt, for obvious
reasons.

**Standard library only, in `lib/`.** PyYAML is used when it is present and a
built-in reader takes over when it is not. Somebody cloning this should be able
to run the style pass without installing anything.

**Tests live next to the code**, `lib/test_*.py`, plain `unittest`. New
behaviour arrives with a test that failed before it.

## Before you push

```bash
./check.sh
```

It runs the tests, self tests every language pack, and refuses a tree where
somebody's profile, a `.env`, an em dash or an emoji made it into the shipped
files. All of those have happened to somebody.

## Adding a language pack, in short

1. `cp -r locales/_template locales/<code>`
2. Fill the four files. Write `lint.yml` against
   [`references/style-taxonomy.md`](references/style-taxonomy.md), **not** by
   translating another pack. Same word, different verdict in another language,
   is normal and expected.
3. Leave `native_reviewed: false` until somebody has actually gone over it, and
   put a real name in `reviewed_by` when they have. Skills announce an
   unreviewed pack to the user rather than hiding it.
4. `python3 lib/lint.py --lang <code> --self-test`
5. `./check.sh`

The self test checks the shape of your pack, never the taste of your lists.
Nobody is going to argue with you about whether a word is a cliche in your
language.

## What gets declined

- **Hook templates calibrated on high performing posts.** They invert the
  mechanism this bundle exists for. See
  [`references/formats.md`](references/formats.md).
- **AI detector evasion.** Optimising against a classifier is writing for the
  classifier.
- **A dependency on a hosted service** in the default path. The default has to
  work with no account anywhere.
- **A claim about platform behaviour without a source.**
  [`references/platform.md`](references/platform.md) has a status column, and
  `folklore` is a legitimate status. Inventing a mechanism is not.
