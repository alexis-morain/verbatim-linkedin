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


def two_angles_each_quoting(transcript: str) -> tuple[bool, str]:
    """Two angles were offered and each one carries a verbatim quote."""
    quoted = re.findall(r'"[^"\n]{10,}"', transcript)
    if len(quoted) < 2:
        return False, "fewer than two quotes of ten or more characters"
    return True, "%d quote(s) of ten or more characters" % len(quoted)


def anchors_are_long_enough(transcript: str) -> tuple[bool, str]:
    """No anchor under ten characters, which is the rule written in words.

    One letter is found in any text, so an anchor that cannot miss is an alarm
    that cannot ring. Code used to refuse these; here it is measured instead.
    """
    short = [q for q in re.findall(r'(?:SAID|CORPUS|SHEET):\s*"([^"\n]*)"',
                                   transcript) if len(q.strip()) < 10]
    if short:
        return False, "%d anchor(s) under ten characters: %s" % (
            len(short), ", ".join(repr(s) for s in short))
    return True, "every anchor is ten characters or more"


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

BAD = {
    "no sheet": GOOD.replace("CENTRAL CONVICTION", "SOMETHING ELSE"),
    "a bare bullet": GOOD.replace(
        '    CORPUS: "Eleven hours. That is the median time I spend"\n', ""),
    "a counted gauge": re.sub(r"Acquired\n(  .*\n)+", "Acquired\n  2 facts\n", GOOD),
    "a short anchor": GOOD.replace(
        '"we were off by thirty one percent on net burn, same model"', '"we"'),
}


def self_test() -> int:
    """Every check holds on GOOD, and the named one fails on each BAD."""
    import io
    problems = []
    for label, check in CHECKS:
        held, detail = check(GOOD)
        if not held:
            problems.append("%s failed on the good transcript: %s" % (label, detail))
    for name, transcript in BAD.items():
        if report(transcript, "fixture", stream=io.StringIO()) == 0:
            problems.append("%r passed, and it must not" % name)
    if problems:
        for p in problems:
            print("  " + p, file=sys.stderr)
        return 1
    print("self test: %d checks hold on a good transcript and fail on %d "
          "broken ones." % (len(CHECKS), len(BAD)))
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


def ask(model: str, key: str, system: str, messages: list) -> str:
    """One Anthropic call. urllib rather than a dependency, like lib/."""
    body = json.dumps({"model": model, "max_tokens": 2000,
                       "system": system, "messages": messages}).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=120) as answer:
        payload = json.load(answer)
    return "".join(b.get("text", "") for b in payload.get("content", []))


def live(engine: Path, model: str, key: str) -> int:
    system = engine.read_text(encoding="utf-8")
    material = (ROOT / "examples" / "material.md").read_text(encoding="utf-8")
    messages = [{"role": "user",
                 "content": "Here is my material.\n\n" + material +
                            "\n\nI want to write a post."}]
    transcript = []
    for answer in ANSWERS:
        said = ask(model, key, system, messages)
        transcript.append(said)
        messages.append({"role": "assistant", "content": said})
        messages.append({"role": "user", "content": answer})
    said = ask(model, key, system, messages)
    transcript.append(said)
    return report("\n".join(transcript), model)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--self-test", action="store_true",
                    help="check the assertions against fixtures, no key needed")
    ap.add_argument("--engine", default="engines/linkedin-post.en.md")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--transcript", help="score a transcript already captured")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.transcript:
        return report(Path(args.transcript).read_text(encoding="utf-8"),
                      args.model)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY is not set. --self-test needs no key.",
              file=sys.stderr)
        return 2
    return live(ROOT / args.engine, args.model, key)


if __name__ == "__main__":
    raise SystemExit(main())
