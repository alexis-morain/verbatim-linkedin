#!/usr/bin/env python3
"""One real turn against one real endpoint, to prove the wire.

The test suite replays recorded streams. Those were written from the published
formats, so they prove the parser and nothing else: a green suite has never
been evidence that any endpoint answers this engine, and `CLAUDE.md` says so
out loud. This script is the evidence. It is manual, it costs a few cents of
somebody's own key, and the plan makes it blocking before v2.0.0.

It is deliberately not in `check.sh`. CI has no key, and a check that skips
itself into a green tick is the failure this whole file exists against.

    export ANTHROPIC_API_KEY=...
    uv run --project app python scripts/smoke.py

    VERBATIM_PROVIDER=openai VERBATIM_MODEL=qwen2.5:14b \\
    VERBATIM_BASE_URL=http://127.0.0.1:11434/v1 VERBATIM_API_KEY=none \\
    uv run --project app python scripts/smoke.py

Three probes, and each one answers a question the recorded streams cannot:

1. **Text streams back.** The endpoint speaks the format this engine parses,
   in the shape it parses it, today.
2. **A required tool fires.** `tool_choice` is the mechanism that replaces
   asking a model nicely, and local runtimes are known to ignore it. A miss
   here is not a failure of the endpoint, it is the degraded path the engine
   documents, and it is reported as DEGRADED rather than as a pass or a fail.
3. **Tokens come back.** The meter over somebody's bill is only as honest as
   what the provider reports. Silence here means the screen shows zero, and
   zero over a real bill is the answer `providers.py` refuses to give.

Nothing is written anywhere. No instance is read, no interview is created, and
the only thing that leaves the machine is one short prompt to the endpoint the
environment names.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app.agent import (  # noqa: E402
    Agent, AgentError, Tool, http_transport)
from verbatim_app.providers import (  # noqa: E402
    ProviderError, price, problems, resolve)
from verbatim_app.tools import redact  # noqa: E402

PASS, FAIL, DEGRADED = "PASS", "FAIL", "DEGRADED"

#: Short, cheap, and answerable without knowing anything. The point is the
#: wire, not the answer.
ASK = "Reply with the single word: ready."

PROBE_TOOL = "smoke_probe"


def probe_tool(seen: list) -> Tool:
    return Tool(
        name=PROBE_TOOL,
        description="Record one word. Called to prove a required tool fires.",
        input_schema={
            "type": "object",
            "properties": {"word": {"type": "string"}},
            "required": ["word"],
        },
        run=lambda arguments: seen.append(arguments.get("word", "")) or "noted")


def run(settings, transport, *, require: str = ""):
    """One turn, collected. Returns (text, tool calls, usage, stop)."""
    seen: list = []
    agent = Agent(settings, [probe_tool(seen)], transport=transport,
                  max_turns=2)
    text, calls, stop = "", [], ""
    messages = [{"role": "user", "content": [{"type": "text", "text": ASK}]}]
    for step in agent.run("", messages, require=require):
        if step.kind == "text":
            text += step.text
        elif step.kind == "tool_call":
            calls.append(step.call.name)
        elif step.kind == "stop":
            stop = step.stop or ""
    return text, calls, agent.usage, stop


def line(verdict: str, label: str, detail: str = "") -> str:
    return f"  {verdict:<9} {label}" + (f"  ({detail})" if detail else "")


def main(argv=None) -> int:
    return main_with(os.environ, http_transport)


def main_with(environ, make_transport) -> int:
    """The report, with the environment and the wire handed in.

    Split out so the plumbing can be exercised against a replayed transport.
    What that proves is that this script runs; what it cannot prove is the one
    thing the script exists for, which is why the real run stays manual.
    """
    # A throwaway directory rather than a real instance: this proves the
    # endpoint, and an instance `.env` would quietly change which one is being
    # proved. What is under test is the environment, and only that.
    with tempfile.TemporaryDirectory(prefix="verbatim-smoke-") as scratch:
        try:
            settings = resolve(Path(scratch), environ)
        except ProviderError as refusal:
            print(f"refused before any request: {refusal}", file=sys.stderr)
            return 2
    gaps = problems(settings)
    if gaps:
        print("nothing to smoke test: "
              + ", ".join(gap.code for gap in gaps), file=sys.stderr)
        return 2

    print(f"provider  {settings.provider}")
    print(f"model     {settings.model}")
    print(f"endpoint  {settings.base_url}")
    print()

    transport = make_transport()
    results = []

    try:
        text, _, usage, stop = run(settings, transport)
    except (AgentError, ProviderError) as failure:
        # Redacted the way the app redacts a provider failure: a gateway that
        # echoes an Authorization header into a debug body would otherwise put
        # the key in a terminal somebody pastes into an issue.
        print(line(FAIL, "text streams back",
                   redact(str(failure), environ)[:160]))
        print("\nthe endpoint did not answer at all, so the two other probes "
              "would only repeat this one.")
        return 1
    results.append((PASS if text.strip() else FAIL, "text streams back",
                    f"stop={stop or 'none'}, {len(text)} characters"))

    total = usage
    try:
        _, calls, tool_usage, _ = run(settings, transport, require=PROBE_TOOL)
        total = total + tool_usage
    except (AgentError, ProviderError) as failure:
        results.append((FAIL, "a required tool fires",
                        redact(str(failure), environ)[:160]))
    else:
        # A runtime that ignores the requirement is the documented degraded
        # path, not a broken endpoint: the engine falls back to reading the
        # ANCHORS block out of prose. Reported as its own verdict so nobody
        # reads a green line as "tool_choice works here".
        results.append(
            (PASS, "a required tool fires", ", ".join(calls)) if calls
            else (DEGRADED, "a required tool fires",
                  "answered without calling it; the engine falls back to "
                  "reading the anchors out of prose"))

    counted = total.input_tokens or total.output_tokens
    results.append((PASS if counted else FAIL, "tokens come back",
                    f"{total.input_tokens} in, {total.output_tokens} out"))

    cost = price(settings.model, total)
    for verdict, label, detail in results:
        print(line(verdict, label, detail))
    print()
    print("  cost      " + (f"{cost:.4f} USD" if cost is not None
                            else "no price for this model in this engine; "
                                 "the tokens above are the whole answer"))

    failed = [row for row in results if row[0] == FAIL]
    print()
    print("Paste into docs/smoke.md, with today's date and the bundle "
          "revision:")
    print(f"| <date> | {settings.provider} | {settings.model} | "
          f"{settings.base_url} | "
          + " ".join(verdict.lower() for verdict, _, _ in results)
          + " | <revision> |")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
