# The instance contract

An instance is one directory, one person. Everything the engine knows about
somebody lives there, in plain markdown, on their machine. This file is the
contract: every file an instance holds, its format, and the rules a consumer
can rely on.

Today the consumers are the skills in this bundle. The contract exists so that
the next consumer, a script, a dashboard, a local UI, can read and write the
same files instead of growing its own database. **If a tool needs state this
contract does not carry, the contract is extended here first.** A side store is
how two versions of the truth start.

It is also what a migration is checked against. This project has already lived
the failure: an instance migrated by hand lost its signature block, silently,
because there was no list to diff against. This is the list.

## The directory

```
<chosen-path>/            wherever the person pointed linkedin-setup
  profile.md              who they are, what they can prove, what they never say
  voice.md                style traits, each one backed by a quote
  pillars.md              three pillars and their ratio
  ideas.md                the angle bank
  corpus/                 published posts, as reference material
  posts/                  one file per post produced here, with its measurement
  linkedin-page.md        the public LinkedIn page as applied, optional
  .env                    engine configuration for this instance, optional
```

File names are fixed and English: they are the machine seam, and the engine
finds its way by them. The prose inside is in whatever language the person is
interviewed in. Front matter keys and section headings stay English for the
same reason the file names do.

None of this is ever committed to the engine repository. `.gitignore` enforces
the names above, and `check.sh` refuses a tree where one slipped through.

## profile.md

Template: `references/profile.template.md`, which documents every section. The
parts a consumer relies on:

- **The `## Status` block, at the top of the file.** Five keys: `filled`,
  `source`, `updated`, `interface_language`, `output_language_default`. While
  `filled: no`, no consumer pretends to know the person. This block is the
  whole seam between engine and profile.
- **The `## Signature block` section.** Appended verbatim to every post, after
  a blank line, never shown to a model. An empty section means no signature.
  Its absence means the migration was incomplete, not that there is none.
- **The guardrail sections are load bearing**: out of scope segments, names
  never to cite, the "what I never say" list. Skills refuse material on their
  authority, so an instance without them is not conservative, it is unguarded.

## voice.md

Style traits observed in the person's own published posts, each trait followed
by the quote it was read from. A trait without a quote is a guess and does not
belong in the file.

Built on fewer than five posts, the file opens with a provisional banner and
every consumer defers to the hard rules in `locales/<lang>/style.md` when the
two disagree. The banner comes off after a rewrite on a real corpus, five to
ten posts, not before.

## pillars.md

Three pillars, written as postures. Each carries a definition, an effect label
(authority, trust, or connection), and optionally a verifiability requirement.
The ratio is stated against the monthly cadence and derived from the business
objective, out loud, so it can be argued with.

The pillar counter is not stored here. It is computed from `posts/` front
matter at read time, over `state: published` only.

## ideas.md

The angle bank. The contract points:

- **The first line under the title names the next session**: a date and an
  already-chosen idea. This is the line that decides whether there is a next
  post, and consumers surface it.
- One line per angle: pillar tag, funnel label (`VISIBILITY`, `TRUST`,
  `ACTION`), the angle stated as a position, and the material that already
  exists for it, named.
- A `## Used` section, append only: date, pillar, angle, file. An idea that
  became a post moves here instead of being deleted.

A session never closes leaving the bank poorer than it found it.

## corpus/

The posts the person had published before this engine existed, one file each,
raw text. Read as reference material for `voice.md` and as a source of
provable facts. Nothing here is generated and nothing here is rewritten.

## posts/

One file per post produced by the engine, named `YYYY-MM-DD-slug.md`. The
front matter block is specified in `references/measure.md` and is the
measurement store: `state` says whether the post is a draft, scheduled or
published, and every count anywhere in the system runs over `state: published`
only. The body is the post exactly as published, followed by session notes
that are not part of the post.

Aggregates, trends and counters are recomputed from these files at read time,
never written back. If a cache ever exists it is regenerated, and when it
disagrees with `posts/`, `posts/` is right.

## linkedin-page.md

Written by `linkedin-profile` and only by it: the person's public LinkedIn
page as actually applied, one heading per section, with an `updated` date in
front matter. Optional; an instance that has never run `linkedin-profile`
does not have it. It exists so the next run can diff against what is really
on the page instead of asking the person to paste everything again.

## Configuration

Two kinds, and the line between them is what a secret is.

**Publishing configuration is not in the instance.** `lib/publish.py` reads
environment variables only, documented by `.env.example` at the bundle root;
where a person keeps them, an exported shell profile or a `.env` loaded by
their own tooling, is machine specific and outside this contract.

**Engine configuration is, since it differs per instance.** A person can run
one instance against a hosted model and another against a model on their own
machine, so the choice belongs next to the material it works on. An instance
may carry a `.env` holding these keys, all optional:

| Key | What it says |
|---|---|
| `VERBATIM_PROVIDER` | `anthropic` for the native wire, `openai` for any endpoint speaking the OpenAI chat format, local inference included |
| `VERBATIM_MODEL` | the model id, exactly as the provider spells it |
| `VERBATIM_BASE_URL` | the endpoint, when it is not the provider's own |

**And it does not get to say where the key goes.** The reasoning that keeps
credentials out of an instance applies to the endpoint too, which is the
easier half to forget: a file that travels between machines cannot silently
retarget a credential it is forbidden from holding. An endpoint named in an
instance `.env` receives the key only when it is the provider's own or a
runtime on this machine. Anything else has to be named from the process
environment, either as `VERBATIM_BASE_URL` or by its host in
`VERBATIM_ENDPOINT_OK`, next to the key it is allowed to receive. Without a
key in the environment there is nothing to leak and nothing is refused.

**No credential is ever written in the instance.** An API key is read from the
process environment and from nowhere else, under `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, or `VERBATIM_API_KEY`, which wins over both. A consumer that
finds a key shaped name in an instance `.env` refuses to start and says which
line to move, comments included, since a credential commented out rather than
deleted is still in the file that gets committed: an instance is a directory people copy, sync and sometimes
commit, and it holds a person's material, never their secrets. The bundle's
`.env.example` documents both halves.

The process environment overrides the instance `.env`, key by key, so a one
off run can name another model without editing a file.

If a future consumer needs per instance state this contract does not carry,
it gains it here first.

## Conformance

What a consumer checks before trusting an instance, in order:

1. `profile.md` exists and its `## Status` block parses.
2. `filled: yes`, otherwise stop and offer `linkedin-setup`.
3. The signature block section exists, even if empty.
4. `voice.md`, `pillars.md`, `ideas.md` exist. A missing one is a migration
   gap to report, not to silently tolerate.
5. Front matter in `posts/` carries the keys `measure.md` specifies. Files
   that predate a key get it added empty, never guessed.
