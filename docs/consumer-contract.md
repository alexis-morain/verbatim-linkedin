# What a consumer can rely on

A maintainer document, not a shipped one. The format of the material is
[`references/material.md`](../references/material.md), which the engine is
generated from; this file holds what is left once the format moved out: the
rules a tool reading or writing somebody's material has to respect, and the
machinery the frozen app grew around it.

**The word `instance` is gone.** It named a directory, and the engine no longer
has one: the floor is a conversation that receives one attached file and
returns text. What used to be an instance is a `material` file plus a corpus
the person pastes. A tier may still keep those in a directory, and the frozen
app does, but that is a tier's business and not a promise the engine makes.

**If a tool needs state this contract does not carry, the contract is extended
here first.** A side store is how two versions of the truth start.

The word survives below, in the sections describing the frozen app, because
that app still ships a module called `instance.py` and calling it something
else here would misdescribe running code. Everywhere the engine speaks, the
word is `material`.

`locales/en/app.yml` and `locales/fr/app.yml` keep the word too, for the same
reason and one more: they are the screen strings of that app, they name a
directory it really reads, and they ship inside the wheel. Rewording them
would describe an application that does not exist. Every other shipped file
speaks of a `material`.

For the same reason, roughly twenty files under `app/` cite this document at
its old path, `references/instance.md`. They are frozen and were left alone:
editing them to fix a link would change an application nobody is developing,
and the clauses they cite are the ones kept below. This paragraph is the
forwarding address.

## What moved

| Was a section here | Is now |
|---|---|
| `profile.md`, `voice.md`, `pillars.md`, `ideas.md` | Four sections of the material, in `references/material.md` |
| `posts/` front matter | The ledger, one table in the material, per ADR 0001 |
| `corpus/` | Pasted into the conversation at setup, out of the material |
| The directory listing | Nothing. There is no directory at the floor. |

## posts/
The post body and the session notes below it, which the frozen app writes as
one file each and a tier may write any way it likes.

**The seam between the two is the line `Session notes, not published:`**, and
it is machine readable on purpose. What a consumer hands to a publishing tier
is the body cut at that marker, never the body whole: below it sit the
validation sheet, every anchor the engine claimed and the line behind each one,
said or approved, which is the rawest material there is. A post is allowed to
contain a line of dashes, so the marker is the seam and the horizontal rule
above it is decoration.

The measurement fields that used to live in this file's front matter are the
ledger now, specified in `references/material.md`, including the rule that
`state` and `published_ref` move on a person's statement and never on a return
code.

## interviews/

Machinery of the frozen app, kept here so freezing it did not delete its specification. The floor has no interview state: the conversation is the transcript.


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
| `draft` | the post the engine wrote and the anchors it offered for it, once there is one. Absent until then, like `sheet` |
| `revisions` | what the person asked for once a draft existed, one entry per request. Absent until the first one, like the two above |
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
key is where that rule lives on disk. It holds the five fields of the sheet exactly as the skill defines
them (`angle`, `elements`, `moment`, `conviction`, `first_lines`), a `state`
that is `proposed` or `approved`, the two timestamps (`proposed`, `approved`),
and `problems`, what could not be read in the way this sheet arrived. Four
rules:

- **Approving is the person's decision, made on their screen.** Nothing a
  model can reach writes `approved`: the engine's tool can only propose.
- **A `proposed` sheet is replaceable, an `approved` sheet is frozen.** If
  something on the sheet is wrong, the person says so and the next proposal
  replaces it; once approved, the sheet is what the draft answers to.
- **A sheet says which road it came down.** `problems` is empty when the
  sheet arrived through the tool and carries at least one entry when it was
  read out of an answer that ignored it, whether or not the reading was
  clean. The two are not the same object: what a model committed to through a
  tool call it cannot later be said not to have meant, and a sheet parsed out
  of free text is a reading somebody should check more slowly. That is a
  decision the person makes on their screen, so the screen shows it. Like the
  draft's field of the same name, nothing a model can reach ever writes it.
- **An approved sheet ends the questions, not the interview.** No further
  interview turn runs, but `state` stays `open`, because `closed` means the
  interview became a post and names the file. The sheet is not transcript
  either: it is the engine's restatement awaiting a decision, and the words
  it restates are already in the transcript.

**`draft` is the post, and the anchors it claims for itself.** It appears once
the engine has written one, which cannot happen before the sheet is approved:
that guard is the sheet's whole purpose and this key is where it is paid.
Six fields:

| Field | What it says |
|---|---|
| `body` | the post as it would be published, signature block excluded: that one is concatenated from `profile.md`, never generated |
| `anchors` | the pairs of `references/anchoring.md`: `post` for the claim, then the line backing it under the key that says where it lives, `said` for the interview sentence or `sheet` for a line of the approved sheet. One of the two per pair, in the order the engine offered them |
| `photos` | the two photo ideas the skill asks the writing step for, the staged portrait and the visual. Empty when they did not arrive |
| `tips` | the three tips the same step is asked for, each a `kind` (`strong`, `weak`, `lesson`) and a `text`. Empty when they did not arrive |
| `problems` | what was unreadable in the way this draft arrived, empty when it arrived structured |
| `written` | timestamp, local time, seconds |

`photos` and `tips` are not the post and are never concatenated into it: they
are what the session leaves behind, and archiving writes them under the post's
session notes. They are optional on the wire on purpose. The skill asks for
eight things and a small runtime returns some of them; refusing the whole
draft over a missing photo idea would trade the post for a note about a photo.
What is missing is shown as missing instead, which is the same bargain the
prose fallback below makes.

Three rules, and the first is the one the screen is built on:

- **No verdict is ever stored.** Anchored, unanchored, fabricated and dangling
  are computed from `body`, `anchors`, the transcript and the approved sheet
  every time somebody looks, each quote against the one source its key names.
  A stored verdict is a second source of truth that stops being true the
  moment any of those changes, and it would go stale in the direction that
  flatters the engine.
- **A new draft replaces the one before it.** Revisions are a free loop in the
  skill, and a draft is not a decision anybody signed: the sheet is. What the
  person keeps is kept by archiving it, which names a file under `posts/` and
  closes the interview.
- **A model can only offer a draft, exactly as it can only propose a sheet.**
  The engine's tool writes this key and nothing else does.

**`revisions` is what the person asked for after a draft existed, and it is
part of what they said.** The skill's revision loop is free and always
restarts from the interview material; this key is the record of what was
asked for. Each entry holds `text`, the request exactly as typed, and `asked`,
a timestamp. Three rules:

- **Only a person writes here.** No tool reaches it, exactly as no tool
  reaches `approved`. The engine putting a request in somebody's mouth and
  then quoting it back is the failure the whole anchoring apparatus exists
  for, and this key is on the side of the line that would make it possible.
- **It is append only.** A revision that has been answered is still something
  somebody asked for, and a record keeping only the last one cannot say why
  the third draft differs from the second.
- **It joins the `Said` side.** `transcript.md` renders each entry as a
  `## Said` section, in order, after the interview turns, and the anchoring
  source includes it. A correction typed here ("it was forty, not thirty") is
  material a redraft is allowed to quote, because the same person typed it on
  the same screen as every interview answer. The consequence is named rather
  than hidden: an approved sheet ends the questions, not the person's ability
  to speak. What it forbids is another interview turn, not another word.

A draft normally arrives through that tool, one field per column above. A
runtime that ignores a forced tool call answers in prose instead, and the
engine then reads the `ANCHORS` block out of the answer. That is not a
hypothetical: `tool_choice` is enforced by the provider on the native wire and
is advisory on an OpenAI compatible one, so a local runtime takes this path
several turns out of six, measured rather than assumed. **The sheet has the
same fallback**, reading the five labels the skill prints; neither one ever
guesses a field it could not read, because a field invented to complete a
sheet is the invention the sheet exists to catch, wearing the sheet's own
authority. When nothing readable comes back, nothing is written and the
screen says so rather than leaving somebody to wonder what their click did. That
path is degraded on purpose and shows it: `body` then holds everything the
model wrote before the block, hooks and notes included, so the panel marks
sentences the post itself would never contain. Whatever could not be read
lands in `problems` rather than in silence.

`transcript.md` is rendered from `conversation.json` on every write and never
parsed back. Its front matter carries `state` (`open` or `closed`), the
dates, both languages, the model and the token total. Its body is a run of
`## Asked` and `## Said` sections in the order they happened. They are not
strictly alternating: a turn where the engine speaks, reads a file and speaks
again leaves two `## Asked` in a row, because the reading is not transcript.

**The anchoring sources are the `Said` side and the approved sheet, and a
consumer reads both from `conversation.json`, never off the rendered file.**
A quote is checked against the one source its key names, what the person said
under `said` or what they approved under `sheet`, never against what the
engine asked or what a tool returned: a model allowed to quote its own
question can satisfy `references/anchoring.md` without the person ever having
said anything. Reading roles out of structure rather than off markdown
headings is what makes that hold, since text that looks like a heading is
still text. The sheet counts only once approved: a proposed one is signed by
nobody and backs nothing.

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

  Archiving is one step and writes three things, in this order: the post file
  under `posts/`, the interview closed on the name of that file, then the
  consumed idea moved into the `## Used` section of `ideas.md`. The order is
  the recovery story, and it runs shortest trap first. Closing an interview
  onto a file that is not there is the worst of the three, so the file goes
  down before the close. Leaving it open after the file exists is the second
  worst: a second attempt then collides with a name already taken and the
  person is stuck between two half states. The idea bank comes last for the
  opposite reason: failing to move a line there is bookkeeping somebody
  repairs by hand in ten seconds, so it is reported and it does not abort
  what has already landed. A post file name that is already taken stops the
  step before anything is written at all.

  The classification the front matter needs, the pillar, the format, the label
  and the slug, is the person's on their screen: none of it is derivable from
  the draft, and a value guessed here would be a guess counted in every ratio
  the system reports afterwards. `state` starts at `draft`, because publishing
  is a different step with a different tool, and the measurement fields start
  empty, because J+7 has not happened.
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

What a consumer checks before trusting a material file, in order:

1. The `## Status` block exists and parses.
2. `filled: yes`, otherwise stop and offer setup.
3. The signature block section exists, even if empty. Its absence means the
   migration was incomplete, not that there is no signature.
4. The Voice, Pillars and Ideas sections exist. A missing one is a migration
   gap to report, not to silently tolerate.
5. Ledger entries carry the nine parsed columns. An entry that predates a
   column gets it empty, never guessed.

`check.sh` counts the fields of the format itself, which is a different
question from whether one person's file is well formed.

