# The sheet as a page

A tier that can publish a web page may emit the validation sheet as one, at
the moment the sheet is produced. **It is a convenience and adds no promise:**
at the floor the sheet is text in the conversation and everything below still
holds. Nothing waits on the page, and a host that cannot make one says so in
one line and carries on.

## What it is for

Two things the conversation does badly.

**The quote beside the bullet is easier to check when it is beside the
bullet.** In a transcript the sheet scrolls; on a page the claim and the
sentence it came from sit on one line and a person reads down the column.

**The character count has to be counted, not estimated.** A model asked for a
length answers with a plausible number. The page counts the actual string, in
JavaScript, in the reader's browser. That is the whole reason there is code on
it: it is the one number nobody should take on trust, and LinkedIn folds a
post at around 210 characters and hard stops it at 3,000.

## Rules, and the first one is the one that matters

**The page never carries the material.** Not the Profile section, not the
Voice traits, not the ledger, not the corpus. Publishing a page that holds
somebody's material puts their profile on somebody else's server. What goes on
the page is this post: its sheet, its quotes, its draft. Nothing else.

**No model call from the page.** It is a rendered artefact, not an
application. Whatever it shows was decided before it existed.

**It is disposable.** One per sheet, no state, nothing that persists between
sessions. A page that remembers is an installation, which is the thing this
engine stopped having.

**The conversation stays authoritative.** The person approves in the
conversation, not on the page. A page cannot be the gate: it may not exist.

## What it shows

In this order, which is the sheet's own:

1. The angle, restated.
2. **Concrete elements, one row each: the bullet, and the sentence it came
   from, with its source named.** A bullet with no quote is shown as bare and
   said to be bare, never quietly dropped.
3. The strong moment, the central conviction, the first line proposals.
4. The draft, when there is one, with the live character count under it: the
   count, the distance to the 210 character fold, and the distance to the
   3,000 character limit.

## The counting, which is the only code on the page

```html
<script>
  const body = document.getElementById("draft").textContent;
  // The count LinkedIn does: characters, not words, newlines included.
  const n = [...body].length;
  document.getElementById("count").textContent =
    n + " characters, " + (210 - n) + " to the fold, " + (3000 - n) + " to the limit";
</script>
```

`[...body]` rather than `body.length`: an emoji or an accented character built
from two code units counts once for a reader and twice for `length`, and a
count that disagrees with what the platform shows is worse than no count.

## What it does not do

No editing, no approving, no publishing, no saving. Every one of those would
make the page a component of the engine rather than a view of one moment of
it, and the floor would then be missing a component.
