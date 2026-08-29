"""The validation sheet, read out of an answer that ignored its tool.

The sibling of `anchors.split_output`, which does the same job for the draft,
and it exists for a measured reason rather than a defensive one. `tool_choice`
is enforced by the provider on the native wire and advisory on an OpenAI
compatible one: two calls out of six on Ollama, `docs/smoke.md`. Without this,
asking for the sheet on a local runtime produces a sheet written out in the
thread, no panel, no approve button, and nothing to do but ask again, most
turns. The guard the whole skill is built on would fire on hosted models and
quietly not on local ones.

Two things this file will not do, and they are the same two `anchors.py`
refuses.

**It does not guess a missing field.** A sheet whose conviction was inferred
from the angle is exactly the invention the sheet exists to catch, wearing the
sheet's own authority. Any of the five missing and there is no sheet at all.

**It does not hide that it ran.** What it reads carries `problems` onto the
sheet, and the screen shows them: a sheet parsed out of free text is a weaker
object than one a model committed to through a tool, and the person deciding
whether to sign it is entitled to know which one is in front of them.

No instruction to a model lives here. The labels are the shape
`skills/linkedin-post` already defines and shows, exactly as `MARKER` in
`anchors.py` is the shape `references/anchoring.md` defines. A test pins them
against the shipped skill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .anchors import QUOTE_PAIRS

#: The five fields of the sheet, keyed by the name `interview.propose` takes
#: and valued by the label the skill prints. One mapping, so the two can never
#: drift into naming four things the same and one differently.
LABELS = {
    "angle": "ANGLE",
    "elements": "CONCRETE ELEMENTS",
    "moment": "THE STRONG MOMENT",
    "conviction": "CENTRAL CONVICTION",
    "first_lines": "FIRST LINE",
}

#: The two fields that are lists. The rest are one line each.
LISTS = ("elements", "first_lines")

#: `interview.propose` refuses more than two first lines. Read them all and
#: report rather than trimming: a proposal dropped here is one the person
#: never got to see, and the refusal that follows says what happened.
MOST_FIRST_LINES = 2

#: What a label line may be dressed in. A model reproducing the skill's block
#: writes a heading, a bold run, a bullet or a numbered item about as often as
#: it writes the bare word.
DECORATION = r"^[\s>]*(?:[-*+]|\d+[.)])?\s*(?:[#*_`]+\s*)*"
TRAILING = r"\s*[:：]?\s*[#*_`]*\s*[:：]?\s*"

#: Bullet markers inside a field's body.
BULLET = re.compile(r"^[\s>]*(?:[-*+]|\d+[.)])\s+(.*)$")

LABEL_LINES = {
    name: re.compile(DECORATION + re.escape(label) + TRAILING + r"(.*)$",
                     re.IGNORECASE)
    for name, label in LABELS.items()
}


@dataclass(frozen=True)
class Read:
    """What came out. `fields` is empty unless all five arrived, and is then
    exactly the mapping `interview.propose` takes."""
    fields: dict = field(default_factory=dict)
    problems: tuple = ()


def _label(line: str):
    """Which field this line opens, and whatever followed it on the line."""
    for name, pattern in LABEL_LINES.items():
        found = pattern.match(line)
        if found:
            return name, found.group(1).strip()
    return None, ""


def _unquote(value: str) -> str:
    """The skill asks for the conviction in quotes. The tool called sheet has
    none, and two sheets that say the same thing have to look the same."""
    value = value.strip()
    for opening, closing in QUOTE_PAIRS:
        if len(value) >= 2 and value.startswith(opening) \
                and value.endswith(closing):
            return value[1:-1].strip()
    return value


def _body(lines, name: str):
    """One field's value, from the lines under its label."""
    if name in LISTS:
        bulleted = [found.group(1).strip() for found in
                    (BULLET.match(line) for line in lines) if found]
        if bulleted:
            return [entry for entry in bulleted if entry]
        return [line.strip() for line in lines if line.strip()]
    return _unquote(" ".join(line.strip() for line in lines if line.strip()))


def sheet(text: str) -> Read:
    """Read the five fields out of an answer, or read nothing at all."""
    found: dict = {}
    problems: list = []
    current, buffer = None, []

    def close():
        if current is None:
            return
        value = _body(buffer, current)
        if value and current not in found:
            found[current] = value

    for line in (text or "").splitlines():
        name, inline = _label(line)
        if name is None:
            buffer.append(line)
            continue
        close()
        if name in found:
            # Padding, or a model restating itself. The first one is what it
            # committed to, and letting a later one win would let it overwrite
            # that quietly.
            problems.append(
                f"{LABELS[name]} appears more than once; the first was kept")
            current, buffer = None, []
            continue
        current, buffer = name, ([inline] if inline else [])
    close()

    missing = [LABELS[name] for name in LABELS if name not in found]
    if missing:
        # No partial sheet. `propose` would refuse it anyway, and a field
        # filled in here to get past that refusal is the invention this whole
        # apparatus exists to catch.
        problems.append("not a sheet: " + ", ".join(missing)
                        + " could not be read")
        return Read(fields={}, problems=tuple(problems))
    if len(found["first_lines"]) > MOST_FIRST_LINES:
        problems.append(
            f"{LABELS['first_lines']} carries {len(found['first_lines'])} "
            f"proposals and the sheet takes {MOST_FIRST_LINES}")
    return Read(fields=found, problems=tuple(problems))
