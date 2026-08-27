# Verbatim

**The LinkedIn post skill that interviews you first.**

A Claude skill bundle that interviews you before it writes anything, then
drafts a LinkedIn post in your voice, checks it against a language specific
style pass, archives it, and publishes it.

The name is the mechanism: no angle is proposed unless it can be traced to a
verbatim quote of something you said in the interview that produced it.

**It cannot write anything you did not say.** Every fact in a generated post
traces back to your profile, to your published corpus, or to a sentence you
spoke in the interview that produced it. When nothing traces, nothing gets
written. That constraint is the product; the writing is a consequence of it.

MIT licensed. Self hosted or no host at all. No account, no subscription, no
service in the middle.

## Why an interview

Most tools of this kind assume the hard part is writing. It is not. The hard
part is getting a specific, true, defensible thing out of your head and onto a
page, and a text box does not do that. A template does not do it either: it
produces a well shaped post about nothing, because a template can be filled
without you having said anything.

So the interview comes first, one question at a time, and it refuses to advance
on an abstract answer. It asks for the instance again: which one, when, how
many, with whom. Between four and six turns, then it stops, because the test is
whether there is a scene, a position and a consequence, not whether a counter
reached six.

Then, before a single line is drafted, it hands you a validation sheet where
every bullet has to trace to something you said. You approve it or you correct
it. Nothing is written until you do.

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

```bash
git clone https://github.com/alexis-morain/verbatim-linkedin.git ~/verbatim-linkedin
ln -s ~/verbatim-linkedin ~/.claude/skills/verbatim
```

**The bundle installs as one unit.** The router at the root dispatches to the
skills inside it, and that is what lets every skill resolve `references/`,
`locales/` and `lib/` by the same relative path. Symlinking a single skill
directory on its own will break those paths.

Then say you want to set up your LinkedIn profile.
`linkedin-setup` runs about twenty minutes and ends on a written post, not on a
folder.

Read [`examples/`](examples/) first if you want to see the shape of a filled
profile before you fill your own. The persona in there is fictional and is
deliberately not in the maintainer's field.

## What ships

| Skill | Does |
|---|---|
| [`linkedin-setup`](skills/linkedin-setup/) | Builds your profile, your pillars, your voice file and your idea bank from a short interview, then hands over to the first post. |
| [`linkedin-post`](skills/linkedin-post/) | Interview, validation sheet, draft, style pass, revisions, archive, publish, measure at J+7. |

Two more are deliberately held back for a second version: a measurement skill
that reads the store across posts, and a profile skill for the nine sections of
a LinkedIn profile page. Setup plus post is a complete loop on its own, and two
skills that work beat four that half do.

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

## What this will not do

- **No hook formulas calibrated on a viral corpus.** They invert the mechanism.
  Here the angle descends from a sentence you said; there it descends from a
  shape that performed for somebody else.
- **No writing against an AI detector.** Optimising for a classifier is writing
  for the classifier.
- **No engagement pods, no comment gate by default.**
- **No invented facts, including inside a revision.** Revisions are where this
  usually breaks, so the traceability check runs again after every one.

## Where it comes from

Built out of a working setup, not out of a specification. The post it was
calibrated on is real and public: Alexis Morain, [the La Growth Machine
workflow](https://www.linkedin.com/feed/update/urn:li:share:7488195323551481856),
29 July 2026, 2,200 characters.

The scars in this bundle are from that setup. The validation sheet exists
because a draft once claimed client experience that did not exist. The
publishing guard exists because three test posts went to a company page. The
disclosure rule exists because an affiliate disclosure survived the draft and
not the published version.

## License

MIT. See [LICENSE](LICENSE).
