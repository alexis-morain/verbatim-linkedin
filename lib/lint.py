#!/usr/bin/env python3
"""Deterministic style pass over a post draft.

No model is involved at any point. It reads a language pack from
locales/<code>/lint.yml, applies it to a text, and reports what it finds.
The categories come from references/style-taxonomy.md.

A hit is a question, not a verdict. Only the rules a pack marks hard set a
non-zero exit code.

    python3 lib/lint.py --lang fr draft.txt
    cat draft.txt | python3 lib/lint.py --lang fr -
    python3 lib/lint.py --lang fr --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, asdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES = os.path.join(ROOT, "locales")

TAXONOMY = [
    "grandiose-verbs",
    "hollow-jargon",
    "filler-crutches",
    "fake-hooks",
    "schoolbook-transitions",
    "summarizing-closers",
    "forced-empathy",
    "negative-parallelism",
    "dramatic-fragmentation",
    "typography",
]

TYPOGRAPHY_RULES = {"em_dash", "emoji", "nbsp_before", "quotes"}

EM_DASH = "—"
NBSP = (" ", " ")
EMOJI = re.compile(
    "[\U0001f000-\U0001faff☀-⛿✀-➿️⬀-⯿]"
)


class PackError(Exception):
    """A language pack is missing, malformed, or unusable."""


@dataclass
class Finding:
    category: str
    weight: int
    hard: bool
    evidence: str
    count: int
    snippet: str


# --------------------------------------------------------------------------
# Text normalisation
# --------------------------------------------------------------------------

def soften(text: str) -> str:
    """Normalise the characters that vary between keyboards, nothing else.

    Case, accents, newlines and spacing are preserved: patterns are written
    against text that looks like what a person typed.
    """
    text = unicodedata.normalize("NFC", text)
    return text.replace("’", "'").replace("ʼ", "'")


def flatten(text: str) -> str:
    """Lowercase, accent free, whitespace collapsed. Used for term matching."""
    text = soften(text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip()


# --------------------------------------------------------------------------
# Pack loading
# --------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            out.append(ch)
            if ch == quote and line[i - 1] != "\\":
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (not out or out[-1] in " \t"):
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _unquote(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_unquote(part) for part in _split_inline(inner)]
    if raw[0] == raw[-1] and raw[0] in "\"'" and len(raw) >= 2:
        body, quote = raw[1:-1], raw[0]
        if quote == "'":
            return body.replace("''", "'")
        out, i = [], 0
        while i < len(body):
            if body[i] == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                out.append({"n": "\n", "t": "\t", "\\": "\\", '"': '"'}.get(nxt, "\\" + nxt))
                i += 2
            else:
                out.append(body[i])
                i += 1
        return "".join(out)
    if raw in ("true", "false"):
        return raw == "true"
    if raw in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


def _split_inline(inner: str):
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in (p.strip() for p in parts) if p]


def _parse_simple_yaml(text: str) -> dict:
    """Parse the subset of YAML a language pack is allowed to use.

    Mappings, lists of scalars, inline lists, comments. Anything else raises
    rather than guessing, because a silent misparse is worse than a refusal.
    """
    root: dict = {}
    # frames: (indent, container). A pending frame carries the key whose value
    # is not known to be a list or a mapping yet.
    stack = [(-1, root, None)]

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent_indent, container, pending = stack[-1]

        if pending is not None and container is None:
            raise PackError(f"line {lineno}: unexpected nesting")

        if content.startswith("- "):
            if pending is not None:
                new = []
                container[pending] = new
                stack[-1] = (parent_indent, new, None)
                container = new
            if not isinstance(container, list):
                raise PackError(f"line {lineno}: list item outside a list")
            container.append(_unquote(content[2:]))
            continue

        if ":" not in content:
            raise PackError(f"line {lineno}: cannot read {content!r}")

        key, _, value = content.partition(":")
        key, value = key.strip(), value.strip()

        if pending is not None:
            new = {}
            container[pending] = new
            stack[-1] = (parent_indent, new, None)
            container = new
        if not isinstance(container, dict):
            raise PackError(f"line {lineno}: mapping key inside a list")

        if value == "":
            container[key] = {}
            stack.append((indent, container, key))
        else:
            container[key] = _unquote(value)
    return root


def _load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        import yaml  # type: ignore
    except ImportError:
        return _parse_simple_yaml(text)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PackError(f"{path}: {exc}") from exc


def available_packs():
    if not os.path.isdir(LOCALES):
        return []
    return sorted(
        name
        for name in os.listdir(LOCALES)
        if not name.startswith("_")
        and os.path.isfile(os.path.join(LOCALES, name, "lint.yml"))
    )


def load_pack(code: str) -> dict:
    path = os.path.join(LOCALES, code, "lint.yml")
    if not os.path.isfile(path):
        have = ", ".join(available_packs()) or "none"
        raise PackError(f"no language pack {code!r}. Available: {have}")
    pack = _load_yaml(path)
    if not isinstance(pack, dict) or "categories" not in pack:
        raise PackError(f"{path}: not a language pack")
    pack.setdefault("language", code)
    pack.setdefault("native_reviewed", False)
    pack.setdefault("reviewed_by", "")
    return pack


# --------------------------------------------------------------------------
# Self test: the shape of a pack, never the taste of its lists
# --------------------------------------------------------------------------

def self_test(pack: dict):
    problems = []
    cats = pack.get("categories") or {}
    for cid in TAXONOMY:
        if cid not in cats:
            problems.append(f"missing category {cid}")
    for cid in cats:
        if cid not in TAXONOMY:
            problems.append(f"unknown category {cid}, not in the taxonomy")
    for cid, cat in cats.items():
        if not isinstance(cat, dict):
            problems.append(f"{cid}: not a mapping")
            continue
        weight = cat.get("weight")
        if not isinstance(weight, int) or not 1 <= weight <= 5:
            problems.append(f"{cid}: weight must be an integer from 1 to 5")
        if not isinstance(cat.get("hard", False), bool):
            problems.append(f"{cid}: hard must be true or false")
        for key in ("terms", "patterns", "hard_rules"):
            if key in cat and not isinstance(cat[key], list):
                problems.append(f"{cid}: {key} must be a list")
        for pattern in cat.get("patterns") or []:
            try:
                re.compile(pattern)
            except re.error as exc:
                problems.append(f"{cid}: bad pattern {pattern!r}: {exc}")
        for rule in (cat.get("rules") or {}):
            if rule not in TYPOGRAPHY_RULES:
                problems.append(f"{cid}: unknown rule {rule}")
    if not isinstance(pack.get("native_reviewed"), bool):
        problems.append("native_reviewed must be true or false")
    if pack.get("native_reviewed") and not pack.get("reviewed_by"):
        problems.append("native_reviewed is true but reviewed_by is empty")
    return problems


# --------------------------------------------------------------------------
# The pass itself
# --------------------------------------------------------------------------

def _snippet(haystack: str, at: int, width: int = 44) -> str:
    start = max(0, at - width // 2)
    return haystack[start:start + width].strip()


def _check_terms(flat, cid, cat, hard, out):
    for term in cat.get("terms") or []:
        needle = flatten(str(term))
        if not needle:
            continue
        rx = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)")
        hits = list(rx.finditer(flat))
        if hits:
            out.append(Finding(cid, cat["weight"], hard, str(term), len(hits),
                               _snippet(flat, hits[0].start())))


def _check_patterns(soft, cid, cat, hard, out):
    for pattern in cat.get("patterns") or []:
        hits = list(re.finditer(pattern, soft, re.IGNORECASE))
        if hits:
            out.append(Finding(cid, cat["weight"], hard, pattern, len(hits),
                               _snippet(soft.replace("\n", " / "), hits[0].start())))


def _check_typography(soft, cid, cat, out):
    rules = cat.get("rules") or {}
    hard_rules = set(cat.get("hard_rules") or [])
    weight = cat["weight"]

    def add(rule, evidence, count, snippet):
        out.append(Finding(cid, weight, rule in hard_rules, evidence, count, snippet))

    if rules.get("em_dash") == "forbid":
        n = soft.count(EM_DASH)
        if n:
            at = soft.index(EM_DASH)
            add("em_dash", "em dash", n, _snippet(soft, at))

    if rules.get("emoji") == "forbid":
        hits = EMOJI.findall(soft)
        if hits:
            add("emoji", "emoji " + "".join(dict.fromkeys(hits)), len(hits), "")

    for char in rules.get("nbsp_before") or []:
        n = soft.count(" " + char)
        if n:
            at = soft.index(" " + char)
            add("nbsp_before", f"ordinary space before {char}", n, _snippet(soft, at))

    quotes = rules.get("quotes") or ""
    if quotes == "«»" and '"' in soft:
        add("quotes", "straight quote, this pack expects « »",
            soft.count('"'), _snippet(soft, soft.index('"')))


def run(text: str, pack: dict):
    """Apply a pack to a text. Returns findings, heaviest first."""
    soft, flat = soften(text), flatten(text)
    out: list[Finding] = []
    for cid, cat in (pack.get("categories") or {}).items():
        if not isinstance(cat, dict):
            continue
        hard = bool(cat.get("hard", False))
        if cid == "typography":
            _check_typography(soft, cid, cat, out)
            continue
        _check_terms(flat, cid, cat, hard, out)
        _check_patterns(soft, cid, cat, hard, out)
    out.sort(key=lambda f: (-f.weight, f.category, f.evidence))
    return out


def exit_code(findings) -> int:
    return 1 if any(f.hard for f in findings) else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _report(findings, pack, stream=sys.stdout):
    if not pack.get("native_reviewed"):
        print(f"note: the {pack['language']} pack has not been reviewed by a "
              "native speaker. Read its findings as suggestions.\n", file=stream)
    if not findings:
        print("clean. nothing flagged.", file=stream)
        return
    for f in findings:
        mark = "BLOCK" if f.hard else "     "
        times = f" x{f.count}" if f.count > 1 else ""
        print(f"{mark} [{f.weight}] {f.category}: {f.evidence}{times}", file=stream)
        if f.snippet:
            print(f"        ...{f.snippet}...", file=stream)
    hard = sum(1 for f in findings if f.hard)
    print(f"\n{len(findings)} finding(s), {hard} blocking.", file=stream)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lang", required=True, help="language pack code, e.g. fr")
    ap.add_argument("path", nargs="?", help="file to read, or - for stdin")
    ap.add_argument("--self-test", action="store_true",
                    help="check the pack's shape and exit")
    ap.add_argument("--json", action="store_true", help="machine readable output")
    args = ap.parse_args(argv)

    try:
        pack = load_pack(args.lang)
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.self_test:
        problems = self_test(pack)
        for p in problems:
            print(f"error: {args.lang}: {p}", file=sys.stderr)
        if not problems:
            print(f"{args.lang}: pack is well formed.")
        return 2 if problems else 0

    if not args.path:
        ap.error("give a file to lint, or - for stdin")
    text = sys.stdin.read() if args.path == "-" else open(
        args.path, encoding="utf-8").read()

    findings = run(text, pack)
    if args.json:
        print(json.dumps({"language": pack["language"],
                          "native_reviewed": pack["native_reviewed"],
                          "findings": [asdict(f) for f in findings]},
                         ensure_ascii=False, indent=2))
    else:
        _report(findings, pack)
    return exit_code(findings)


if __name__ == "__main__":
    sys.exit(main())
