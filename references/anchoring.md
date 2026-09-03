# Anchoring

How a draft proves its sources. The engine's promise is that it writes nothing
the person did not say, and anchoring is the piece of that promise a machine
can check: it verifies that a quoted sentence exists in the interview
transcript. It never verifies that a claim is true. Truth stays with the
human; presence in the transcript is what a program can decide. Which
transcript, and what else may stand in for one, is a second question, and
`Provenance` at the end of this file answers it.

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


## Provenance

Anchoring answers whether a claim is backed. Provenance answers **where the
backing lives**. They are two questions, and each has its own failure.

A draft is written from more than the transcript. The drafting turn is handed
the interview sides, the sheet the person signed, and the current revision
request. Only the first of those is the transcript. So a claim can be well
founded and still have no quote in `said()`, because it descends from a sheet
the person approved rather than from a sentence they typed. Today such a claim
can only come back `unanchored`, and that under reports it: it is not
baseless, it is backed somewhere this block cannot name.

Naming it is what this section is for.

### The label is derived, never written

The rule that carries the most weight, and the cheapest one to get wrong:

**The words shown to a person over a backing are computed from its provenance.
They are never a fixed string in a template.**

"Because you said" is true over a transcript backing and false over every
other one. A template that prints it regardless will eventually print it over
a sentence nobody uttered, and it will look exactly like a quotation. A
fabricated anchor still covers its claim, and a mislabelled one still
convinces its reader. The second is the worse of the two, because the machine
reports the first and cannot see the second at all.

### The provenances this engine has

| Provenance | Where it lives | May back a claim | Seam |
|---|---|---|---|
| **Transcript** | `said()`, every word the person typed, revision requests included | yes | `SAID:` |
| **Sheet** | `conversation.sheet`, once approved | yes, when its seam is read | reserved, not emitted |
| **Profile** | the instance on disk | no | none, and never |
| **Engine speech** | `engine_turns()`, tool results | no | none, and never |

The last two rows are the load bearing ones.

The **profile** is what the person wrote about themselves, once, outside this
session. It is legitimate input to a question and to an angle. It is not
evidence. A post that quotes the profile back proves only that the profile
exists, and the person recognises their own words without noticing that
nothing was verified.

**Engine speech** is already excluded by `said()`, for the reason its
docstring gives: a model that could quote the question it was just asked would
satisfy anchoring without the person having said anything.

### Approval is consent, not utterance

The sheet is signed by a person, and that signature is real: an approved sheet
closes the questions. It does not make the sheet's sentences theirs. Its
elements are the engine's rewording of what was said, and a rewording is
exactly where a number drifts a digit or a hedge quietly disappears.

So **a backing never converts**. A claim backed by the sheet is shown as
backed by the sheet, over the person's approval, and not as something they
said. Print the two the same way and the sheet becomes a laundry: anything the
engine wrote into it comes out wearing the person's voice.

### An ingested source, if one is ever accepted

This engine interviews. It does not read articles, and keeping it that way is
a product decision rather than a technical one: material the person did not
live is the failure this bundle exists to prevent, and a document is the
easiest way to import some.

If a source is ever accepted, provenance is what makes it survivable, and the
rules follow from the ones above instead of being new:

- a source is a **piece with an identity**: a name, a year, a locator. Without
  one it cannot be cited, and what cannot be cited cannot back a claim.
- source material **does not count toward sufficiency**. An interview ends
  when the person has said enough, and a document says nothing on their
  behalf.
- ownership is asked once, at ingestion, and asked in the words of its
  consequence rather than of its setting. Whether the material is the person's
  own decides whether the draft speaks it or cites it, and that is the
  sentence to put on the screen.
- **the sheet shows the source material it will use.** A sheet that promises
  everything it will use and omits one channel is worse than no sheet at all,
  because it spends the person's trust on an incomplete list.

### Adding a provenance

A seam the machine does not read is not a seam. `anchors.py` reads `POST:` and
`SAID:`, and reports every other line inside the block as a problem. A writer
told today to emit a third label would produce a block full of problems and
claims anchored to nothing.

So until its machine side lands, **a backing whose provenance has no seam is
not emitted, and its claim stays bare**. That is already what this contract
asks for when nothing backs a claim, and it stays honest: the reader sees an
unanchored claim and asks about it.

Landing a provenance means landing all of it at once, because a half landed
seam is the mislabelling this section exists to prevent:

1. the parse accepts the label, and the two guards that catch entry shaped
   lines outside the block know it too
2. an anchor carries which provenance backs it, rather than the pair alone
3. verification picks the text to search from that provenance, so a quote is
   checked against the thing it claims to come from and nothing else
4. `fabricated` is decided per provenance: a quote absent from the source it
   named is fabricated, whichever source that was
5. the screen derives its wording from the provenance, in `locales`, one
   phrasing per provenance per language
6. the sheet and the archive carry it, so a post read a year later still says
   where each line came from
