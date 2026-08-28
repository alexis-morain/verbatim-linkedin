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
         app/tests/test_anchors.py app/tests/test_interview.py; do
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

step "no model instruction lives under app/"
# Prompts stay in skills/ and locales/. The app carries mechanics only.
prompts="$(grep -rniE 'you are (a|an|the) |system prompt|act as (a|an) |as an ai|respond only with|never reveal' \
           app/verbatim_app 2>/dev/null || true)"
if [ -z "$prompts" ]; then ok "clean"; else bad "instruction strings:"; echo "$prompts" | sed 's/^/     /'; fi

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

step "the interview screen's script"
# It carries security: the lines that move a sheet digest into the approval
# form, and the ones that decide a turn is over. Node's own test runner over a
# hand written DOM, no npm and no node_modules in a Python repository.
if command -v node >/dev/null 2>&1; then
  if node --test app/tests/interview.test.js >/dev/null 2>&1; then
    ok "app/tests/interview.test.js"
  else
    bad "app/tests/interview.test.js"
    node --test app/tests/interview.test.js 2>&1 | tail -20 | sed 's/^/     /'
  fi
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
for f in $(find references skills locales lib app/verbatim_app app/tests -type f ! -name '*.pyc' ! -path '*__pycache__*' 2>/dev/null) app/pyproject.toml; do
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
