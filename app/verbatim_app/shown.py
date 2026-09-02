"""The digest a form carries of what was on the screen.

Three screens now say the same sentence: the form carries a digest of what was
on the screen, a mismatch writes nothing. The sheet approval, the publishing
confirmation and the section editor all sign something a person read, and all
three can be older than the disk. This is the one implementation of that
digest, so the three cannot drift into signing different things.

Truncated to sixteen hex characters. What it guards is a screen going stale,
not an adversary picking a collision: nothing here writes on a digest alone,
the person's click does.
"""

from __future__ import annotations

import hashlib


def shown(*parts: str) -> str:
    """One digest over everything the person had in front of them."""
    payload = "\0".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
