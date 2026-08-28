"""Load the bundle's skills and assemble the system block for a step.

Everything a model reads comes out of `skills/`, `references/` and
`locales/` at the bundle root; this file only finds, resolves and
concatenates those texts. It holds none of its own, which is the decision
that keeps the prompts maintained in one place, and `check.sh` greps for it.

A skill cites the files it relies on by path, with `<lang>` style
placeholders for the language packs. The loader resolves every citation and
refuses a dangling one outright: this repository once shipped a skill citing
a reference that was not in the tree, and a hard error here is what makes
that a test failure instead of a silent hole in the block.

Two language axes, not one. A person is interviewed in one language and can
publish in another, and the skills cite pack files across both:
`<interface_language>` always means the interview side, while `<lang>` means
whichever side its sentence is about, which no parser can read. So
`<interface_language>` resolves to the interview language alone, and every
other placeholder resolves to both languages when they differ. The block
then carries both pack files, each named, and the skill's own prose says
which applies where. Placeholders in the body are left as written for the
same reason: a mechanical rewrite would pick one axis and pick it wrong.

Standard library only, like the rest of the engine seam.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .instance import parse_front_matter, split_front_matter

REQUIRED_KEYS = ("name", "description", "version")

#: A path a skill cites: a references/ file, or a locales/ file whose
#: language segment may be a `<placeholder>`.
CITED = re.compile(
    r"\b(?:references/[\w.-]+\.md|locales/[\w<>.-]+/[\w.-]+\.md)\b")

PLACEHOLDER = re.compile(r"<[a-z_]+>")

#: The one placeholder whose axis is unambiguous: the interview side.
INTERFACE = "<interface_language>"


class SkillError(Exception):
    pass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    version: str
    body: str


@dataclass(frozen=True)
class Citation:
    cited: str      # the path as the skill wrote it
    resolved: str   # the bundle relative path actually read
    fallback: bool = False  # the asked language pack lacks it, en stands in
    asked: str = ""  # the path the language asked for, before any fallback


@dataclass(frozen=True)
class SystemBlock:
    text: str
    citations: tuple


def list_skills(bundle_root) -> list:
    root = Path(bundle_root) / "skills"
    return sorted(path.parent.name for path in root.glob("*/SKILL.md"))


def load_skill(bundle_root, name: str) -> Skill:
    path = Path(bundle_root) / "skills" / name / "SKILL.md"
    if not path.is_file():
        known = ", ".join(list_skills(bundle_root)) or "none"
        raise SkillError(
            f"no skill called {name!r} in this bundle; there are: {known}")
    block, body = split_front_matter(path.read_text(encoding="utf-8"))
    if block is None:
        raise SkillError(f"{path} has no front matter")
    data = parse_front_matter(block)
    missing = [key for key in REQUIRED_KEYS if not data.get(key)]
    if missing:
        raise SkillError(
            f"{path} front matter is missing: {', '.join(missing)}")
    return Skill(name=str(data["name"]), description=str(data["description"]),
                 version=str(data["version"]), body=body)


def citations(bundle_root, text: str, lang: str,
              output_lang: str | None = None) -> list:
    """Every file the text cites, first seen order, one entry per resolved
    file. `lang` is the interview language; when `output_lang` differs, the
    ambiguous placeholders resolve to both languages."""
    root = Path(bundle_root)
    both = [lang] + ([output_lang] if output_lang and output_lang != lang
                     else [])
    found, taken = [], set()
    for cited in CITED.findall(text):
        if PLACEHOLDER.search(cited) is None:
            targets = [cited]
        elif INTERFACE in cited:
            targets = [_fill(cited, lang)]
        else:
            targets = [_fill(cited, code) for code in both]
        for asked in targets:
            resolved, fallback = asked, False
            if not (root / resolved).is_file():
                stand_in = _fill(cited, "en")
                if stand_in == asked or not (root / stand_in).is_file():
                    raise SkillError(
                        f"the skill cites {cited}, and {asked} is not in the "
                        "bundle. A citation that resolves to nothing is a "
                        "hole in the block, not a detail.")
                resolved, fallback = stand_in, True
            if resolved in taken:
                continue
            taken.add(resolved)
            found.append(Citation(cited=cited, resolved=resolved,
                                  fallback=fallback, asked=asked))
    return found


#: A language code names a directory under `locales/`, so it is checked the
#: way every other path segment in this engine is.
LANG = re.compile(r"\A[a-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})?\Z")


def _fill(cited: str, lang: str) -> str:
    """Put a language code into a cited path.

    Substituted as data, not as a replacement template: a language code read
    out of somebody's profile is somebody's text, and `\\1` in a replacement
    means something entirely different from `\\1` in a path. Checked as a path
    segment for the same reason, since that is what it becomes.
    """
    if not LANG.match(lang):
        raise SkillError(
            f"{lang!r} is not a language code. It names a directory under "
            "locales/, so it is two or three letters, optionally a region.")
    return PLACEHOLDER.sub(lambda match: lang, cited)


def split_sections(body: str) -> list:
    """The body as (heading, text) pairs, in order. The first pair is the
    preamble before any `## ` heading, under the empty heading."""
    parts = []
    heading, lines = "", []
    for line in body.splitlines():
        if line.startswith("## "):
            parts.append((heading, "\n".join(lines).rstrip()))
            heading, lines = line[3:].strip(), [line]
        else:
            lines.append(line)
    parts.append((heading, "\n".join(lines).rstrip()))
    return parts


def _select(body: str, wanted) -> str:
    parts = split_sections(body)
    known = [heading for heading, _ in parts if heading]
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise SkillError(
            f"no section called {', '.join(repr(n) for n in unknown)}; "
            f"the sections are: {', '.join(known)}")
    kept = [text for heading, text in parts
            if heading == "" or heading in wanted]
    return "\n\n".join(part for part in kept if part)


def system_block(bundle_root, name: str, lang: str, *,
                 output_lang: str | None = None,
                 sections=None) -> SystemBlock:
    """The text a model reads for one step: the skill body, or the chosen
    sections of it with the preamble, followed by every file that text
    cites, across both language axes when they differ. All of it comes from
    the bundle; the only lines added here name which file the reader is in."""
    root = Path(bundle_root)
    body = load_skill(bundle_root, name).body
    if sections is not None:
        body = _select(body, tuple(sections))
    cites = citations(bundle_root, body, lang, output_lang)
    parts = [body.rstrip()]
    for cite in cites:
        header = f"===== {cite.resolved}"
        if cite.fallback:
            header += (f" (standing in for {cite.asked}, "
                       "which is not in its pack)")
        content = (root / cite.resolved).read_text(encoding="utf-8").rstrip()
        parts.append(header + "\n\n" + content)
    return SystemBlock(text="\n\n".join(parts), citations=tuple(cites))
