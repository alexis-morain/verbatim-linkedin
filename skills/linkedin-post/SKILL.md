---
name: linkedin-post
description: "Interviews a person to extract one idea, then writes a LinkedIn post in their voice, checks it, archives it and publishes it. Triggers: write a LinkedIn post, I have an idea for a post, turn this into a post. Not for setting up pillars or a voice profile (use linkedin-setup)."
version: 0.2.2
---

# Write a post

> **Paths in this file are relative to the bundle root**, the directory holding
> the router `SKILL.md`, not to this skill's own directory. The bundle installs
> as one unit so that `references/`, `locales/` and `lib/` resolve the same way
> from every skill in it.

The bottleneck is not writing, it is extraction. This skill interviews first
and writes second. **It never invents material.**

## Before anything

1. Read the profile's `## Status` block. If `filled: no`, say so in one line
   and offer `linkedin-setup`. Do not proceed by guessing who this person is.
2. Read `profile.md`, `voice.md`, `pillars.md`, `ideas.md`.
3. Read `locales/<interface_language>/style.md` and `interview.md`. If the pack
   does not exist, fall back to `locales/en`, and say so.
4. Count the pillars of the last eight `state: published` files in `posts/`,
   drafts do not count. Announce the balance in one line and name the pillar
   that is behind.
5. Find posts published more than seven days ago whose measurement fields are
   still empty. Ask for the numbers. It takes thirty seconds and it feeds the
   loop that everything else depends on.

Then offer three ways in: a free subject, a voice note, or an idea from
`ideas.md`, prioritising the pillar that is behind.

For a voice note, transcribe locally. Nothing about this leaves the machine.

## The interview

Intents and ladder: `references/interview-intents.md`, set B.
Wording: `locales/<interface_language>/interview.md`.

**One question at a time. Never a numbered block.** Ask, wait, dig. Between
four and six turns.

The rules that matter most, restated because they are the ones that get
dropped:

- **If an answer is abstract, do not advance.** Ask for the instance again.
  A form changes subject when an answer is hollow. This does not.
- **Quote the previous answer inside the next question.**
- **Announce what is acquired and what is missing, every turn, in one line.**
- Six is a ceiling, not a target.

## The break: format and angle

Happens **after the first or second answer, not at the end.** The format
decides which rungs matter. The angle gives every later question a thesis to
serve.

Both are covered by `references/formats.md`, including the exact shape of an
angle proposal.

The one rule to carry in your head: **two angles, never one, and each one
carries a verbatim quote of something the person actually said.** If it cannot
be quoted, the angle was invented. Throw it away and ask another question.

## The validation sheet

**Nothing is written until this sheet is approved.** This is the guard that is
missed most often, and it is exactly the mechanism that catches a borrowed
experience before it reaches a draft.

Produce the sheet, then ask whether to go with it. Do not draft until there is
an answer.

**When a tool is offered for the sheet, the sheet goes through it and nothing
else is said in that turn.** One field per line of the sheet, the elements as
a list, one or two first lines. No further question, no commentary around the
call: the person reads the sheet on their screen and decides there. If the
material is thin, say so inside the sheet, under CONCRETE ELEMENTS, rather
than asking again. A small model asked for the sheet tends to answer with one
more interview question, and the person then gets no sheet at all.

```
ANGLE               one line, restated with the material collected
CONCRETE ELEMENTS   one bullet per fact from the interview, nothing else
THE STRONG MOMENT   the anecdote or reported sentence that carries the post
CENTRAL CONVICTION  in quotes, what they conclude
FIRST LINE          two proposals, or theirs
```

Three hard rules on this sheet:

- **Every bullet under CONCRETE ELEMENTS must trace to an interview answer, to
  `profile.md`, or to `corpus/`.** A bullet that does not trace comes out. No
  "plausible", no inference. A model that knows how an infrastructure usually
  works will write the usual one as a fact. That is the failure this prevents.
- The first line is the only thing most readers will see. If a proposal is
  chosen, **the post is written for it**, to the character.
- Once the sheet is approved, the interview is closed. No more questions.

## Writing

**Open the generation with an explicit output-language directive.** One line,
before anything else: the post is written in `<language>`. This is one of the
two guards against the engine's English leaking into the post.

Then produce, in this order:

1. **Three hooks, three different angles.** Not three phrasings of one idea.
   Each has to stand alone inside the fold.
2. **The body**, structured by the chosen format.
3. **The close.** One idea, not a summary. An open question only if it is
   sincere.
4. **The character count.** Do not trim by reflex: a dense long post holds, and
   `references/platform.md` explains why length is an outcome and not a
   setting. `lib/publish.py` refuses anything past the platform limit.
5. **Two photo ideas.** A **portrait** staging the action of the post, not a
   generic pose: what they do, where, with what in their hands. And a
   **visual** showing the number or the object the hook talks about.
6. **Three tips**: the **strong message**, quoting the sentence *and saying why
   it works*; the **weak spot**, naming the passage; the **lesson** for the
   next post.
7. **The raw transcript** of the interview, verbatim. It is material for later.
   The angles that were not taken are sleeping in it, and they go back into
   `ideas.md` at the end of the session.
8. **The anchors block**, format in `references/anchoring.md`: each claim of
   the body paired with what backs it, and the label says where that lives.
   `SAID:` is the interview sentence, quoted word for word in the language of
   the interview; `SHEET:` is a line of the approved sheet, copied exactly. A
   line of the sheet is never offered as `SAID:`, the person approved it and
   did not say it. A claim with nothing to back it stays bare; bare is honest,
   and a plausible quote invented to dress it is the failure the block exists
   to catch. The profile backs nothing: it is input to a question, never
   evidence.

**When a tool is offered for the post, `body` is the post alone**: the chosen
first line, the body and the close, in the output language, and nothing else.
The other hooks, the character count and the transcript stay out of it. The
transcript is already on disk, and a hook left inside the body is a sentence
the traceability check will mark as unanchored. The photo ideas and the tips
go in their own fields; the anchors block becomes the `anchors` field, one
pair per entry, the backing under `said` or `sheet` exactly as the block would
label it, under the same rules.

**The signature block is not generated, it is concatenated.** It is appended
after a blank line, without passing through the model. A generated signature
drifts a little on every post until it belongs to somebody else. It lives in
`profile.md`.

## The deterministic pass

Run it on the post body, not on the archive file: the front matter and the
title will produce findings that have nothing to do with the post.

```bash
python3 lib/lint.py --lang <lang> - < body.txt
```

It reports; the human decides. Only the rules a pack marks hard block, and
those are typically the em dash and emoji. A finding on a word the person
actually said, in a quote, stays in.

If the pack is not native reviewed, the tool says so, and its findings are
read as suggestions.

## Revisions

Free loop, no quota. Always restart from the interview material, never rewrite
blind.

**The sheet rule applies here too, and this is where it is usually forgotten.**
A revision can reintroduce an invented detail behind the guard, because the
guard only covered the first generation. Observed in the wild: a plain "change
the angle" request turned a home made verification script into a piece of
server infrastructure that never existed, stated as fact.

So: after every revision, reread the produced text and check that each new fact
comes from the interview. If one does not, say so and take it out.

Five ways in. When a revision is asked for without saying what, offer this
vocabulary. It unblocks faster than an open question.

| Revision | Offer |
|---|---|
| Redo the hook | too commercial, open on a number, sharper, make it a question |
| Change the angle | more about the failure, from the client's point of view, more contrarian, business rather than personal |
| Add an element | a numbered anecdote, an objection, a date, a consequence |
| Change the tone | blunter, less corporate, more personal, calmer, less preachy |
| One specific passage | they paste the extract, nothing else is touched |

## Graded review, on request

On a post written elsewhere, or before publishing. Return a **score out of
10**, a **status** (ready to publish, needs work, material is missing), one
sentence of verdict, then the passages to revisit **quoted**, each with a
proposed replacement.

The score alone says nothing actionable; the status is what decides. And do not
be generous: a decent post is a 7, not a 9.

## Archive, publish, measure

**A post that stays a draft is not finished.** A batch of drafts that never
shipped is the most common way this whole system dies.

1. Write `posts/YYYY-MM-DD-slug.md` with the front matter block from
   `references/measure.md`, measurement fields left empty.
2. Move the consumed idea into the used section of `ideas.md`, and add the new
   angles spotted during the interview. **Never close a session leaving the
   bank poorer than it was at the start.**
3. Publish or schedule. `lib/publish.py` handles the three tiers.

   **Never hand raw text to a scheduling tool.** Run it through
   `publish.to_scheduler_html` first. A feed renders consecutive paragraphs
   with no gap, so a post sent without empty separators arrives as a wall of
   text, and a decomposed accent that survived every layer intact shows up as a
   letter with something floating beside it. Both have happened here, on the
   same post. The converter also settles what crosses over: the post is text,
   only `**bold**` becomes markup, and a short numbered heading is the one
   place it earns its keep.

   **Check the target channel before scheduling anything.** A personal profile
   and a company page are two lines in a config file and two very different
   things in a feed. This has already gone wrong in this project's history:
   three test posts went to the wrong page and five drafts sat scheduled on it.
   `publish.py --plan` prints the target before anything is sent, and it warns
   when the channel has an id but no name.

   Deleting a post inside a scheduling tool does not unpublish it from the
   platform. Removing something already live means going to the platform.

4. At J+7, fill the measurement fields: inbound connections from target
   profiles, inbound messages that mention a project, mentions of the post in a
   meeting. Not likes. Confidence thresholds are in `references/measure.md`.

5. **Set the next session before closing this one.** This is the step that
   decides whether there is a second post at all. The bottleneck is not
   writing, it is coming back.

   Propose a date, and **attach an idea already chosen** from `ideas.md`,
   prioritising the pillar that is behind. An appointment without a subject
   gets postponed; an appointment with one gets kept. Write both at the top of
   `ideas.md`.

   If they want a reminder, set one. Do not set one unasked.

## Hard rules

- **No invented number.** Every number comes from `profile.md`, `corpus/`, or
  the interview. If one is missing, ask, or drop the claim.
- **No fabricated client experience.** Never attach a post to a lived
  experience that does not exist. The profile's abandoned segments exist
  precisely so a post is not written as if they were clients.
- **Names that are not public stay out.** `profile.md` lists them. Ask before
  citing.
- **No post aimed at a target that is out of scope for this channel.** The
  profile says which ones those are.
- **Paid promotion is disclosed.** Affiliate links included. See
  `locales/<lang>/market.md`, and note that this project has already lost a
  disclosure between a draft and its published version. It is not a style
  detail and it does not get cut for length.
- **Style**: `locales/<lang>/style.md` applies in full.
- **No comment gate** unless the profile has deliberately turned it on.
