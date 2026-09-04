"""How much material is on the table, as a number beside the sentence.

`references/interview-intents.md` asks the engine to announce the missing
material every turn, in one line, and says why: it replaces a question
counter with a sufficiency test. That sentence is the honest half. It is also
the unreadable half, because a person mid interview cannot tell from it
whether they are nearly there or nowhere. This is the number that goes beside
it, and it never replaces it: what is missing is a judgement about the
material, and only the sentence can carry it.

**Two rules, and the second one is the contract.**

The gauge scores the density of facts, not the number of turns. Somebody who
answers four times without saying anything concrete has said nothing
concrete, and a counter that moved on each answer would tell them otherwise
at exactly the moment the interview should be digging.

And it counts what the author said, and nothing else. That is
`references/anchoring.md` applied to a gauge rather than to an anchor: the
sheet is a consent and not an utterance, the profile is not this interview,
and a tool result is a machine's. None of them is material the person put on
the table, and a number that credited them would hand back the engine's own
work as the person's own. The rule is a guarantee by construction rather than
a check: this reads one string, and `interview.sufficiency` is the one place
that decides which string, which is `said()`, the same text an anchor of
transcript provenance is verified against.

**What a fact is, said out loud because the number is a reading of it.** A
figure, and a named instance. Both are what somebody can be asked to point
at, and both are what an anchor can quote later. Neither is a measure of
whether the material is any good: a screen showing this shows the counts
beside it, so the percentage is always a reading of something inspectable and
never a verdict of its own.

Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: How many distinct facts this counts to. A threshold somebody can argue
#: with, and the reason the counts are on the screen beside the percentage:
#: what is not arguable is 5 figures and 3 named things, and that is what a
#: reader is given. Eight is the density of an interview that has a scene, a
#: number and a position in it with instances attached to each.
ENOUGH = 8

#: A sentence, for the only purpose of knowing which word starts one. A line
#: break ends one too: somebody answering in a list writes no full stops, and
#: every line of that list would otherwise open with a name.
SENTENCE = re.compile(r"[^.!?\n]+")

#: A word: starts on a letter, so a figure is not one of these. The
#: apostrophes are in it because `j'ai` and `l'annee` are one word in French
#: and splitting them would make `ai` a word starting a sentence.
WORD = re.compile(r"[^\W\d_][\w'’-]*", re.UNICODE)

#: A figure, with the separators a keyboard and a locale put inside one:
#: `6 800`, `0,04`, `2.037`, and the narrow and non breaking spaces a word
#: processor leaves behind. Without them one number reads as two.
FIGURE = re.compile(r"\d+(?:[.,    ]\d+)*")

#: Below this a token is not an instance anybody can point at, and `I` is the
#: author rather than a name.
SHORTEST = 2


@dataclass(frozen=True)
class Reading:
    """What is on the table: the counts, and the number read off them."""
    figures: int = 0
    named: int = 0

    @property
    def facts(self) -> int:
        return self.figures + self.named

    @property
    def ratio(self) -> int:
        """The percentage, capped. Past the threshold there is nothing more
        to say than that there is enough, and a figure over a hundred would
        invite somebody to keep feeding a gauge instead of stopping."""
        return min(100, round(100 * self.facts / ENOUGH))

    @property
    def enough(self) -> bool:
        return self.facts >= ENOUGH


def of(said: str) -> Reading:
    """The reading of one text: what somebody said, and nothing else.

    Distinct facts, not mentions. Density is the thing being measured, and a
    gauge paying per mention would pay most to the person who repeats
    themselves, which is the opposite of what the interview is asking for.
    """
    figures = {_plain(found.group()) for found in FIGURE.finditer(said)}
    named = set()
    for sentence in SENTENCE.finditer(said):
        # The first word of a sentence is capitalised because it starts one.
        # Counting those would count sentences, which is the turn counter
        # this gauge exists to replace.
        for word in list(WORD.finditer(sentence.group()))[1:]:
            token = word.group()
            if token[:1].isupper() and len(token) >= SHORTEST:
                named.add(token.casefold())
    return Reading(figures=len(figures), named=len(named))


def _plain(figure: str) -> str:
    """One figure, with the separators taken out, so `6 800` and `6800` are
    the same number said twice rather than two of them."""
    return re.sub(r"[.,    ]", "", figure)
