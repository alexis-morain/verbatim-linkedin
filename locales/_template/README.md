# Language pack template

Copy this directory to `locales/<code>/` and fill the four files. Use an
ISO 639-1 code (`nl`, `de`, `pt`), lowercase.

| File | Holds | Read by |
|---|---|---|
| `style.md` | Prose style rules, in the language, with examples. | The model, before writing. |
| `lint.yml` | Exact strings and patterns, by taxonomy id. | `lib/lint.py`, deterministically. |
| `interview.md` | The wording of each intent from `references/interview-intents.md`. | The model, during the interview. |
| `market.md` | Local platform conventions and disclosure obligations. | The model, before publishing. |

## What must never go in here

**Anything about one person.** Their pillars, their clients, their numbers,
their signature. That is a profile, and profiles stay on the machine that made
them. A language pack describes a language, not an author.

**A translation of another pack.** The categories are shared, the lists are not.
`scalable` is a tell in French and an ordinary word in English. "Force est de
constater" has no English twin. Write against the taxonomy, in your language,
from what you actually hear people say. A pack that reads like a translation
will flag the wrong words and miss the real ones.

## Acceptance criteria for a new pack

A pack is accepted when all of these hold:

1. **All four files exist**, and `lint.yml` carries every id from
   `references/style-taxonomy.md`. A category with nothing in it is declared
   empty, not omitted, so a reader can tell "nothing to flag" from "nobody got
   to this yet".
2. **A native speaker signs it.** `reviewed_by` in `lint.yml` is a real name or
   handle. If nobody has reviewed it yet, `native_reviewed: false`, and every
   skill that uses the pack announces the degradation instead of hiding it.
3. **No entry is a translation of an entry in another pack** unless it is
   independently a tell in this language. Same word, different verdict, is
   normal and expected.
4. **`interview.md` covers every intent id** in
   `references/interview-intents.md`. A missing wording is legal: the model
   generates one and says it did. A wrong wording is not.
5. **`market.md` states its jurisdiction** and dates its claims. Disclosure
   rules change and this file will go stale.
6. **`lib/lint.py --lang <code> --self-test` passes.** It checks the shape of
   the file, not the taste of the list.

Nobody has to be a maintainer to propose a pack. The bar is being a native
speaker who publishes in the language.
