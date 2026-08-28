# Anchoring

How a draft proves its sources. The engine's promise is that it writes nothing
the person did not say, and anchoring is the piece of that promise a machine
can check: it verifies that a quoted sentence exists in the interview
transcript. It never verifies that a claim is true. Truth stays with the
human; presence in the transcript is what a program can decide.

A post is often written in another language than the interview. A French
interview feeding an English post shares no literal text with it, so nothing
can anchor the post byte to byte. The model therefore quotes its source in
the language of the interview, exactly as spoken, and the machine looks for
that quote in the transcript.

## The block

After everything else it produces, the writer appends one block:

```
ANCHORS
POST: one claim of the draft, copied exactly, on one line
SAID: the interview sentence that backs it, word for word, on one line
POST: the next claim
SAID: its source
```

Rules, each one load bearing:

- `ANCHORS` stands on a line of its own and everything after it belongs to
  the block. `POST:` and `SAID:` are the machine seam, English like file
  names and front matter keys, whatever languages the interview and the post
  use.
- One line per entry. A claim or a quote that spans several sentences becomes
  several pairs.
- `POST:` copies a fragment of the draft exactly. A paraphrase of the draft
  cannot be found in it, so an anchor written that way points at nothing.
- `SAID:` quotes the transcript word for word, in the language of the
  interview. Trimming a sentence is fine; rewording it is fabrication.
- A claim with nothing to back it stays bare. Bare is the honest output:
  the reader sees an unanchored claim and asks about it. Decorating it with
  a plausible quote is precisely the failure this block exists to catch.
- An entry shorter than ten characters, typography folded, identifies
  nothing: one letter is found in any text, and an anchor that cannot miss
  is an alarm that cannot ring. The machine reports such an entry and
  counts it as absent.

## What the machine reads off it

The comparison forgives typography and nothing else: whitespace runs, curly
against straight quotes and apostrophes, case. The words themselves must
match.

Three alarm states, equal in weight:

- **unanchored**: a claim of the draft that no pair covers. The machine
  reads claims as rough sentences, cut on line breaks and sentence
  punctuation.
- **fabricated**: a `SAID:` quote that is not in the transcript. The model
  invented a source, which is worse than naming none.
- **dangling**: a `POST:` fragment that is not in the draft.

A claim is anchored when its fragment is found in the draft and its quote is
found in the transcript. That is the only state that passes.
