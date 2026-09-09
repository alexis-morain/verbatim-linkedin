# Verbatim

**The LinkedIn post skill that interviews you first.**

One markdown file you attach to a conversation. It interviews you before it
writes anything, then drafts a LinkedIn post in your voice and checks it
against a language specific style pass. No install, no account, no service in
the middle, and nothing about you leaves the file you keep.

The name is the mechanism: no angle is proposed unless it can be traced to a
verbatim quote of something you said in the interview that produced it.

**It cannot write anything you did not say.** Every fact in a generated post
traces back to your profile, to your published corpus, or to a sentence you
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
back fabricated, and so does anything lifted from your profile.

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
| Write a post | [`linkedin-post.en.md`](https://raw.githubusercontent.com/alexis-morain/verbatim-linkedin/main/engines/linkedin-post.en.md) |
| Set yourself up, first time | [`linkedin-setup.en.md`](https://raw.githubusercontent.com/alexis-morain/verbatim-linkedin/main/engines/linkedin-setup.en.md) |
| Rework your public page | [`linkedin-profile.en.md`](https://raw.githubusercontent.com/alexis-morain/verbatim-linkedin/main/engines/linkedin-profile.en.md) |

French versions sit beside them in [`engines/`](engines/), one file per skill
and language. Each one carries its skill, the router, and every reference and
pack file it needs, because the weakest host this is written for cannot fetch
a second file.

**That host is the contract.** A conversation that receives an attachment and
returns text, writes no file and runs no code. Anything a better host adds is
convenience: it never adds a promise, and the engine says so where it matters.

Your material is a second file you attach, and it stays yours. The engine
prints the lines that changed at the end of a session and you paste them back.

## Engine and profile

Two things, kept apart on purpose.

**The engine** is this repository. It holds mechanism: the interview ladder,
the formats, the validation sheet, the measurement schema, the deterministic
style pass. It contains nothing about any particular person.

**The profile** is yours. Your positioning, your pillars, your provable facts,
the names you cannot cite, your signature. It lives in a directory you choose,
on your machine, and `.gitignore` here is written to make sure it never ends up
in this repository by accident.

The seam between them is three lines at the top of your profile:

```
## Status
- filled: no
- source: template
- updated: --
```

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
| [`linkedin-setup`](skills/linkedin-setup/) | Builds your profile, your pillars, your voice file and your idea bank from a short interview, then hands over to the first post. |
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
