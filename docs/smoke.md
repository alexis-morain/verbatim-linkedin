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

That measurement is what put the sheet's prose fallback in the engine. Before
it, only the draft had one, so on a local runtime asking for the sheet did
nothing visible about two turns in three. Both halves read the shape their
skill prints, neither ever guesses a field it could not read, and when nothing
readable comes back the screen says so instead of leaving somebody wondering
what their click did. A `DEGRADED` row is therefore a usable endpoint, not a
half broken one.

## The one that does not announce itself

Running the app end to end against Ollama on 2026-08-29 turned up a failure
the three probes cannot see, because the probes send a short prompt and the app
sends the skill.

**A context window smaller than the system block truncates it, and the model
answers anyway.** Measured, same prompt, same model, `temperature: 0`:

| `num_ctx` | prompt tokens the runtime read | what came back |
|---|---|---|
| 4096 | 4096, exactly the window | a fluent, confident French answer |
| 16384 | 6629, the whole thing | a different, better placed answer |

The interview step's block is about 25 400 characters, roughly 6 400 tokens.
Ollama's default window is below that. Nothing in the reply says a third of the
skill was cut, and the skill is where every guardrail lives: the sheet rules,
the hard rules, the anchoring contract. A person reading fluent French has no
way to know their model never saw the part that says not to invent a number.

This is worse than an error, and it is the failure class this whole project
exists against, arriving through the back door.

Ollama says it in its own log at startup, which is where this was confirmed:

```
msg="vram-based default context" total_vram="17.8 GiB" default_num_ctx=4096
```

**The fix is server side**, because the OpenAI compatible endpoint has no
field for it:

```bash
OLLAMA_CONTEXT_LENGTH=16384 ollama serve
```

With that set, the same interview turn reported 6302 prompt tokens instead of
stopping dead on 4096.

The engine says the block's size on the interview screen and now says what a
smaller window does to it. It does not claim to detect it: knowing the true
token count of what was sent needs the provider's own tokeniser, and a verdict
computed from a characters per token guess would be exactly the invented
figure this codebase refuses everywhere else. **Open, and the biggest one
against the local first claim.**

## What running the whole app turned up about the models

Driving the real screens against Ollama, rather than the three probes, on
2026-08-29 with the window raised:

**`qwen2.5:14b` does not produce the sheet when it is asked for.** Not through
the tool, and not in prose either: asked for the validation sheet it replied
"if you already have this information, share it with me too", which is another
interview question. The engine refused to make a sheet out of that and said so
on screen. That is the right outcome, and it bounds what the prose fallback is
for: it reads a sheet a model wrote in the wrong place, and it cannot conjure
one a model never wrote.

So a `DEGRADED` row means the endpoint is usable, not that every step will
complete on it. On this model the interview runs; the sheet needs asking more
than once, or a stronger model.

## Results

Append a row per run. The revision is the bundle commit it ran against, so a
row that predates a change to `providers.py` reads as what it is: an old
measurement, not a current promise.

<!-- date | provider | model | endpoint | text tool tokens | revision -->

| Date | Provider | Model | Endpoint | text / tool / tokens | Revision |
|---|---|---|---|---|---|
| 2026-08-29 | openai | qwen2.5:14b | Ollama, 127.0.0.1:11434 | pass / degraded (2 of 6 runs) / pass | `c77ea20` |
| 2026-08-29 | openai | deepseek-r1:14b | Ollama, 127.0.0.1:11434 | pass / fail / pass | `c77ea20` |

## What the first release ships untested, and on purpose

**The `anthropic` wire has never been run against anything, and v2.0.0 ships
that way.** Decided by the maintainer on 2026-08-29: the first online version
is tested against local runtimes and against OpenAI, and no Anthropic key is
spent on it. That lifts a gate this file used to call blocking, so the gate is
not quietly dropped, it is written here with a date and a reason.

What that costs, stated so nobody has to work it out later:

- The native wire's request shape, its stream parsing and its error handling
  are covered by recorded streams and by nothing else. If Anthropic's format
  has moved, this engine finds out from whoever runs it first.
- `tool_choice` is enforced on that wire, which is the case with **no**
  measurement behind it. Every measurement here is of the advisory kind.
- The prices in `providers.py` are the ones nobody has seen a bill against.

Anyone with a key closes this in about a minute, and the row belongs in the
table below like any other.

**The `openai` wire is proved.** Both rows are the same endpoint speaking the
OpenAI chat format, which is what that wire had to demonstrate.

What the two rows say about the models rather than about the wire:
`deepseek-r1:14b` declares no tool support, so this engine cannot drive it at
all; `qwen2.5:14b` can be driven, and will take the degraded path most turns.
