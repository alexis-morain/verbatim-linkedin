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
for t in lib/test_lint.py lib/test_publish.py; do
  if python3 "$t" >/dev/null 2>&1; then ok "$t"; else bad "$t"; python3 "$t" 2>&1 | tail -20; fi
done

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
for f in $(find references skills locales lib app/verbatim_app app/tests scripts -type f ! -name '*.pyc' ! -path '*__pycache__*' 2>/dev/null) app/pyproject.toml app/hatch_build.py; do
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

step "the material format still counts to thirteen"
# 1.1 of the pivot plan exists because a hand migration already lost a
# signature block in silence, and nothing could be compared against anything.
# The list is that comparison, so the list itself is held here rather than by
# whoever remembers to reread it. Nine parsed columns and four in the free
# text tail, per ADR 0001, plus the block that actually went missing.
out="$(python3 - 2>&1 <<'MATERIAL'
import pathlib
import re
import sys

doc = pathlib.Path("references/material.md")
text = doc.read_text(encoding="utf-8")

def rows(start, end):
    """Field names in the first column of one table."""
    body = text.split(start)[1].split(end)[0]
    return re.findall(r"^\| `(\w+)`", body, re.M)

wrong = []
try:
    columns = rows("### The nine parsed columns", "### The four in the free text tail")
    tail = rows("### The four in the free text tail", "### Confidence thresholds")
except IndexError:
    sys.stderr.write("the ledger headings moved, so nothing could be counted\n")
    sys.exit(2)

if len(columns) != 9:
    wrong.append("%d parsed columns, not 9: %s" % (len(columns), ", ".join(columns)))
if len(tail) != 4:
    wrong.append("%d fields in the tail, not 4: %s" % (len(tail), ", ".join(tail)))

#: Every field the post front matter carried. Losing one is the failure.
FIELDS = ["date", "pillar", "format", "label", "hook", "chars", "state",
          "published_ref", "measured", "inbound_connections", "inbound_dms",
          "meeting_mentions", "note"]
absent = [f for f in FIELDS if "`%s`" % f not in text]
if absent:
    wrong.append("no longer described: %s" % ", ".join(absent))

#: The one that went missing for real, and is prose rather than a field.
if "Signature block" not in text:
    wrong.append("the signature block section is gone, which is how this started")

if wrong:
    print("\n".join(wrong))
    sys.exit(1)
MATERIAL
)"
case "$?" in
  0) ok "9 columns, 4 in the tail, 13 fields" ;;
  1) bad "the material format lost something:"; echo "$out" | sed 's/^/     /' ;;
  *) bad "the material check could not run:"; echo "$out" | sed 's/^/     /' ;;
esac

step "app/, which this block no longer checks"
# app/ is frozen at 2.5.0 and its steps moved to scripts/check-app.sh: they
# cost about thirty of the thirty six seconds this block used to take, and a
# commit on a skill should not pay to rebuild a Python application nobody is
# developing. Frozen is not unchecked, so the split is stated here rather than
# left to whoever remembers it, and it gets louder when app/ has actually
# moved. release.yml runs both, because a DMG is built out of app/.
# Scoped to what check-app.sh actually reads: app/, and the two Swift files
# it compiles. Widening it to all of scripts/ would cry wolf on smoke.py and
# on this split's own script, and a guard that cries wolf gets ignored.
# No filter on app/dist/: it is gitignored, so the built wheels never reach
# this list in the first place.
touched="$(git status --porcelain -- app/ 'scripts/*.swift' 2>/dev/null || true)"
if [ -z "$touched" ]; then
  printf '   note app/ was not checked. ./scripts/check-app.sh does that.\n'
else
  bad "app/ or a launcher Swift file changed, and this block did not check it."
  echo "$touched" | sed 's/^/     /'
  printf '     run ./scripts/check-app.sh\n'
fi

printf '\n'
if [ "$fail" -eq 0 ]; then echo "all checks passed."; else echo "checks failed."; fi
exit "$fail"
