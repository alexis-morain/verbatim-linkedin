#!/usr/bin/env python3
"""Generate one self contained engine per skill and language.

    python3 scripts/build-engines.py           # write engines/
    python3 scripts/build-engines.py --check   # fail if anything is stale
    python3 scripts/build-engines.py --weight  # what they carry unasked

An engine is what the floor consumes: one markdown file a person attaches to
a conversation, holding the router, one skill, and every reference and pack
file that skill needs. No second file to fetch, because the floor cannot
fetch one.

**The manifest is read, never inferred.** Each skill carries an
`engine.manifest` listing its dependencies by hand. A generator that worked
out dependencies by reading the skill's prose would be the same design that
failed four times on the markdown parser check, where a comment naming a
library and an import of it are indistinguishable to a regular expression.
The prose is still read, but only to *contradict* the manifest: a citation
the manifest does not carry is an error, because it would ship an engine
pointing at a file nobody attached.

**Both directions get read, and only one of them fails.** A path named and
not carried is broken, so it stops the build. A path carried that the skill
never asked for is merely expensive, and expensive is a judgement: the build
prints what it costs and who named it, then leaves it alone. Weight is the
measured failure mode of this bundle (`docs/eval.md`), so it is worth seeing
on every build rather than on the day somebody goes looking for it.

Standard library only, like the rest of the engine seam.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "engines"

#: A path a skill cites. Same shape as app/verbatim_app/skills.py, on purpose:
#: two readers of one convention, and a skill that satisfies one satisfies the
#: other.
CITED = re.compile(
    r"\b(?:references/[\w.-]+\.md|locales/[\w<>.-]+/[\w.-]+\.md)\b")

#: Placeholder for the size line, replaced once the body is assembled and its
#: length is known. A sentinel rather than an index, so inserting a section
#: above it cannot silently move it.
SIZE_LINE = "<!-- size -->"

#: Both spellings of the interview axis. The field was renamed and the frozen
#: app still writes the old one.
LANG_PLACEHOLDERS = ("<lang>", "<interview_language>", "<interface_language>")


def languages(root: Path = None) -> list[str]:
    """Every shipped pack, `_template` excluded."""
    return sorted(d.name for d in ((root or ROOT) / "locales").iterdir()
                  if d.is_dir() and not d.name.startswith("_"))


def skills(root: Path = None) -> list[Path]:
    """Every skill that declares what its engine carries."""
    return sorted(p for p in ((root or ROOT) / "skills").iterdir()
                  if (p / "engine.manifest").is_file())


def fill(path: str, lang: str) -> str:
    for placeholder in LANG_PLACEHOLDERS:
        path = path.replace(placeholder, lang)
    return path


def manifest(skill: Path) -> list[str]:
    """The declared dependencies of one skill, comments and blanks dropped."""
    lines = (skill / "engine.manifest").read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def dangling(engine: str, lang: str) -> list[str]:
    """Citations in the finished engine whose content is not in the engine.

    **This reads the product, not the intention.** An earlier version compared
    the manifest against the skill's own prose, which missed two whole
    surfaces: the root router, embedded in every engine, and the reference
    files themselves, which cite each other. Four of six engines shipped
    pointing at files nobody attached, and a citation of a file that did not
    exist anywhere passed every guard. Whatever the manifest says, what
    matters is whether a person holding this one file can follow every path it
    names, so that is what is checked.

    A path counts as carried when the engine holds a `## <path>` heading for
    it, which is how `one()` writes every embedded file.
    """
    carried = {line[3:].strip() for line in engine.splitlines()
               if line.startswith("## ")}
    missing = set()
    for cited in CITED.findall(engine):
        if fill(cited, lang) not in carried:
            missing.add(cited)
    return sorted(missing)


def cited_by(path: str, root: Path) -> set[str]:
    """Every reference path the file at `path` names, `<lang>` left as written."""
    target = root / fill(str(path), "en")
    if not target.is_file():
        return set()
    return set(CITED.findall(target.read_text(encoding="utf-8")))


def unasked(skill: Path, root: Path = None) -> list[tuple[str, int, str]]:
    """What a skill's engine carries that the skill itself never asks for.

    `dangling()` reads one direction: a path named has to be carried, or the
    person holding the file follows it into nothing. This reads the other, and
    it is the direction that costs bytes. A file enters an engine because
    something named it, and the thing that named it is often not the skill. The
    router ships in all six engines and names four references; a reference file
    names another in a see-also sentence. Neither asked whether this particular
    skill needed it.

    **This prints and does not fail.** Whether carried weight is justified is a
    judgement about what a model needs to read, which no regular expression
    holds: a skill can need a file it names in prose rather than as a path, and
    that file lands here looking unused. So the cost is put in front of whoever
    changed the manifest, at the moment they changed it, and they decide. A
    build that refused would be a rule pretending to have read the prose.

    Returns one row per carried file the skill's own citations do not reach:
    the path, what it weighs in words, and who named it.
    """
    root = root or ROOT
    carried = manifest(skill)
    # Every file read once. The namer loop below is quadratic in the manifest
    # and the closure walks it again, so reading from disk inside either one
    # meant re-reading the same eight files dozens of times per skill.
    names = {path: cited_by(path, root) for path in carried}
    names["SKILL.md"] = cited_by("SKILL.md", root)
    own = cited_by(skill / "SKILL.md", root)

    want, queue = set(), list(own)
    while queue:                       # the closure of what the skill itself cites
        node = queue.pop()
        if node in want:
            continue
        want.add(node)
        queue += [c for c in names.get(node, cited_by(node, root)) if c not in want]
    asked = {fill(w, "en") for w in want}

    rows = []
    for path in carried:
        if fill(path, "en") in asked:
            continue
        namers = ["the router"] if path in names["SKILL.md"] else []
        namers += [Path(other).name for other in carried
                   if other != path and path in names[other]]
        target = root / fill(path, "en")
        weight = len(target.read_text(encoding="utf-8").split()) if target.is_file() else 0
        rows.append((path, weight, ", ".join(namers) or "nothing in this engine"))
    return rows


def one(skill: Path, lang: str) -> str:
    """The whole engine for one skill in one language, as text."""
    parts = [
        "<!-- Generated by scripts/build-engines.py. Do not edit here.\n"
        "     Edit the skill, its manifest, or the pack, then regenerate. -->\n",
        "# Verbatim engine: %s, %s\n" % (skill.name, lang),
        "Everything this engine needs is in this file. Attach it to a\n"
        "conversation and start. It writes no file and runs no code; where a\n"
        "host can do more, that is a convenience and never a promise.\n",
        SIZE_LINE,
        "The pack below is the %s one. If the person writes their posts in\n"
        "another language, say so plainly: the output pack is not in this\n"
        "file, and the style rules that apply are the ones written here.\n"
        % lang,
        "\n---\n\n## Router\n",
        (ROOT / "SKILL.md").read_text(encoding="utf-8"),
        "\n---\n\n## Skill: %s\n" % skill.name,
        (skill / "SKILL.md").read_text(encoding="utf-8"),
    ]
    for cited in manifest(skill):
        resolved = fill(cited, lang)
        target = ROOT / resolved
        if not target.is_file():
            stand_in = ROOT / fill(cited, "en")
            if not stand_in.is_file():
                raise SystemExit("%s: %s names nothing" % (skill.name, cited))
            parts.append("\n---\n\n## %s\n\n> The %s pack has no %s. The English\n"
                         "> one stands in, and this line is the degradation\n"
                         "> being announced rather than hidden.\n"
                         % (resolved, lang, Path(cited).name))
            target = stand_in
        else:
            parts.append("\n---\n\n## %s\n" % resolved)
        parts.append(target.read_text(encoding="utf-8"))
    # The size, written into the file the size describes. Measured on the body
    # only and rounded to the nearest thousand words, so adding this line
    # cannot change the number it reports. A reader needs it: a host with a
    # small window truncates a system block that does not fit rather than
    # refusing it, which is silent, and nothing downstream can tell the
    # difference between a model that failed and a model that never saw the
    # rules.
    words = len(" ".join(parts).split())
    size = ("**About %d thousand words, so roughly %d thousand tokens.** A host "
            "whose window is smaller than that will truncate this file rather "
            "than refuse it, and say nothing.\n"
            % (round(words / 1000), round(words * 1.3 / 1000)))
    parts[parts.index(SIZE_LINE)] = size
    return "\n".join(parts)


def build(check: bool) -> int:
    OUT.mkdir(exist_ok=True)
    declared = skills()
    stale, wrote = [], 0
    for skill in declared:
        for lang in languages():
            text = one(skill, lang)
            missing = dangling(text, lang)
            if missing:
                print("%s.%s points at what it does not carry: %s"
                      % (skill.name, lang, ", ".join(missing)), file=sys.stderr)
                print("  add it to skills/%s/engine.manifest, or stop citing "
                      "it as a path." % skill.name, file=sys.stderr)
                return 2
            path = OUT / ("%s.%s.md" % (skill.name, lang))
            if check:
                if not path.is_file() or path.read_text(encoding="utf-8") != text:
                    stale.append(path.relative_to(ROOT))
            else:
                path.write_text(text, encoding="utf-8")
                wrote += 1
                print("  %-34s %6d words" % (path.relative_to(ROOT),
                                             len(text.split())))
    if check:
        if stale:
            print("stale, regenerate with scripts/build-engines.py:",
                  file=sys.stderr)
            for path in stale:
                print("  %s" % path, file=sys.stderr)
            return 1
        return 0
    print("%d engines written" % wrote)
    report(declared)
    return 0


def report(declared: list[Path]) -> None:
    """Print what the engines carry unasked, per skill, once for all languages.

    Language independent on purpose: `<lang>` resolves to a different pack but
    to the same shape, so a row here is the same row in every pack, and saying
    it six times would bury it.
    """
    rows = [(skill, unasked(skill)) for skill in declared]
    if not any(carried for _, carried in rows):
        return
    engines = len(declared) * len(languages())
    total = sum(w for _, carried in rows for _, w, _ in carried) * len(languages())
    print("\ncarried without the skill asking for it, which is what naming a "
          "path costs:")
    for skill, carried in rows:
        for path, words, namers in carried:
            print("  %-17s %-28s %5d words   named by %s"
                  % (skill.name, path, words, namers))
    print("  %d words across %d engines. Not an error: a skill can need a file "
          "it names in\n  prose rather than as a path. This is the bill, and "
          "reading it is the whole point." % (total, engines))


def self_test() -> int:
    """Prove `unasked()` reports the four cases it exists to tell apart.

    Against a fixture rather than against this repository, because an assertion
    on live data passes the day somebody deletes the thing it was watching. The
    fixture's root is passed in rather than swapped into the module global,
    which would have left `OUT` pointing at the real `engines/` for the length
    of the test: harmless while nothing here writes, and a trap the first time
    something does.
    Each case is checked twice: once that the right answer comes out, and once
    that perturbing the fixture changes it. A report that silently returned
    nothing would otherwise look exactly like an engine carrying no dead
    weight, and there would be no way to tell those apart from the outside.
    """
    tmp = Path(tempfile.mkdtemp(prefix="verbatim-selftest-"))
    failures = []

    def check(name: str, got, want) -> None:
        if got == want:
            print("   ok   %s" % name)
        else:
            failures.append(name)
            print("   FAIL %s\n          want %r\n          got  %r"
                  % (name, want, got))

    def write(rel: str, body: str) -> None:
        target = tmp / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    def rows() -> dict[str, str]:
        return {path: namers
                for path, _, namers in unasked(tmp / "skills" / "demo", root=tmp)}

    try:
        # The router names one reference, as the real one does.
        write("SKILL.md", "# Router\nSee `references/router-named.md`.\n")
        write("skills/demo/SKILL.md", "# Demo\nRead `references/asked.md`.\n")
        write("references/asked.md", "Then `references/reached.md`.\n")
        write("references/reached.md", "The end of the chain.\n")
        write("references/router-named.md", "Named by the router alone.\n")
        write("references/orphan.md", "Named by nobody at all.\n")
        write("locales/en/pack.md", "A pack.\n")
        write("skills/demo/engine.manifest", "\n".join([
            "references/asked.md",
            "references/reached.md",
            "references/router-named.md",
            "references/orphan.md",
            "locales/<lang>/pack.md",
        ]) + "\n")

        got = rows()
        check("a file the skill cites is not on the bill",
              "references/asked.md" in got, False)
        check("a file the skill reaches through another is not on the bill",
              "references/reached.md" in got, False)
        check("a file only the router names is on the bill, and says so",
              got.get("references/router-named.md"), "the router")
        check("a file nobody names is on the bill, and says that",
              got.get("references/orphan.md"), "nothing in this engine")

        # Each answer above has to move when the fixture moves, or it was not
        # being measured. This is the half that catches a report gone silent.
        write("skills/demo/SKILL.md", "# Demo\nNothing is cited here.\n")
        got = rows()
        check("dropping the skill's citation puts both back on the bill",
              ("references/asked.md" in got, "references/reached.md" in got),
              (True, True))
        check("and the one it reached through names the file that named it",
              got.get("references/reached.md"), "asked.md")

        write("SKILL.md", "# Router\nNo path here.\n")
        check("a router that names nothing stops being a namer",
              rows().get("references/router-named.md"),
              "nothing in this engine")

        write("skills/demo/SKILL.md", "# Demo\nRead `references/asked.md`.\n")
        write("skills/demo/engine.manifest", "references/asked.md\n")
        check("a manifest carrying only what the skill cites has an empty bill",
              rows(), {})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("\n%d of the weight report's answers are not being measured."
              % len(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="do not write; fail if any engine is out of date")
    ap.add_argument("--weight", action="store_true",
                    help="print what the engines carry unasked; write nothing")
    ap.add_argument("--self-test", action="store_true", dest="self_test",
                    help="prove the weight report still measures something")
    args = ap.parse_args()
    if args.self_test:
        raise SystemExit(self_test())
    if args.weight:
        report(skills())
        raise SystemExit(0)
    raise SystemExit(build(args.check))
