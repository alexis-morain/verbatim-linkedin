#!/usr/bin/env bash
# Validation block. Run before every push.
#   ./check.sh
# Exits non zero on the first failure that matters.
set -uo pipefail
cd "$(dirname "$0")"

fail=0
step() { printf '\n== %s\n' "$1"; }
bad()  { printf '   FAIL %s\n' "$1"; fail=1; }
ok()   { printf '   ok   %s\n' "$1"; }

step "tests"
for t in lib/test_lint.py lib/test_publish.py app/tests/test_instance.py \
         app/tests/test_providers.py app/tests/test_agent.py \
         app/tests/test_skills.py app/tests/test_tools.py \
         app/tests/test_anchors.py app/tests/test_interview.py \
         app/tests/test_archive.py app/tests/test_smoke.py \
         app/tests/test_prose.py app/tests/test_intents.py \
         app/tests/test_sufficiency.py; do
  if python3 "$t" >/dev/null 2>&1; then ok "$t"; else bad "$t"; python3 "$t" 2>&1 | tail -20; fi
done

step "app suite, with its dependencies"
# The block above runs on a bare interpreter and proves the stdlib only claim.
# This one installs the app and runs everything, screens and transport included.
if command -v uv >/dev/null 2>&1; then
  if (cd app && uv run --quiet python -m unittest discover -s tests -p 'test_*.py') >/dev/null 2>&1; then
    ok "app/tests"
  else
    bad "app/tests"
    (cd app && uv run --quiet python -m unittest discover -s tests -p 'test_*.py') 2>&1 | tail -20
  fi
else
  # announced degradation, not a silent pass
  printf '   skip uv not installed, the app suite did not run\n'
fi

step "the wheel carries the whole bundle"
# An installation has no checkout to fall back on, so anything the engine
# reads at run time and the wheel does not carry is a hole nobody sees until
# somebody who is not the maintainer runs it. The manifest is checked by
# app/tests/test_bundle.py; this builds the thing and looks inside it.
# Wheel only, on purpose: see the note in app/pyproject.toml.
if command -v uv >/dev/null 2>&1; then
  if (cd app && uv build --wheel --quiet) >/dev/null 2>&1; then
    wheel="$(ls -t app/dist/*.whl 2>/dev/null | head -1)"
    # Listed once, then matched without a pipe: under pipefail a `grep -q`
    # that finds its match early closes the pipe, unzip takes the SIGPIPE,
    # and the pipeline reports a failure that is really a success. Every
    # entry but the last one in the archive would read as absent.
    listing="$(unzip -l "$wheel" 2>/dev/null)"
    absent=""
    for path in SKILL.md locales/en/app.yml skills/linkedin-post/SKILL.md \
                references/anchoring.md lib/lint.py lib/publish.py; do
      case "$listing" in
        *"verbatim_app/_bundle/$path"*) ;;
        *) absent="$absent $path" ;;
      esac
    done
    if [ -z "$absent" ]; then ok "$(basename "$wheel")"; else bad "not in the wheel:$absent"; fi
  else
    bad "the wheel does not build"
    (cd app && uv build --wheel) 2>&1 | tail -10 | sed 's/^/     /'
  fi
else
  # announced degradation, not a silent pass
  printf '   skip uv not installed, the wheel was not built\n'
fi

step "no model instruction lives under app/"
# Prompts stay in skills/ and locales/. The app carries mechanics only.
prompts="$(grep -rniE 'you are (a|an|the) |system prompt|act as (a|an) |as an ai|respond only with|never reveal' \
           app/verbatim_app 2>/dev/null || true)"
if [ -z "$prompts" ]; then ok "clean"; else bad "instruction strings:"; echo "$prompts" | sed 's/^/     /'; fi

step "one markdown parser, in one file"
# Rendering a file into a page is where an export from another tool becomes
# markup in somebody's browser, and markup.py is where that boundary is set:
# html=False, images turned into links, links given a rel, no anchor inside an
# anchor. A second parser imported somewhere else would be a second boundary,
# drawn by whoever was in a hurry. The rule is held here rather than by
# discipline, like the grep above about model instructions.
#
# **This one reads the syntax tree, not the lines.** Four greps in a row got
# it wrong, and each failed from a different side: a comment naming a library
# is prose, an import inside a `try:` is code, a vendored parser arrives as
# `from .vendor import mistune`, and no regular expression tells those apart
# in a repository whose docstrings discuss markdown parsers on every other
# page. `ast` already knows which is which.
#
# One warning for whoever edits the block below: it lives inside a command
# substitution, so a bare apostrophe anywhere in it, in a comment included,
# opens a quote bash never closes and the whole script stops parsing. Write
# `does not` rather than `doesn't`. Learned by breaking it.
#
# Two things it still cannot see, and neither is a regular expression away:
# a library nobody has put on the list, and a module named at run time out of
# a string, which is `importlib.import_module` and `__import__`. Written here
# rather than papered over.
out="$(python3 - 2>&1 <<'PARSERS'
import ast
import pathlib
import sys

#: The second parser somebody might reach for. A list, because nothing here
#: can know what that will be.
BANNED = {"markdown_it", "markdown", "markdown2", "mistune", "mistletoe",
          "marko", "commonmark", "cmarkgfm"}
#: The one file allowed to hold the boundary.
BOUNDARY = pathlib.Path("app/verbatim_app/markup.py")
#: The name of this package, which is the third way to spell a path inside
#: it, and the one app/tests/ is written in.
PACKAGE = "verbatim_app"


def inside(parts, level=0):
    """Which components of a module path to weigh.

    A path that leads outside this package names a distribution by its first
    component, and only that one counts: `from typing import Mapping` must
    not match on something buried further in. A path that leads inside it can
    hold a vendored copy at any depth, so every component counts.

    Inside is three spellings of one thing, and all three have to fail
    together or the guard only teaches which one to use: `from .mistune`,
    `from verbatim_app.mistune`, and `import verbatim_app.vendor.mistune`.
    The absolute one matters most, because `app/tests/` is written that way
    and it is the line somebody copies out of a test.
    """
    return parts if (level or parts[:1] == [PACKAGE]) else parts[:1]


def hits(source, name="<fixture>"):
    """Every import of a banned parser in one file, as (line, what)."""
    found = []
    for node in ast.walk(ast.parse(source, filename=name)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for part in inside(alias.name.split(".")):
                    if part in BANNED:
                        found.append((node.lineno, alias.name))
                        break
        elif isinstance(node, ast.ImportFrom):
            parts = (node.module or "").split(".")
            for part in inside(parts, node.level):
                if part in BANNED:
                    found.append((node.lineno, node.module))
                    break
            for alias in node.names:
                # `from . import mistune`, `from .vendor import mistune`: the
                # vendored copy, which is how a second parser arrives with no
                # line in pyproject.toml to notice it. This branch reads the
                # imported name, not its alias, so it also fails on a local
                # symbol that happens to be called `markdown`, and this app
                # has one: `web.py` gives the templates a global by that
                # name. A known trade, not a bug. It fails loudly and an
                # `as` alias settles it, where dropping the branch would
                # reopen the vendoring hole in silence.
                if alias.name in BANNED:
                    found.append((node.lineno, alias.name))
    return found


# The check gets its own fixtures. It has been wrong before, and the next
# edit to it needs holding. Above the divider: what it must see. Below: what
# it must leave alone, which is where every earlier version failed.
FIXTURES = [
    ("import markdown_it", True),
    ("import os, markdown", True),
    ("import os as o, markdown_it as md", True),
    ("import markdown_it.common", True),
    ("try:\n    import markdown_it\nexcept ImportError:\n    pass", True),
    ("if True:\n    from markdown_it import MarkdownIt", True),
    ("from markdown_it.common.utils import escapeHtml", True),
    ("from . import markdown_it", True),
    ("from .vendor import mistune", True),
    ("from .mistune import Markdown", True),
    ("from .vendor.mistune import Markdown", True),
    ("from ..vendor.marko import Parser", True),
    ("import verbatim_app.mistune", True),
    ("import verbatim_app.vendor.marko", True),
    ("from verbatim_app.mistune import Markdown", True),
    ("from verbatim_app.vendor.mistune import Markdown", True),
    ("import os, \\\n    marko", True),

    ("from .markup import render  # the only markdown_it entry point", False),
    ('"""One rule: import markdown_it only in markup.py."""', False),
    ("# Note: from markdown_it we take only MarkdownIt.", False),
    ("import markdownify", False),
    ("from .archive import notes_only, post_only", False),
    ("from .markup import render", False),
    ("from .markup import render as markdown", False),
    ("from typing import Mapping", False),
    ("from verbatim_app.markup import render", False),
    ("import verbatim_app.instance", False),
]
for source, wanted in FIXTURES:
    if bool(hits(source)) != wanted:
        sys.stderr.write("the check itself does not hold on: %r\n" % source)
        sys.exit(2)

bad = []
for path in sorted(pathlib.Path("app/verbatim_app").rglob("*.py")):
    if path == BOUNDARY:
        continue
    try:
        found = hits(path.read_text(encoding="utf-8"), str(path))
    except (SyntaxError, UnicodeDecodeError, OSError) as broken:
        sys.stderr.write("%s does not read: %s\n" % (path, broken))
        sys.exit(2)
    bad += ["%s:%d: %s" % (path, line, what) for line, what in found]
if bad:
    sys.stdout.write("\n".join(bad))
    sys.exit(1)
PARSERS
)"
# Two exits, two sentences. A file that will not parse is a file to repair,
# and reporting it as a parser import would send somebody to the wrong place.
case "$?" in
  0) ok "clean" ;;
  1) bad "markdown parser imported outside markup.py:"; echo "$out" | sed 's/^/     /' ;;
  *) bad "the parser check could not run:"; echo "$out" | sed 's/^/     /' ;;
esac

step "no sentence reaches a browser from under app/"
# An HTTPException detail is rendered as the whole page body on a plain form
# navigation, so a sentence written here is a sentence in the wrong language on
# a French screen. Machine codes only; the sentence lives in locales/<lang>/app.yml.
# Scoped to routes/, which is where an HTTPException can be raised at all.
# Anything that is not a bare double quoted kebab literal fails, so a single
# quoted string, an f-string and a call all fail: none of them is a fixed code.
# An SSE frame's technical text uses another keyword for the same reason.
prose="$(grep -rnoE '(^|[^_[:alnum:]])detail=[^,)]*' app/verbatim_app/routes --include='*.py' 2>/dev/null \
         | grep -vE 'detail="[a-z0-9-]+"$' || true)"
if [ -z "$prose" ]; then ok "clean"; else bad "prose in an error detail:"; echo "$prose" | sed 's/^/     /'; fi

step "the screen scripts"
# They carry security: the lines that move a sheet digest into the approval
# form, the ones that decide a turn is over, and the one that decides which
# bytes reach a clipboard. Node's own test runner over a hand written DOM, no
# npm and no node_modules in a Python repository.
if command -v node >/dev/null 2>&1; then
  for t in app/tests/interview.test.js app/tests/copy.test.js; do
    if node --test "$t" >/dev/null 2>&1; then
      ok "$t"
    else
      bad "$t"
      node --test "$t" 2>&1 | tail -20 | sed 's/^/     /'
    fi
  done
else
  # announced degradation, not a silent pass
  printf '   skip node not installed, the screen script was not tested\n'
fi

step "language packs"
for dir in locales/*/; do
  code="$(basename "$dir")"
  [ "${code#_}" = "$code" ] || continue
  if python3 lib/lint.py --lang "$code" --self-test >/dev/null 2>&1; then
    ok "$code"
  else
    bad "$code"; python3 lib/lint.py --lang "$code" --self-test 2>&1 | sed 's/^/     /'
  fi
done

step "no profile file is tracked outside examples/"
leaked="$(git ls-files | grep -E '(^|/)(profile|profil|voice|voix|pillars|piliers|ideas|idees|measure|mesure|linkedin-page)\.md$' \
          | grep -v '^examples/' | grep -v '^references/' | grep -v '\.template\.md$' || true)"
# An interview transcript is the rawest thing a person ever says to this
# engine. It has no fixed file name to grep for, so the directory is the rule.
leaked="$leaked
$(git ls-files | grep -E '(^|/)interviews/' || true)"
if [ -z "$(echo "$leaked" | tr -d '[:space:]')" ]; then ok "clean"; else bad "these are somebody's profile:"; echo "$leaked" | sed 's/^/     /'; fi

step "every engine file is actually tracked"
missing=""
for f in $(find references skills locales lib app/verbatim_app app/tests scripts -type f ! -name '*.pyc' ! -path '*__pycache__*' 2>/dev/null) app/pyproject.toml; do
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 || missing="$missing $f"
done
if [ -z "$missing" ]; then ok "clean"; else bad "ignored by mistake:$missing"; fi

step "no .env and no key material is tracked"
secrets="$(git ls-files | grep -E '(^|/)\.env($|\.)|\.pem$|_rsa$' | grep -v '\.env\.example$' || true)"
if [ -z "$secrets" ]; then ok "clean"; else bad "$secrets"; fi

step "skill front matter"
for f in SKILL.md skills/*/SKILL.md; do
  miss=""
  for key in name description version; do
    head -12 "$f" | grep -q "^$key:" || miss="$miss $key"
  done
  # A skill description says what it is not for, so the router never picks it
  # by accident. The bundle router is exempt, it is the one doing the routing.
  if [ "$f" != "SKILL.md" ] && ! head -12 "$f" | grep -qi "not for"; then
    miss="$miss not-for-sentinel"
  fi
  if [ -z "$miss" ]; then ok "$f"; else bad "$f missing:$miss"; fi
done

step "no em dash in shipped prose"
dashes="$(grep -rln $'—' --include='*.md' --include='*.yml' . 2>/dev/null \
          | grep -v '^./lib/test_' || true)"
if [ -z "$dashes" ]; then ok "clean"; else bad "em dash in: $dashes"; fi

step "no emoji in shipped prose"
emoji="$(grep -rlnP '[\x{1F300}-\x{1FAFF}\x{2600}-\x{26FF}]' --include='*.md' . 2>/dev/null \
         | grep -v '^./lib/test_' || true)"
if [ -z "$emoji" ]; then ok "clean"; else bad "emoji in: $emoji"; fi

printf '\n'
if [ "$fail" -eq 0 ]; then echo "all checks passed."; else echo "checks failed."; fi
exit "$fail"
