# Style taxonomy

Ten categories of AI tell. The categories are universal. The word lists that
fill them are not, and they are never translated.

Every language pack carries a `style.md` (prose rules, for the model) and a
`lint.yml` (exact strings, for `lib/lint.py`). Both are organised by the ten
ids below. A pack that skips a category declares it empty rather than dropping
the key, so a reader can tell "nothing to flag here" from "nobody wrote this
yet".

| id | What it catches |
|---|---|
| `grandiose-verbs` | Verbs that inflate an ordinary action into an event. |
| `hollow-jargon` | Nouns that sound like expertise and carry no claim. |
| `filler-crutches` | Phrases that buy time before the sentence starts. |
| `fake-hooks` | Openers that announce a subject instead of stating it. |
| `schoolbook-transitions` | Connectives from a graded essay, not from speech. |
| `summarizing-closers` | Endings that repeat the post instead of ending it. |
| `forced-empathy` | Validation addressed to nobody. |
| `negative-parallelism` | "Not X, it's Y." A shape, not a word list. |
| `dramatic-fragmentation` | One-word lines, "read that again", rhetorical beats. |
| `typography` | Em dashes, emoji, spacing and quote conventions. |

## Why the lists are not translations of each other

Three asymmetries, each one enough on its own to kill the idea of translating
a single list:

1. **A word can be a cliche in one language and neutral in another.**
   `scalable` and `mindset` are borrowed marketing tells in French. In English
   they are ordinary words that a technical post may need.
2. **Some tells have no counterpart.** French "force est de constater" has no
   English equivalent worth listing. English "in today's fast-paced world" has
   no French twin.
3. **The same category can rank differently.** Negative parallelism is the
   dominant English tell of 2026 and merely common in French. Weighting has to
   follow the language, not the category.

## What belongs where

- The **category** is engine-side. It goes in this file and nowhere else.
- The **list** is pack-side. It goes in `locales/<lang>/lint.yml`.
- The **explanation of why a category matters to a reader** is pack-side too,
  in `locales/<lang>/style.md`, because the example has to be in the language.

## Two rules for the lint pass

**Never rewrite by substitution.** `negative-parallelism` in particular has no
mechanical fix: the repair is two separate statements, and only the author
knows which two. The lint reports, the human decides.

**A hit is a question, not a verdict.** A post that quotes a client saying
"game-changer" should keep the word. The pass flags, it does not block. The
only entries that block are the ones a pack marks `hard: true`, and a pack
should keep that set very small.
