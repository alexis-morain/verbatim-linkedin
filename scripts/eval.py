#!/usr/bin/env python3
"""Do the visible guards hold, on a real model, on a real transcript.

    python3 scripts/eval.py --self-test              # no key, no cost
    ANTHROPIC_API_KEY=... python3 scripts/eval.py    # a few cents

The engine used to enforce three things in code: a gauge that counted facts,
anchors checked against the source each named, and a forced tool call that
made the sheet be a sheet. The floor runs none of it, so ADR 0002 converted
each one into something a person can see. This script is the payoff nobody
planned: **a guard made visible is a guard made greppable from outside.**

Every assertion below reads the transcript and nothing else. None of them
knows which model produced it, what it was asked, or how it works inside.

**A failure here is a measurement, not a regression.** It says this model did
not hold these guards. A small local model failing is information about that
model, which is why the report names what it ran against and refuses to print
a verdict without one.

Deliberately not in `check.sh`, for the reason `docs/smoke.md` gives about the
smoke test: CI has no key, and a check that skips itself into a green tick is
the failure the check exists against. `--self-test` is in `check.sh`, because
it proves the assertions themselves and costs nothing.

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The five labels the sheet prints, from the skill itself.
SHEET_LABELS = ("ANGLE", "CONCRETE ELEMENTS", "THE STRONG MOMENT",
                "CENTRAL CONVICTION", "FIRST LINE")

#: What a bullet's backing is allowed to name. The profile is not on this
#: list on purpose: it is input to a question, never evidence.
SOURCES = ("SAID:", "CORPUS:", "SHEET:")


# --------------------------------------------------------------------------
# The assertions. Pure functions over text, which is what makes them testable
# without a key and readable by somebody who distrusts this script.
# --------------------------------------------------------------------------

def sheet_appeared(transcript: str) -> tuple[bool, str]:
    """All five labels, in one block, in order."""
    missing = [l for l in SHEET_LABELS if l not in transcript]
    if missing:
        return False, "no sheet: missing %s" % ", ".join(missing)
    seen = [transcript.index(l) for l in SHEET_LABELS]
    if seen != sorted(seen):
        return False, "the sheet's labels are out of order"
    return True, "five labels, in order"


def bullets_carry_quotes(transcript: str) -> tuple[bool, str]:
    """Every bullet under CONCRETE ELEMENTS has a quoted source under it.

    The engine is told to print the source on the line below the bullet. A
    bullet with nothing under it is the invented one this whole design exists
    to surface, so it is the failure, not a formatting nit.
    """
    if "CONCRETE ELEMENTS" not in transcript:
        return False, "no CONCRETE ELEMENTS block to read"
    block = transcript.split("CONCRETE ELEMENTS", 1)[1]
    for label in SHEET_LABELS[2:]:
        block = block.split(label, 1)[0]
    bullets = [l for l in block.splitlines() if l.strip().startswith(("-", "*"))]
    if not bullets:
        return False, "CONCRETE ELEMENTS has no bullets"
    bare = []
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if not line.strip().startswith(("-", "*")):
            continue
        following = " ".join(lines[i + 1:i + 4])
        if not any(s in following for s in SOURCES) or '"' not in following:
            bare.append(line.strip()[:48])
    if bare:
        return False, "%d bullet(s) with no quoted source: %s" % (
            len(bare), " | ".join(bare))
    return True, "%d bullets, each with a quoted source" % len(bullets)


def gauge_listed_facts(transcript: str) -> tuple[bool, str]:
    """The gauge listed what it counted instead of announcing a number."""
    if "Acquired" not in transcript:
        return False, "the gauge never printed an Acquired block"
    block = transcript.split("Acquired", 1)[1].split("Missing", 1)[0]
    facts = [l for l in block.splitlines() if l.strip()]
    if not facts:
        return False, "Acquired was printed empty"
    # A bare count where a list belongs is the failure this converts away from.
    if len(facts) == 1 and re.fullmatch(r"\s*\d+\s*(facts?|elements?)?\s*",
                                        facts[0]):
        return False, "the gauge announced a number instead of listing: %r" % facts[0]
    return True, "%d fact(s) listed" % len(facts)


#: The shape references/formats.md fixes for an angle proposal. The line is
#: the traceability mechanism, not decoration, so it is what identifies an
#: angle. English on purpose: the shape lives in the engine, which is English,
#: while the quote inside it is in whatever language the interview ran in.
ANGLE_LINE = re.compile(r'[Bb]ecause you said:\s*"([^"\n]*)"')


def two_angles_each_quoting(transcript: str) -> tuple[bool, str]:
    """Two angles were offered, each resting on a quote.

    Counting quoted strings anywhere would pass on a transcript with no angles
    in it at all, which is what an earlier version of this did. An angle is
    identified by the line that makes it traceable.
    """
    quotes = [q.strip() for q in ANGLE_LINE.findall(transcript)]
    if len(quotes) < 2:
        return False, ("%d angle(s) resting on a quote, fewer than two"
                       % len(quotes))
    short = [q for q in quotes if len(q) < 10]
    if short:
        return False, "%d angle(s) resting on an unfindable quote: %s" % (
            len(short), ", ".join(repr(q) for q in short))
    return True, "%d angles, each resting on a quote" % len(quotes)


def anchors_are_long_enough(transcript: str) -> tuple[bool, str]:
    """No anchor under ten characters, which is the rule written in words.

    One letter is found in any text, so an anchor that cannot miss is an alarm
    that cannot ring. Code used to refuse these; here it is measured instead.
    """
    found = re.findall(r'(?:SAID|CORPUS|SHEET):\s*"([^"\n]*)"', transcript)
    if not found:
        # A check with no counterexample and no existence test scores an empty
        # transcript as holding. It held on "" until a review said so.
        return False, "no anchor at all, so nothing was measured"
    short = [q for q in found if len(q.strip()) < 10]
    if short:
        return False, "%d anchor(s) under ten characters: %s" % (
            len(short), ", ".join(repr(s) for s in short))
    return True, "%d anchors, every one ten characters or more" % len(found)


CHECKS = (
    ("the sheet appeared", sheet_appeared),
    ("every bullet carries a quote", bullets_carry_quotes),
    ("the gauge listed facts", gauge_listed_facts),
    ("two angles, each quoting", two_angles_each_quoting),
    ("anchors are findable", anchors_are_long_enough),
)


def report(transcript: str, model: str, stream=sys.stdout) -> int:
    """Run every check. Returns 0 when all held."""
    print("model: %s\n" % model, file=stream)
    failed = 0
    for label, check in CHECKS:
        held, detail = check(transcript)
        print("%s %-30s %s" % ("ok  " if held else "FAIL", label, detail),
              file=stream)
        failed += not held
    print(file=stream)
    if failed:
        print("%d of %d guards did not hold on %s. That is a measurement of "
              "this model,\nnot a regression in the engine."
              % (failed, len(CHECKS), model), file=stream)
    else:
        print("every guard held on %s." % model, file=stream)
    return 1 if failed else 0


# --------------------------------------------------------------------------
# Fixtures: what a holding transcript looks like, and what each failure looks
# like. The script has to fail on the second set or it is measuring nothing.
# --------------------------------------------------------------------------

GOOD = '''
Acquired
  31 percent error on net burn      "we were off by thirty one percent"
  the meeting ran 40 minutes        "the next meeting ran forty minutes"
Missing
  when this happened

THE COMMENTARY, NOT THE MODEL
The numbers were fine and the story around them was not.
Because you said: "we were off by thirty one percent on net burn, same model"
We would dig into: what changed between the two versions of the deck.

ELEVEN SLIDES DELETED
What a board pack looks like once you cut what nobody reads.
Because you said: "we deleted eleven slides and kept the cash chart"
We would dig into: how the next meeting actually ran.

ANGLE               Your model is not wrong, your commentary is
CONCRETE ELEMENTS
  - Forecast error went from 31 percent to 6 percent
    SAID: "we were off by thirty one percent on net burn, same model"
  - The rebuild took eleven hours
    CORPUS: "Eleven hours. That is the median time I spend"
THE STRONG MOMENT   the partner had stopped reading by slide four
CENTRAL CONVICTION  "the numbers were fine, the argument was not"
FIRST LINE          Thirty-one percent to six percent, on the same model.
'''

#: One broken transcript per check, keyed by the check it must break. The
#: keys are not decoration: self_test asserts that *this* check fails on
#: *this* fixture, not merely that something failed. Four fixtures for five
#: checks passed for a while, and the missing one was the check that turned
#: out to measure nothing.
BAD = {
    "the sheet appeared":
        GOOD.replace("CENTRAL CONVICTION", "SOMETHING ELSE"),
    "every bullet carries a quote":
        GOOD.replace('    CORPUS: "Eleven hours. That is the median time I spend"\n', ""),
    "the gauge listed facts":
        re.sub(r"Acquired\n(  .*\n)+", "Acquired\n  2 facts\n", GOOD),
    "two angles, each quoting":
        GOOD.replace("ELEVEN SLIDES DELETED", "").replace(
            'Because you said: "we deleted eleven slides and kept the cash chart"\n', ""),
    "anchors are findable":
        GOOD.replace('"we were off by thirty one percent on net burn, same model"', '"we"'),
}

#: The empty transcript. Every check has to fail on it: a check that passes
#: on nothing at all scores a model that produced nothing as holding.
EMPTY = ""


def self_test() -> int:
    """Every check holds on GOOD, each one fails on its own fixture, and none
    of them passes on an empty transcript."""
    problems = []
    for label, check in CHECKS:
        held, detail = check(GOOD)
        if not held:
            problems.append("%s failed on the good transcript: %s" % (label, detail))

    for label, check in CHECKS:
        if label not in BAD:
            problems.append("%s has no fixture, so nothing proves it can fail" % label)
            continue
        held, _ = check(BAD[label])
        if held:
            problems.append("%s passed on the transcript written to break it" % label)

    for label, check in CHECKS:
        held, _ = check(EMPTY)
        if held:
            problems.append("%s passed on an empty transcript, so it measures nothing"
                            % label)

    if problems:
        for problem in problems:
            print("  " + problem, file=sys.stderr)
        return 1
    print("self test: %d checks hold on a good transcript, each fails on its own\n"
          "broken one, and none of them passes on an empty transcript."
          % len(CHECKS))
    return 0


# --------------------------------------------------------------------------
# The run against a real endpoint
# --------------------------------------------------------------------------

#: What the fictional persona answers. Scripted so the transcript is
#: comparable between runs and between models: what varies is the engine's
#: behaviour, never the material it was given.
ANSWERS = [
    "I want to write about a board pack I rebuilt. The forecast error on net "
    "burn went from 31 percent to 6 percent, on the same model. Nobody "
    "rebuilt the model, we rewrote the commentary around it.",
    "It was a Series A, 22 people, in March. The partner had stopped reading "
    "by slide four of the old deck.",
    "We deleted eleven slides and kept the cash chart. The next meeting ran "
    "forty minutes instead of ninety.",
]


def ask_anthropic(model, key, system, messages, **_):
    """One Anthropic call. urllib rather than a dependency, like lib/."""
    body = json.dumps({"model": model, "max_tokens": 2000,
                       "system": system, "messages": messages}).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=300) as answer:
        payload = json.load(answer)
    return "".join(b.get("text", "") for b in payload.get("content", []))


def ask_ollama(model, key, system, messages, base_url="", num_ctx=0, **_):
    """One call to Ollama's own API, which is the only one taking `num_ctx`.

    The OpenAI compatible endpoint accepts no context option, and Ollama
    defaults to a window far under the size of a generated engine. It does not
    error on a system block that does not fit: it truncates, silently, which
    is the failure `CLAUDE.md` names and the reason this path exists at all.
    Passing the window explicitly is what separates "this model cannot hold
    the guards" from "this model never saw them".
    """
    options = {"num_ctx": num_ctx} if num_ctx else {}
    body = json.dumps({"model": model, "stream": False, "options": options,
                       "messages": [{"role": "system", "content": system}] + messages}).encode()
    req = urllib.request.Request(
        (base_url or "http://127.0.0.1:11434") + "/api/chat", data=body,
        headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as answer:
        payload = json.load(answer)
    return payload.get("message", {}).get("content", "")


def ask_openai(model, key, system, messages, base_url="", **_):
    """Any endpoint speaking the OpenAI chat format, hosted or local."""
    body = json.dumps({"model": model, "max_tokens": 2000,
                       "messages": [{"role": "system", "content": system}] + messages}).encode()
    req = urllib.request.Request(
        (base_url or "https://api.openai.com") + "/v1/chat/completions",
        data=body, headers={"content-type": "application/json",
                            "authorization": "Bearer " + (key or "none")})
    with urllib.request.urlopen(req, timeout=300) as answer:
        payload = json.load(answer)
    return payload["choices"][0]["message"]["content"]


TRANSPORTS = {"anthropic": ask_anthropic, "ollama": ask_ollama,
              "openai": ask_openai}


def live(engine: Path, model: str, key: str, transport, *,
         base_url: str = "", num_ctx: int = 0, keep: str = "") -> int:
    system = engine.read_text(encoding="utf-8")
    material = (ROOT / "examples" / "material.md").read_text(encoding="utf-8")
    words = len(system.split())
    print("engine: %s, about %d words, roughly %d tokens"
          % (engine.name, words, int(words * 1.3)), file=sys.stderr)
    if num_ctx:
        print("window: %d tokens, asked for explicitly" % num_ctx, file=sys.stderr)
    messages = [{"role": "user",
                 "content": "Here is my material.\n\n" + material +
                            "\n\nI want to write a post."}]
    transcript = []
    for answer in ANSWERS:
        said = transport(model, key, system, messages,
                         base_url=base_url, num_ctx=num_ctx)
        transcript.append(said)
        messages.append({"role": "assistant", "content": said})
        messages.append({"role": "user", "content": answer})
    said = transport(model, key, system, messages,
                     base_url=base_url, num_ctx=num_ctx)
    transcript.append(said)
    whole = "\n".join(transcript)
    if keep:
        Path(keep).write_text(whole, encoding="utf-8")
        print("transcript kept at %s" % keep, file=sys.stderr)
    return report(whole, model)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--self-test", action="store_true",
                    help="check the assertions against fixtures, no key needed")
    ap.add_argument("--engine", default="engines/linkedin-post.en.md")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--provider", default="anthropic", choices=sorted(TRANSPORTS))
    ap.add_argument("--base-url", default="", help="for openai and ollama")
    ap.add_argument("--num-ctx", type=int, default=0,
                    help="ollama only: the context window, in tokens. Ollama "
                         "truncates a system block that does not fit rather "
                         "than refusing it, so a run without this measures "
                         "the truncation and not the model.")
    ap.add_argument("--keep", default="", help="write the transcript here")
    ap.add_argument("--transcript", help="score a transcript already captured")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.transcript:
        return report(Path(args.transcript).read_text(encoding="utf-8"),
                      args.model)
    key = os.environ.get("VERBATIM_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY" if args.provider == "anthropic" else "OPENAI_API_KEY", "")
    if args.provider == "anthropic" and not key:
        print("ANTHROPIC_API_KEY is not set. --self-test needs no key, and "
              "--provider ollama needs none either.", file=sys.stderr)
        return 2
    return live(ROOT / args.engine, args.model, key, TRANSPORTS[args.provider],
                base_url=args.base_url, num_ctx=args.num_ctx, keep=args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
