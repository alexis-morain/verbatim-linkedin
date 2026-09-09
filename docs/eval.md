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
| anchors are findable | At least one anchor, none under ten characters. |

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

| Date | Model | Window | Held | Note |
|---|---|---|---|---|
| 2026-09-09 | `qwen2.5:14b` | 4,096 (Ollama default) | **0 of 5** | The engine never reached the model. |
| 2026-09-09 | `qwen2.5:14b` | 24,576 | **not measured** | Stopped: it made the machine unusable. See below. |

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

## What this does not measure

**Whether the post is any good.** Every check here is structural. A transcript
can hold all five and still produce something nobody would publish, and the
engine's own answer to that is the validation sheet, which is a person.

**Anything about a model it has not been run against.** The table above is the
whole of what is known.
