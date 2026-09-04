# Releases

One entry per published version, newest first. The dated working log is
[`journal.md`](journal.md), in French, and it is a different file: it records
sessions, not versions.

## 2.4.0, 4 September 2026

**The first version of Verbatim to be published.** This repository has been
public for a while and has never been on PyPI. Versions 2.0.0 through 2.3.0
exist in its git history and will never exist on the index: 2.4.0 is the
first release anybody can install, and the lowest number PyPI will ever show
for this project. Nothing is being upgraded here, and there is no migration
to read.

### What it is

A LinkedIn post writer that interviews you before it writes anything. The
name is the mechanism: no line of a draft is proposed unless it traces to a
verbatim quote of something you said, to your profile, or to your published
corpus. When nothing traces, nothing gets written. The constraint is the
product and the writing is a consequence of it.

It comes in two shapes over the same directory of files. As a skill bundle it
runs inside Claude Code or any agent that reads skills, and needs no Python
at all. As a local web app it drives the same skills and adds screens for the
parts that are decisions rather than conversation: the validation sheet you
approve, the traceability panel above it, the archive form, the publish plan,
and the measurement store across posts. It binds to 127.0.0.1, there is no
account and no service in the middle, and the profile stays on your disk.

Python 3.11 or later, and a model endpoint of your own: Anthropic, OpenAI, or
anything speaking the OpenAI chat format, a local Ollama or LM Studio
included. The README has the two ways to run it and `.env.example` documents
what to point it at.

### What this version carries

Every backing now says where it came from. A quote is searched in the one
source its provenance names, so a line of the validation sheet offered as
something you said comes back fabricated, and so does anything lifted from
your profile. The traceability panel words a sentence you spoke differently
from a sheet you approved, because an approval is consent rather than speech.

The interview asks in the order the format needs. A story climbs from the
scene to the friction, the number and the position; a stance enters by the
position it already arrives with. There is a second door on the first rung
for somebody reporting a case they witnessed rather than lived, which none of
the six rungs covered. Beside it, a count of how much material is on the
table: distinct figures and proper nouns, read from what you actually said
rather than from the number of turns taken. It undercounts on purpose and
there is no badge that says you are ready, because that is a judgement about
material and this is a number.

A revision can aim at one passage. The block between two blank lines carries
its own span, so the rest of the post is out of reach by construction rather
than by asking a model nicely. A post keeps its earlier drafts, the way back
unstacks them rather than piling a new version on top, and what moved is
marked in the margin.

The first line of a post is a choice, and turning down both proposals is one
of the answers rather than the absence of one. A drafting turn answers in the
panel where its request was typed, not in the interview thread, which is the
anchoring source and no place for the engine to appear to speak. The waiting
line says which phase is running, and a half typed instruction survives a
reload, a closed tab and a trip to another screen.

A refusal names the shapes an answer could take instead of asking an open
question, and a turn that produced nothing does not cost the request.

### What it ships without

The native Anthropic wire has never been run against a real endpoint. Its
request shape, stream parsing and error handling are covered by recorded
streams and by nothing else, which is a decision with a date on it rather
than an oversight. The OpenAI wire is proved, hosted and local.
[`docs/smoke.md`](smoke.md) keeps the evidence and states plainly what the
gap costs. Anybody with a key closes it in about a minute.

The English language pack has not been read by a native speaker. It is
marked as such in the pack itself.

A model with a small context window truncates the skill in silence and then
answers without its guardrails, which is the worst failure mode here because
it looks like an answer. The bundle runs to roughly 6400 tokens and Ollama
defaults to 4096: raise `OLLAMA_CONTEXT_LENGTH` before pointing it at a local
runtime.

The wheel is the only distribution. `uv build` with no flag builds a source
distribution first and fails there on purpose, because the project file sits
one level below the bundle it packages and reaches up for it. What that costs
is `pip install --no-binary`. The source distribution of this project is the
git repository, which is how the skill bundle gets installed anyway.

### Verified

1158 tests on the app, run twice, once on a bare interpreter to hold the
standard library only claim and once with the dependencies installed. 94 on
the screen scripts. The wheel is built and opened on every run of
`check.sh`, which fails if anything the engine reads at run time is missing
from it. MIT licensed.
