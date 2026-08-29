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

**A required tool that does not fire is `DEGRADED`, not `FAIL`.** Local
runtimes are known to ignore the requirement, and the engine has a documented
path for exactly that: it reads the `ANCHORS` block out of the prose instead,
and `references/instance.md` says the path is degraded and shows it on screen.
A `DEGRADED` row is a usable endpoint whose draft screen will carry a
`problems` list more often. It is not a bug to fix before release; it is the
reason the fallback was written.

## Results

Append a row per run. The revision is the bundle commit it ran against, so a
row that predates a change to `providers.py` reads as what it is: an old
measurement, not a current promise.

<!-- date | provider | model | endpoint | text tool tokens | revision -->

| Date | Provider | Model | Endpoint | text / tool / tokens | Revision |
|---|---|---|---|---|---|
| | | | | | |

**No row here yet.** The table is empty on purpose rather than absent: an
absent table reads as "nobody thought of it", an empty one reads as "nobody
has run it", and only the second one is true.
