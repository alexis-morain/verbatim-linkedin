# English pack: request for a native review

You do not need the code, the repo, or any tooling to answer this. Everything
under review is in this document.

## What this is

Verbatim is an open source tool that interviews a person before writing a
LinkedIn post in their own voice. One part of it is a style pass: a list of
words and shapes that read as machine-written, checked against a draft before
it goes out.

That list lives in a per-language pack. The French pack was written and signed
by a native speaker. The English one was written in one pass and nobody
qualified has gone over it. It currently ships with a flag that says so, and
prints this line above every result:

> note: the en pack has not been reviewed by a native speaker. Read its
> findings as suggestions.

English is about to become the default experience for most users. Flagging the
problem is not fixing it, so this is the fix.

## What I am asking you

For each entry: **keep**, **cut**, or **change the weight**. Plus anything
missing. You are the authority on all four questions below, I am not.

1. **Does this actually read as machine-written to you in 2026?** Some entries
   may have been tells two years ago and gone neutral since.
2. **Would it fire on ordinary writing?** `landscape` and `ecosystem` have
   literal meanings. A post about a hiking trail or about biology would trip
   them for no reason. Is the cost worth it?
3. **Is the weight right?** See the scale below.
4. **What is missing?** This matters more than anything you cut. A tell nobody
   listed is invisible to the tool.

Answer however is easiest: inline in this document, a mail, a voice note. There
is no form to fill.

## How the check actually works

Four things decide whether your judgment lands the way you expect.

**Whole words only.** `robust` matches "a robust system" and does not match
"robustness". No entry ever fires inside a longer word.

**Case is ignored.** `robust`, `Robust` and `ROBUST` all match.

**Weight sorts, it does not block.** The scale runs 1 to 5 and controls the
order results are printed in, nothing else. A weight 5 entry and a weight 1
entry both produce a line the writer reads and decides on.

**Two entries block a draft, and only two: the em dash and emoji.** Everything
else in this document is advisory by design. A post quoting a client who said
"game-changer" should keep the word. The check asks a question, it does not
overrule the author.

One consequence worth stating plainly, because it changes what a wrong entry
costs: a bad entry here wastes a moment of someone's attention. It does not
silently rewrite anyone's post. Nothing in this list substitutes anything. Err
toward keeping an entry you are unsure about, and tell me you were unsure.

## The ten categories

The ten category names are fixed across every language and are not under
review. The lists inside them are, and they are deliberately not translations
of the French ones: a word can be a cliche in one language and ordinary in
another.

### 1. grandiose-verbs, weight 3

Verbs that inflate an ordinary action into an event.

revolutionize, revolutionise, supercharge, turbocharge, unlock the potential,
unleash, empower, elevate your, take it to the next level

Two shapes are also matched:

| What it catches | Fires on | Does not fire on |
|---|---|---|
| "leverage" as a verb, before a possessive or a determiner | "leverage your data", "leveraging our network", "leverage the pipeline" | "the leverage ratio" |
| "transform" applied to a business abstraction | "transform your business", "transforming their pipeline" | "transform the data" |

The second one is limited to five nouns: business, approach, pipeline, mindset,
strategy. "transform the data" does not fire.

### 2. hollow-jargon, weight 3

Nouns that sound like expertise and carry no claim.

robust, holistic, synergy, synergies, landscape, ecosystem, paradigm,
best-in-class, world-class, enterprise-grade, cutting-edge, seamless,
frictionless, thought leadership, value-add, game-changer, game changer

Note that "game-changer" and "game changer" are both listed, so a hyphenated
and unhyphenated spelling each produce their own line. Same word, counted
twice. Tell me if that is noise.

This is the category I am least sure about. `robust`, `landscape` and
`ecosystem` are ordinary English words with literal meanings, and a technical
post may need all three.

### 3. filler-crutches, weight 2

Phrases that buy time before the sentence starts.

feel free to, it's important to note, it is important to note, it's worth
noting, needless to say, that being said, at the end of the day, in today's
fast-paced world, in today's world

### 4. fake-hooks, weight 4

Openers that announce a subject instead of stating it.

let's dive in, let's dive into, let's delve into, let's explore, let's talk
about, here's the thing, buckle up, plot twist

### 5. schoolbook-transitions, weight 2

Connectives from a graded essay, not from speech.

furthermore, moreover, additionally, in addition, that said

Two things to rule on. "that said" sits here at weight 2 while "that being
said" sits in filler-crutches at weight 2, which splits one idea across two
categories. And "in addition" is close to unavoidable in some registers.

### 6. summarizing-closers, weight 3

Endings that repeat the post instead of ending it.

in summary, in conclusion, to sum up, all in all, to wrap up, the bottom line is

### 7. forced-empathy, weight 3

Validation addressed to nobody.

i understand your point, that's completely valid, you're right to, great
question, i hear you

These read as chatbot replies rather than post openers. Do they belong in a
list checked against a written post at all, or are they only tells in a
conversation?

### 8. negative-parallelism, weight 5

"Not X, it's Y." A shape, not a word list, and per the project's own notes the
dominant English tell of 2026. It has no mechanical fix: the repair is two
separate sentences, and only the author knows which two.

Four shapes are matched. Here is what each one does in practice:

| Fires on | Misses |
|---|---|
| "It's not just a tool, it's a system." | "It is not just a tool, it is a system." |
| "This isn't just software, it's a practice." | same sentence written without contractions |
| "Not merely faster. Cleaner. Instead, ..." | |
| "Stop guessing. Start measuring." | |

**I found a hole here and I want your read on it.** The first two shapes only
recognise the contracted forms, `it's` and `isn't`. Written out as "It is not
just a tool, it is a system", the exact same sentence goes through untouched. I
verified this against the running code.

The question is whether it matters. If nobody writes this shape without
contractions on LinkedIn, the hole is theoretical and I will leave it. If the
uncontracted form is what a careful or non-native writer produces, then the
heaviest category in the pack is missing its most common case, and I fix it
before anything ships.

### 9. dramatic-fragmentation, weight 4

One-word lines, rhetorical beats, the drum.

let that sink in, read that again, think about it, the result?

Plus two shapes:

| What it catches | Note |
|---|---|
| Three short sentences in a row used as a beat: "Word. Word. Word." | Fires on any three consecutive one-word sentences |
| Three consecutive lines of 20 characters or fewer | Catches the stacked one-line paragraph style |

The second is the one I would expect to misfire, since a short list written as
separate lines would trip it. Worth keeping?

### 10. typography, weight 5

**This is the only category that can block a draft, and only on two rules:**

- **em dash**, forbidden. The long dash. Blocks.
- **emoji**, forbidden. Blocks.

Quote style and non-breaking space rules are empty for English on purpose,
since English uses neither the French spacing conventions nor guillemets. Say
so if you disagree, in particular about curly versus straight apostrophes.

## The one thing I would rather have than any of the above

A tell that is not on this list. Cuts make the tool quieter. An addition makes
it see something it is blind to today, and blindness is the failure that costs
a user a post that reads as machine-written.

If you have five minutes rather than an hour, spend them on that question and
skip the rest.

## What happens to your answer

The pack gets your edits, `native_reviewed` flips to true, and your name or
handle goes in `reviewed_by` unless you would rather it did not. The warning
line above disappears from every result. The project is MIT licensed and the
pack is a plain text file anyone can read.
