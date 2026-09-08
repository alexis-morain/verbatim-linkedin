---
status: accepted
---

# The ledger is the store, and the post body is optional

`references/measure.md` set the opposite rule: one store, and it is the posts
themselves, with any table derived from them at read time and never written
back. That rule assumed a consumer with a filesystem. The engine is now written
against a floor that cannot write a file, so a person carries one attachable
`material` file and the ledger inside it becomes the record: one entry per
post, the nine fields the loops actually read, and a free text tail nothing
parses. Post bodies keep living in the corpus, where losing one costs a voice
reference rather than a measurement.

## Considered options

Keeping the post file as the store and deriving an index, as `measure.md`
anticipated, would have needed the engine to write two things and keep them
in step. At the floor it writes neither, so the person would be the one keeping
them in step by hand, which is the drift `measure.md` was written to prevent.

## Consequences

The two arguments `measure.md` gave for its own rule now support this one.
Drift: a single store cannot disagree with itself, and at the floor a second
store would be maintained by hand or not at all. Editing: filling a line at
J+7 stays a thirty second job in a file already open, and several posts can be
filled in one pass instead of one file at a time.

What is genuinely lost is per post provenance of the measurement. A ledger line
can be edited without touching anything else, where a frontmatter block sat
next to the text it described. The confidence thresholds in `measure.md` are
unchanged and still refuse to conclude under two measured posts.
