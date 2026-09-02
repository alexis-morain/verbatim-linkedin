"""Cut a document into its `## ` sections, and rewrite one of them.

A section is a `## ` heading, the body under it, and the span of characters
it occupies; the span is what lets a screen save one section and leave every
other byte of somebody's file where it was. Placeholders are looked for so a
section that is still the template talking can be marked as such: no skill
may quote one.

Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .shown import shown


@dataclass
class Section:
    """One `## ` section of a document, and the span it occupies.

    The span is what makes an edit local: a screen that saves one section
    rewrites those characters and leaves every other byte of somebody's file
    where it was.
    """
    heading: str
    body: str
    start: int
    end: int
    digest: str
    unvalidated: bool = False
    #: Another section carries the same heading, so this one cannot be
    #: addressed by it. Shown rather than guessed between.
    duplicate: bool = False


#: A section opens on `## `. Deeper headings belong to the section above them,
#: which is what a person editing one expects to keep.
HEADING = re.compile(r"^## (.*)$", re.MULTILINE)

#: An HTML comment, taken out before a placeholder is looked for: the template
#: explains its placeholders in comments, and a comment is instructions to the
#: person rather than a hole in their profile.
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

#: What the template writes where somebody's own words go. Angle brackets
#: around anything but a comment, over several lines if that is how it was
#: wrapped.
PLACEHOLDER = re.compile(r"<(?!!--)[^<>]+>", re.DOTALL)


def _blank_stripped(raw: str) -> str:
    lines = raw.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _unvalidated(body: str) -> bool:
    """Whether this section is still the template talking.

    Two ways: nothing in it, or a placeholder nobody replaced. Both are the
    same fact for a reader, which is that no skill may quote this section.
    """
    if not body.strip():
        return True
    return PLACEHOLDER.search(COMMENT.sub("", body)) is not None


def sections_of(text: str) -> list:
    """Every `## ` section of a document, in order, with its span.

    The preamble is not one: it is the title and whatever sits under it, and
    nothing addresses it by a heading.
    """
    marks = list(HEADING.finditer(text))
    seen: dict = {}
    found = []
    for index, mark in enumerate(marks):
        heading = mark.group(1).strip()
        # The span opens on the newline that ends the heading line, so a
        # rewrite of it never touches the heading itself.
        start = mark.end()
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = _blank_stripped(text[start:end])
        seen[heading] = seen.get(heading, 0) + 1
        found.append(Section(heading=heading, body=body, start=start, end=end,
                             digest=shown(heading, body),
                             unvalidated=_unvalidated(body)))
    for section in found:
        section.duplicate = seen[section.heading] > 1
    return found


def _status_line(text: str, key: str, value: str) -> str:
    """Rewrite one `- key:` line of the Status block, textually.

    Inside the block's own span, so a line of the same shape further down the
    file is not the one that moves. A block with no such key and no keys at
    all is a block to repair: nothing is invented into it here, and the
    conformance report already says so.
    """
    found = [s for s in sections_of(text) if s.heading == "Status"]
    if not found:
        return text
    section = found[0]
    span = text[section.start:section.end]
    line = f"- {key}: {value}"
    pattern = re.compile(rf"^-\s+{key}:.*$", re.MULTILINE)
    if pattern.search(span):
        span = pattern.sub(lambda _: line, span, count=1)
    else:
        keys = list(re.finditer(r"^-\s+\w+:.*$", span, re.MULTILINE))
        if not keys:
            return text
        span = span[:keys[-1].end()] + "\n" + line + span[keys[-1].end():]
    return text[:section.start] + span + text[section.end:]
