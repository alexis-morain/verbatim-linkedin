# Smoke tests, per provider

The suite replays recorded streams. They were written from the published
formats, so a green suite is evidence about the parser and about nothing else.
**It has never been evidence that any endpoint answers this engine.** This file
is where that evidence is kept, and the plan makes at least one green row per
supported wire blocking before v2.0.0.

## Running one

`scripts/smoke.py` sends two short requests to whatever the environment names,
prints a verdict per probe and a row to paste below. It reads no instance and
writes nothing anywhere: a throwaway directory stands in, so an instance `.env`
cannot quietly change which endpoint is being proved.

The native wire:

```bash
ANTHROPIC_API_KEY=... uv run --project app python scripts/smoke.py
```

Any endpoint speaking the OpenAI chat format, local inference included:

```bash
VERBATIM_PROVIDER=openai VERBATIM_MODEL=qwen2.5:14b VERBATIM_BASE_URL=http://127.0.0.1:11434/v1 VERBATIM_API_KEY=none uv run --project app python scripts/smoke.py
```

It costs a few cents of somebody's own key, which is why it is not in
`check.sh`: CI has no key, and a check that skips itself into a green tick is
the exact failure this file exists against.

## What the three probes mean

| Probe | What a pass says | What a failure says |
|---|---|---|
| text streams back | the endpoint speaks the format this engine parses, in the shape it parses it, today | the wire moved, or this endpoint never spoke it. Nothing else in the run will mean anything |
| a required tool fires | `tool_choice` works here, so the validation sheet and the draft happen through their tools | see below: this one has three outcomes, not two |
| tokens come back | the meter over somebody's bill is reporting something real | the screen will show zero over a real bill, which is the figure `providers.py` refuses to invent |

**A required tool has three outcomes, not two.**

- It fires: `PASS`.
- It is refused outright: `FAIL`. The model has no tool support at all and
  answers 400 to the whole request. This engine cannot drive it, since both
  the validation sheet and the draft happen through tools.
- It is ignored and the model answers in prose: `DEGRADED`. That is the path
  `references/instance.md` documents, where the engine reads the `ANCHORS`
  block out of the answer instead.

**And `DEGRADED` is not a stable property of an endpoint.** Measured on Ollama
on 2026-08-29: the same model, the same request, six times, called the tool
twice. `tool_choice` there is advisory, not enforced server side, so it is
left to the model each turn. One green run on a local runtime therefore
proves nothing about the next one, and a row here should say how many times
it was run when the answer was not the same every time.

The consequence is bigger than this table and is written down in the repo's
`CLAUDE.md`: the draft has a prose fallback and **the validation sheet does
not**. On a runtime that treats `tool_choice` as a suggestion, asking for the
sheet does nothing visible roughly two times in three.

## Results

Append a row per run. The revision is the bundle commit it ran against, so a
row that predates a change to `providers.py` reads as what it is: an old
measurement, not a current promise.

<!-- date | provider | model | endpoint | text tool tokens | revision -->

| Date | Provider | Model | Endpoint | text / tool / tokens | Revision |
|---|---|---|---|---|---|
| 2026-08-29 | openai | qwen2.5:14b | Ollama, 127.0.0.1:11434 | pass / degraded (2 of 6 runs) / pass | `c77ea20` |
| 2026-08-29 | openai | deepseek-r1:14b | Ollama, 127.0.0.1:11434 | pass / fail / pass | `c77ea20` |

**The `openai` wire is proved and the `anthropic` wire is not.** Both rows are
the same endpoint speaking the OpenAI chat format, which is what that wire had
to demonstrate. The native Anthropic wire has never been run against anything
and stays blocking for v2.0.0.

What the two rows say about the models rather than about the wire:
`deepseek-r1:14b` declares no tool support, so this engine cannot drive it at
all; `qwen2.5:14b` can be driven, and will take the degraded path most turns.
