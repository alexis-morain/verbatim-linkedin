# Frozen fixtures

The Nadia Feriel persona in the shape this application reads: four files and
two directories, with `interface_language` in the Status block.

It used to be `examples/` at the repository root, and these tests copied it
from there. The engine moved on: `examples/` is one `material.md` now, per
ADR 0001 and the pivot plan, and this application is frozen on the old format
and does not migrate to the new one.

So the fixture is frozen here, beside the code that reads it. Copying it back
out of `examples/` would test the app against a format it does not implement,
and pointing the app at the new `examples/` would fail for the right reason at
the wrong time.

Nothing here is anybody's real material. Every number, client and quote is
invented.
