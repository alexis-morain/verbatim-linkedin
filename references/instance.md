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
  interviews/             conversations in progress, one directory each, optional
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

## interviews/

One directory per interview in progress, named `YYYY-MM-DD-HHMM`, suffixed
`-2`, `-3` when two start in the same minute. This is the one piece of
instance state that is machinery before it is material: a conversation with a
model, kept on disk so that closing the browser, or restarting the process,
loses nothing somebody said.

```
interviews/2026-08-28-1432/
  conversation.json     the resume state, and the truth
  transcript.md         what a human reads, rendered from it on every write
```

`conversation.json` is the only file in an instance that is not markdown, for
one reason: a tool call carries an id the next request has to echo back, and a
format that cannot round trip that id produces a conversation the provider
rejects. Its keys:

| Key | What it says |
|---|---|
| `version` | the format's own number. A reader that does not know it refuses the file rather than guessing, so this is the first key a writer gets right |
| `id` | the directory's name, repeated so a moved file still says what it is |
| `state` | `open` or `closed`, the same value the transcript's front matter carries |
| `post` | the post file it became, empty while open |
| `skill` and `sections` | which step of which skill the system block is assembled from, so the block is rebuilt from the bundle rather than stored |
| `interface_language`, `output_language` | the two language axes, kept per interview: changing the profile does not change the language of a conversation already under way |
| `provider`, `model` | what answered on the last turn |
| `started`, `updated` | timestamps, local time, seconds |
| `usage` | the running token total, input and output |
| `spent` | dollars, accumulated turn by turn at the rate of the model that ran that turn. `null` once any turn had no price, and empty in the transcript front matter: a total that silently drops a turn is worse than no total, and applying today's rate to yesterday's turns is worse still |
| `sheet` | the validation sheet, once the engine has proposed one. Absent until then, so an older reader sees a file it already knows |
| `messages` | the provider shaped message list, as it goes on the wire |

It is rewritten after every step that changes the conversation, so what is on
disk is a conversation a provider would accept at any moment, including the
moment somebody walked away mid turn. Two consequences of that promise are
worth naming, because both are shapes a naive writer produces:

- **Two messages of the same role never follow each other.** An answer typed
  after a turn that failed joins the turn that got no answer rather than
  starting a second one, so a person retyping does not produce a conversation
  their provider refuses.
- **The block decides who spoke, not the message.** On a user role message a
  `tool_result` block is a tool answering and a `text` block is the person.
  They travel together whenever somebody answers after an interrupted tool
  call, and only the `text` blocks are ever credited as what was said.

**`sheet` is the validation sheet of `linkedin-post`, and its `state` is the
guard.** The skill says nothing is written until the sheet is approved; this
key is where that rule lives on disk. It holds the five fields of the sheet
exactly as the skill defines them (`angle`, `elements`, `moment`,
`conviction`, `first_lines`), a `state` that is `proposed` or `approved`, and
the two timestamps (`proposed`, `approved`). Three rules:

- **Approving is the person's decision, made on their screen.** Nothing a
  model can reach writes `approved`: the engine's tool can only propose.
- **A `proposed` sheet is replaceable, an `approved` sheet is frozen.** If
  something on the sheet is wrong, the person says so and the next proposal
  replaces it; once approved, the sheet is what the draft answers to.
- **An approved sheet ends the questions, not the interview.** No further
  interview turn runs, but `state` stays `open`, because `closed` means the
  interview became a post and names the file. The sheet is not transcript
  either: it is the engine's restatement awaiting a decision, and the words
  it restates are already in the transcript.

`transcript.md` is rendered from `conversation.json` on every write and never
parsed back. Its front matter carries `state` (`open` or `closed`), the
dates, both languages, the model and the token total. Its body is a run of
`## Asked` and `## Said` sections in the order they happened. They are not
strictly alternating: a turn where the engine speaks, reads a file and speaks
again leaves two `## Asked` in a row, because the reading is not transcript.

**The anchoring source is the `Said` side, and a consumer reads it from
`conversation.json`, never off the rendered file.** A quote is checked
against what the person said, never against what the engine asked or what a
tool returned: a model allowed to quote its own question can satisfy
`references/anchoring.md` without the person ever having said anything.
Reading roles out of structure rather than off markdown headings is what
makes that hold, since text that looks like a heading is still text.

Tool calls and their results stay in `conversation.json`. They are on screen
while the interview runs, and they are not transcript: a tool result is a
file the engine read, not a thing the person said.

Nothing aggregates over this directory. Counters, ratios and the pillar
balance run over `posts/` with `state: published`, exactly as before.

An interview ends one of three ways:

- **It becomes a post.** Front matter turns to `state: closed` and names the
  post file. The engine does not delete the directory: those are the
  person's own words, and the session notes in the post file are a summary
  of them, not a replacement.
- **It is discarded.** The person says so, and the directory goes, whole.
- **It is left.** Nothing happens, which is the point. The directory stays
  `state: open`, and the next consumer offers to resume or to discard it. No
  timeout collects an interview: an unfinished conversation is not garbage.

The directory is optional, and an instance driven from a terminal never grows
one. Its absence is not a conformance gap. What it must not be is anything
other than a directory: not a file, and above all not a symbolic link, at any
level. An id addresses a directory inside the instance, and following a link
out of one is how a discard leaves the instance.

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
