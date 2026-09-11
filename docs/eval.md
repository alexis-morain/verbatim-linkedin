# Do the visible guards hold, and on what

`scripts/smoke.py` proves an endpoint speaks the wire. This proves something
else: that a model reading a generated engine actually does the things the
engine is written to make visible. Same shape as the smoke test, same
discipline, and the same reason it is not in `check.sh`.

```bash
python3 scripts/eval.py --self-test        # no key, no cost, in check.sh
python3 scripts/eval.py --provider ollama --model qwen2.5:14b --num-ctx 24576
ANTHROPIC_API_KEY=... python3 scripts/eval.py
```

## What it asserts, and why it can

Five things, each read off the transcript and nothing else. No assertion knows
which model produced it, what it was asked, or how it works inside.

| Check | Holds when |
|---|---|
| the sheet appeared | All five labels, in the order the skill prints them. |
| every bullet carries a quote | Each bullet under CONCRETE ELEMENTS has a quoted source under it. |
| the gauge listed facts | An Acquired block with facts in it, not a count. |
| two angles, each quoting | Two "because you said" lines, each with a findable quote. |
| anchors are long enough | At least one anchor, none under ten characters. Both shapes: quoted in the sheet, bare in the `ANCHORS` block. |
| the closing block appeared | A MATERIAL UPDATE block, with a ledger row of nine fields. |

This is possible because of ADR 0002 and nothing else. When those guards were
code, checking them meant running the code. Converting them into something a
person can see also made them greppable by a stranger.

**A failure is a measurement of that model, not a regression in the engine.**
The report refuses to print a verdict without naming what it ran against.

## The window comes first, and it fails silently

An engine carries everything it cites, which puts `linkedin-post` at about
18,000 tokens. **A host whose context is smaller does not refuse the file. It
truncates it, and says nothing.** Ollama truncates from the front, which is
exactly where the engine sits, so the model keeps the material and loses the
rules.

That is why `--num-ctx` exists. Without it, a run measures the truncation and
reports it as a model that cannot hold the guards.

## Results

| Date | Model | Reached the model by | Window | Held | Note |
|---|---|---|---|---|---|
| 2026-09-09 | `qwen2.5:14b` | Ollama, engine as system prompt | 4,096 (Ollama default) | **0 of 5** | The engine never reached the model. |
| 2026-09-09 | `qwen2.5:14b` | Ollama, engine as system prompt | 24,576 | **not measured** | Stopped: it made the machine unusable. See below. |
| 2026-09-11 | `claude-sonnet-5` | subscription session, engine read from disk as the attachment | ample | **6 of 6** | The whole loop, replayed by hand. [Transcript](transcripts/2026-09-11-claude-sonnet-5.txt). |

**The third column is not decoration.** The first two rows put the engine in a
system prompt over an API. The third handed it to a model the way a person
does, and that difference is most of what separates the two results. A row
without it reads like a claim about the model alone.

**2026-09-09, `qwen2.5:14b` at the default window.** All five failed, and the
transcript says why rather than leaving it to be guessed: the model had read
the material and counted the pillars off the ledger correctly, then opened
with "Great! Let's go through the process of selecting an idea" -- a fake hook
the `en` pack lists by name. It was not ignoring the rules. It never saw them.

This is the single most likely way somebody's first run goes wrong, it produces
no error, and the output looks like a working tool answering badly.

**The obvious fix has a cost nobody had priced.** Raising the window to 24,576
so the engine fits is what separates a model that fails the guards from one
that never saw them, and on an Apple laptop a 14B model at that window made
the machine unusable and the run was killed before it finished. So the honest
state of local inference against these engines is: the default window
guarantees failure, and the window that does not is expensive enough that
somebody has to decide to pay it.

That is worth knowing before recommending a local model to anybody, and it is
an argument for the engines getting smaller rather than for the window getting
bigger. A hosted model has neither problem and is what the README points at.

**2026-09-11, `claude-sonnet-5` in a subscription session.** All six held, over
the whole loop. The scripted interview was replayed turn by turn into a context
that had never seen this repository: the engine was the only instruction it was
given, `examples/material.md` the only material, and the scripted answers its
only new information. It read the ledger, found pillar 1 behind, asked for the
measurement the ledger was still owed before writing anything, listed its gauge
as facts rather than a count, offered two angles each resting on a quote,
printed the sheet with a source under every bullet, wrote the post, and handed
the session back in a MATERIAL UPDATE block.
[Transcript](transcripts/2026-09-11-claude-sonnet-5.txt).

**Three things were then checked that this script does not check.** All three
hold, and all three were run beside the eval rather than by it.

- **Provenance.** Fourteen quotes, twelve anchors and two angle lines, each
  searched in the one source its label names. Every one is in what the person
  said or on the sheet it came off, word for word.
- **The character count.** The draft announced 353 characters. It is 353.
- **Style.** The draft passes `lib/lint.py --lang en` with nothing flagged.

**The ledger row it printed was real.** The block reported row `2026-08-29`
updated from `draft` to `published`, and that row is in the material it was
given, as a draft. It also replaced that row's `chars: 1263` with 353, the
length of the post it had just written. It left the idea bank's matching entry
alone, correctly: that idea was already spent, and it added a new one instead,
which is the rule the engine states as never closing a session leaving the bank
poorer than it found it.

**This run is what found two holes, both now closed.** They were invisible for
the same reason: `ANSWERS` stopped at the sheet, two turns before the engine
does.

- `anchoring.md` fixes the `ANCHORS` block with no quotation marks anywhere,
  one line per entry. The anchor check read only quoted backings, so it
  answered "no anchor at all, so nothing was measured" on the very block the
  engine exists to print, while scoring the sheet's anchors as five of five. It
  reads both shapes now, and the fixture that proves it is the prescribed block
  with a two-character anchor in it. Its label said "findable" for a check that
  searches nothing, and now says what it does.
- Nothing measured the closing block, though the engine says in words that a
  session ending without it "has quietly lost everything it produced". That is
  the heaviest guard at the floor, and it was the one with no check. It has one
  now, and `ANSWERS` runs to the end of the loop so a live run can reach it.

**What this row still does not settle.** The engine reached that model as a
file read off a disk by a host with tools, which is a tier above the floor it
is written against: a file attached to a bare conversation that runs nothing.
The floor is still unmeasured, and it is the one most people will use. The
turns were also driven by hand rather than by `live()`, so the protocol is the
same and the transport is not.

## What this does not measure

**Whether the post is any good.** Every check here is structural. A transcript
can hold all five and still produce something nobody would publish, and the
engine's own answer to that is the validation sheet, which is a person.

**Anything about a model it has not been run against.** The table above is the
whole of what is known.

**Whether an anchor's quote is real.** The check is named
`anchors_are_long_enough`, and that is what it measures: an anchor exists, and
none is under ten characters. Searching each quote in the source its
provenance names is a second pass, run beside this script rather than by it,
and the 2026-09-11 row above says what that pass found.
