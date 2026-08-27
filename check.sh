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
leaked="$(git ls-files | grep -E '(^|/)(profile|profil|voice|voix|pillars|piliers|ideas|idees|measure|mesure)\.md$' \
          | grep -v '^examples/' | grep -v '\.template\.md$' || true)"
if [ -z "$leaked" ]; then ok "clean"; else bad "these are somebody's profile:"; echo "$leaked" | sed 's/^/     /'; fi

step "every engine file is actually tracked"
missing=""
for f in $(find references skills locales lib -type f ! -name '*.pyc' 2>/dev/null); do
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
