# Interview intents

This file stores **what each question is looking for**. It never stores the
question itself. Wording lives in `locales/<lang>/interview.md`.

The split matters. An intent survives translation, a formulation does not. When
a pack has no formulation for an intent, the model writes one from the intent
and the skill says so out loud:

> Wording generated from the intent, not yet reviewed by a native speaker.

Degradation is visible. It is never silent.

## The three input affordances

Pick the affordance from the nature of the question, not from the stage.
Constraint produces more than a blank page: ticking a box costs three seconds
and yields a usable sentence, while "what is your deepest conviction?" in a free
field costs ten minutes and usually yields a platitude.

| Affordance | Use it when | Shape |
|---|---|---|
| **Options to pick from** | The question asks for an opinion or a stance. | Three propositions built from what the profile already says, plus "or write your own". |
| **Memory prompts** | The question asks for a scene the person lived. | Three italic starters that are triggers, not answers, above a free field. |
| **Editable propositions** | The question asks for a thesis or a formulation. | Three drafts the person can combine, edit, or overwrite. |

The propositions are built from the profile and the transcript so far. Never
from a template of what a good answer looks like: that is how a person ends up
agreeing to someone else's opinion.

## Set A. Setup interview

Eight intents. They run once, in `linkedin-setup`, and produce the pillars.
Every question announces what the answer becomes, in the question itself. The
person should know what they are feeding while they feed it.

| id | Seeks | The answer becomes |
|---|---|---|
| `false-belief` | What a typical client believes on arrival that is wrong. | Public stances. The raw material of contrarian posts. |
| `market-shift` | What is changing in the market that most people have not seen yet. | Analysis posts. Reading the game before the others. |
| `origin-scene` | One moment with one client that confirmed why they do this work. | The lived post. What a reader remembers. |
| `repeated-advice` | The two or three things they tell every client. | Expertise posts. What they say in private, said in public. |
| `current-quest` | What they are trying to build or prove through the business. Optional follow-up: what they are working on right now that moves toward it. | The through line, and a renewable source of ideas from work in progress. |
| `thesis` | How a stranger would be introduced to them: "he believes that...". | The sentence they get quoted on. |
| `stage` | Where the business actually is today. | The register. Starting out and established do not speak alike. |
| `cadence` | Publishing rhythm and the business objective behind it. | The mix. The objective sets the dosage of the funnel labels. |

Two intents feed the guardrails rather than the pillars, and they are worth
their own slot because nothing else in a profile captures them:

| id | Seeks |
|---|---|
| `core-conviction` | What they hold to be true that the field mostly does not. |
| `what-they-fight` | What they are against. Named, concrete, arguable. |

## Set B. Post interview

Six rungs, and two doors into the first one. They run every time, in
`linkedin-post`. This is a ladder, not a list: each question is built on the
previous answer, and the climb stops as soon as the material is sufficient.

| # | id | Seeks | Sufficiency test |
|---|---|---|---|
| 1 | `scene` | When, with whom, in what context. One specific moment. | A reader could place it on a calendar. |
| 1 | `witnessed-instance` | The other door. An occurrence of a thesis they already hold, when no scene has been given. | They can name who, when, and where. |
| 2 | `number` | What is measured in it. If nothing is, record that and move on. | The number has a source, or it is dropped. |
| 3 | `friction` | What jammed, surprised, or cost more than planned. | Something went wrong, and it is named. |
| 4 | `position` | What they conclude that most people do not. | Someone could disagree with it. |
| 5 | `cost-of-not-knowing` | What it costs a person who does not know this. | The punchline almost always comes from here. |
| 6 | `contradiction` | Optional. What in their own practice contradicts what they just said. | It makes the post hard to attack. |

### Rules that make this an interview and not a form

- **One question at a time. Never a numbered block.** Ask, wait, dig.
- **Never ask what the profile already answers.** They know what they sell.
- **If an answer is abstract, do not advance.** Ask for the instance again:
  which one, when, how many, with whom. This is the rule that separates this
  from a questionnaire. A form changes subject when an answer is hollow. This
  does not.
- **Quote the previous answer in the next question.** "That 0.04 figure", "the
  6,800 euros". They do not repeat themselves, and they can tell they are heard.
- **Do not suggest one answer inside a question.** Offering **two opposed
  options** is allowed and often useful: "did something specific trigger it, or
  did it just happen?" spares them inventing a heroic origin.
- **Announce the missing material every turn, in one line.** "We have the scene
  and the number. What is missing is what it cost you to find out." This
  replaces a question counter with a sufficiency test.
- **Six is a ceiling, not a target.** Stop at a scene, a position, and a
  consequence.
- **Rung 1 has two doors, and taking one closes the other.**
  `witnessed-instance` replaces `scene`, it never adds a step. It is the way
  in when the person arrives with a thesis and no moment behind it, which is
  the case none of the other five cover: they all assume a scene is already
  on the table. Asking that person for a scene is how an interview talks
  somebody into inventing one.

## Where the interview breaks once, on purpose

After the first or second answer, the interview stops to settle the **format**
and the **angle**. Not at the end. The format sets which rungs matter, and the
angle gives every later question a thesis to serve.

The angle is proposed **two at a time**, never one, and each one carries a
verbatim quote of something the person actually said. If it cannot be quoted,
the angle was invented and it gets thrown away. See `references/formats.md`.

### The ladder each format climbs

The six rungs above are listed in the story's order. It is not everybody's,
and running it on a stance is how an interview asks for a scene the person
never lived.

| Format | Enters on | Then | Then | Then |
|---|---|---|---|---|
| `the-story` | `scene` | `friction` | `number` | `position` |
| `the-stance` | `position` | `witnessed-instance` | `number` | `friction` |

Two climbs, not one with its steps shuffled:

- **`the-story`** starts at the moment and ends on what is concluded from it.
  `position` is the arrival, and it is earned by everything asked before it.
- **`the-stance`** starts at `position`, because a stance arrives with its
  thesis already said, and that sentence is usually the one the angle was
  quoted from. `witnessed-instance` is the rung carrying the weight here: a
  thesis with no occurrence behind it is exactly the hole this format falls
  into. `number` then goes after the person's own figures rather than the
  market's, and `friction` is read as **the objection somebody opposed to
  them**, with how they answered it asked inside that same rung.

`counter-intuitive-number`, `the-breakdown` and `the-post-mortem` have no row
here, on purpose. Their climb gets written when an interview has been run in
that format and somebody has an observation to write down. Filling the table
by symmetry with these two would be inventing an order and then obeying it.

## Set C. Page interview

Three intents. They run in `linkedin-profile`, and only for what the profile
does not already answer, which should be most of the time nothing at all. The
editorial profile is the source; this set fills the three gaps a page has that
a post does not.

| id | Seeks | The answer becomes |
|---|---|---|
| `reader-next-step` | What a stranger should do after reading the page: message, book, follow, subscribe. One action, not a menu. | The close of the About and the promise the headline makes. |
| `buyer-words` | The words clients use for the problem, in their mouths, not the person's jargon. Two or three phrases actually heard. | The headline vocabulary and the skills list. A search surface built from real speech. |
| `proof-pick` | Which two or three facts from "what I can prove" carry the page. The person picks; the engine does not rank their proof for them. | The above-the-fold About and the Featured items. |

The affordances apply as everywhere: `reader-next-step` is options to pick
from, `buyer-words` is memory prompts (heard sentences, not invented ones),
`proof-pick` is options built from the profile's own proof list.
