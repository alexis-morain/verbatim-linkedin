# Verbatim

**The LinkedIn post skill that interviews you first.**

One markdown file you attach to a conversation. It interviews you before it
writes anything, then drafts a LinkedIn post in your voice and checks it
against a language specific style pass. No install, no account, no service in
the middle, and nothing about you leaves the file you keep.

The name is the mechanism: no angle is proposed unless it can be traced to a
verbatim quote of something you said in the interview that produced it.

**It cannot write anything you did not say.** Every fact in a generated post
traces back to your material, to your published corpus, or to a sentence you
spoke in the interview that produced it. When nothing traces, nothing gets
written. That constraint is the product; the writing is a consequence of it.

MIT licensed. Self hosted or no host at all. No account, no subscription, no
service in the middle.

![The draft, and every claim of it checked against the interview](docs/screenshots/traceability.png)

*Every claim of a draft against what backs it, and where that backing lives:
a sentence you said, or a line of the sheet you approved. Highlighted means no
quote backs it, which is honest and is yours to check; red means the engine
named a source that does not hold the quote. The example material in
[`examples/`](examples/) is a fictional persona; nothing here is anybody's real
material.*

A backing also says where it lives: a sentence you said, or a line of the
validation sheet you approved. The panel words the two differently, because
an approval is consent rather than speech, and a quote is checked against the
one source it names: a line of the sheet offered as something you said comes
back fabricated, and so does anything lifted from your material.

## Why an interview

Most tools of this kind assume the hard part is writing. It is not. The hard
part is getting a specific, true, defensible thing out of your head and onto a
page, and a text box does not do that. A template does not do it either: it
produces a well shaped post about nothing, because a template can be filled
without you having said anything.

So the interview comes first, one question at a time, and it refuses to advance
on an abstract answer. It asks for the instance again: which one, when, how
many, with whom. Six turns at the outside, fewer when the format asks for
fewer: a stance stops earlier than a story. Then it stops, because the test is
whether there is a scene, a position and a consequence, not whether a counter
reached its number.

Then, before a single line is drafted, it hands you a validation sheet where
every bullet has to trace to something you said. You approve it or you correct
it. Nothing is written until you do.

## How to run it

Download one file and attach it to a conversation. That is the whole
installation.

| You want to | Attach |
|---|---|
| Write a post | [`linkedin-post.en.md`](https://github.com/alexis-morain/verbatim-linkedin/releases/download/engines-v1.0.0/linkedin-post.en.md) |
| Set yourself up, first time | [`linkedin-setup.en.md`](https://github.com/alexis-morain/verbatim-linkedin/releases/download/engines-v1.0.0/linkedin-setup.en.md) |
| Rework your public page | [`linkedin-profile.en.md`](https://github.com/alexis-morain/verbatim-linkedin/releases/download/engines-v1.0.0/linkedin-profile.en.md) |

Those are **1.0.0**, and the number is deliberate: an engine is a file you
keep, and a file you keep has to be sayable. The newest one is always on the
[releases page](https://github.com/alexis-morain/verbatim-linkedin/releases), French versions beside the
English, one file per skill and language. [`engines/`](engines/) in this
repository is the same six files at whatever `main` currently says: the right
thing to read when you are working on the engine, and the wrong thing to attach
when you are using it.

Each one carries its skill, the router, and every reference and pack file it
needs, because the weakest host this is written for cannot fetch
a second file. `scripts/build-engines.py` holds that by reading the finished
engine and refusing any path it names but does not carry, which is a stronger
question than whether a manifest was filled in.

**That host is the contract.** A conversation that receives an attachment and
returns text, writes no file and runs no code. Anything a better host adds is
convenience: it never adds a promise, and the engine says so where it matters.

**Check the window before you use a small model.** These files run from about
9,000 to 18,000 tokens, and each one states its own size near the top. A
host whose context is smaller does not refuse the file, it truncates it and
says nothing, so the model answers without ever having seen the rules it is
being judged on. Local runtimes are where this bites: Ollama defaults to
4,096 tokens and needs `OLLAMA_CONTEXT_LENGTH` raised.

Your material is a second file you attach, and it stays yours. The engine
prints the lines that changed at the end of a session and you paste them back.

## Engine and material

Two things, kept apart on purpose.

**The engine** is this repository. It holds mechanism: the interview ladder,
the formats, the validation sheet, the measurement schema, the deterministic
style pass. It contains nothing about any particular person.

**The material** is yours. Your positioning, your pillars, your provable
facts, the names you cannot cite, your signature. It is one file you keep and
attach, and `.gitignore` here is written to make sure it never ends up in this
repository by accident.

The seam between them is the Status block at the top of it:

```
## Status
- filled: no
- source: template
- updated: --
- interview_language: --
- output_language_default: --
```

The last two are independent on purpose: plenty of people want to be
interviewed in one language and publish in another.

While `filled: no`, every skill falls back to generic rules, says so, and
offers to set you up. No skill pretends to know you.

## Getting started

Attach `linkedin-setup.en.md` and say you want to set up your LinkedIn
profile. It runs about twenty minutes and ends on a written post, not on a
file.

Read [`examples/material.md`](examples/material.md) first if you want to see
the shape of a filled one before you fill your own. The persona in there is
fictional and is deliberately not in the maintainer's field.

**Working on the engine rather than using it?** Clone it, and read
[`CONTRIBUTING.md`](CONTRIBUTING.md). The skills live in `skills/`, the
engines in `engines/` are generated from them by
`scripts/build-engines.py`, and `check.sh` holds the rules.

## What ships

| Skill | Does |
|---|---|
| [`linkedin-setup`](skills/linkedin-setup/) | Builds your material, one file, from a short interview: who you write to, your pillars, your voice, your idea bank. Then hands over to the first post. |
| [`linkedin-post`](skills/linkedin-post/) | Interview, validation sheet, draft, style pass, revisions, archive, publish, measure at J+7. |
| [`linkedin-profile`](skills/linkedin-profile/) | Audits and rewrites the nine sections of your public LinkedIn page, headline and About first, from material you can prove. |


One more is deliberately held back: a measurement skill that advises across
posts. It waits for real measured posts to be built against, because advice
written from imagined data measures the imagination. Nothing concludes under
two measured posts.

**There was also a local Python app**, `verbatim-linkedin`, which drove the
same skills from screens over a directory. It is frozen at
[v2.4.1](https://github.com/alexis-morain/verbatim-linkedin/releases) and out
of the way under [`app/`](app/): plugging an API key in was the step that lost
people, and everyone already has a conversation to paste a file into.

## Languages

Three axes, and they are independent:

- The **engine** is in English. Once, by the maintainer.
- The **interview** happens in your language.
- The **output** is per post, defaulting to the interview language.

The last two really are separate. Plenty of people want to be interviewed in
their own language and publish in English.

`en` and `fr` ship today. A language pack is four files, and it is **never a
translation of another pack**: the ten categories in
[`references/style-taxonomy.md`](references/style-taxonomy.md) are shared, the
word lists that fill them are not. `scalable` is a marketing tell in French and
an ordinary word in English. "Force est de constater" has no English twin.
Negative parallelism is the dominant English tell of 2026 and merely common in
French.

The contract and the acceptance criteria are in
[`locales/_template/README.md`](locales/_template/README.md). You do not have
to be a maintainer to propose a pack; you have to be a native speaker who
publishes in the language.

## The style pass

`lib/lint.py` is deterministic. No model, no network, no AI detector.

```bash
python3 lib/lint.py --lang fr - < draft.txt
```

It reports and the human decides. Only the rules a pack marks hard block a
draft, and that set is deliberately tiny. A flagged word that you actually said,
inside a quote, stays in.

It runs on the standard library alone. PyYAML is used when it is installed and
a small built-in reader takes over when it is not.

## Checking a session

The engine's guards are visible on purpose: the sheet prints its quote beside
every bullet, the gauge lists the facts it counted instead of announcing a
number, and every anchor names the one source it can be found in. A guard you
can see is a guard you can check, and you do not need this repository's
maintainer or an API key to do it.

```bash
python3 scripts/eval.py --transcript my-session.txt --model "the one you used"
```

Paste your session into a file and run that. It reads plain text and nothing
else: it does not know which model produced the transcript, what it was asked,
or how it works inside. Five checks come back, each one with its reason.

| Check | Holds when |
|---|---|
| the sheet appeared | All five labels, in the order the skill prints them. |
| every bullet carries a quote | Each bullet under CONCRETE ELEMENTS has a quoted source under it. |
| the gauge listed facts | An Acquired block with facts in it, not a count. |
| two angles, each quoting | Two "because you said" lines, each with a findable quote. |
| anchors are findable | At least one anchor, none under ten characters. |

**A failure is a measurement of that model, not a bug in the engine**, which is
why `--model` is worth filling in honestly: the verdict names what it ran
against and refuses to print without one. The most likely cause of a bad run is
the window above, not the model. Every check here is structural, and none of
them says whether the post is any good; the engine's answer to that is the
validation sheet, which is a person.

## Publishing

Three tiers. The default needs no configuration.

| `LINKEDIN_PUBLISH` | Does |
|---|---|
| `copy` (default) | Prints the post, ready to paste. Nothing leaves your machine. |
| `postiz` | Self hosted [Postiz](https://postiz.com). Needs `POSTIZ_INTEGRATION_ID`. |
| `command` | Runs your own binary, post on stdin. `LINKEDIN_PUBLISH_CMD`. |

Anything that leaves the machine needs `--confirm`, and without it the script
prints the target channel and stops. That guard exists because the maintainer
has already published to the wrong channel: a personal profile and a company
page are two lines in a config file and two very different things in a feed.

![The publish plan: tier, target channel by name, when, length, first line](docs/screenshots/publish-plan.png)

*The plan, as the frozen app drew it. `lib/publish.py --plan` prints the same
thing at a terminal, and at the floor there is nothing to send: you post it
yourself.*

A post carrying a link gets one more line, asking whether it needs a
disclosure. Nothing here decides that for you, because nothing here can know
whether there is a material connection behind a link. What is mechanical is
that a post with no link never raises the question. The wording that satisfies
your market is in `locales/<lang>/market.md`, and the reason this exists at all
is that a disclosure once survived a draft here and not the published version.

**Publishing does not set the state of a post.** A tier accepting something is
not the same fact as a post being live: the copy tier prints a post nobody has
pasted yet, and a scheduling payload still has to be sent by whatever holds the
account. `state` and `published_ref` are yours to write, exactly like the
pillar and the format, which the engine asks for rather than guesses.

## What this will not do

- **No hook formulas calibrated on a viral corpus.** They invert the mechanism.
  Here the angle descends from a sentence you said; there it descends from a
  shape that performed for somebody else.
- **No writing against an AI detector.** Optimising for a classifier is writing
  for the classifier.
- **No engagement pods, no comment gate by default.**
- **No invented facts, including inside a revision.** Revisions are where this
  usually breaks, so the traceability check runs again after every one.

## License

MIT. See [LICENSE](LICENSE).
