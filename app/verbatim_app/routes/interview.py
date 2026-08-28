"""The interview screen: the first one that talks to a model.

The mechanism is the loop from `agent.py`, unchanged, with its steps turned
into frames a browser can read. Everything the model reads is assembled by
`skills.py` out of the bundle, every turn; nothing on this side of the seam
has anything to say.

Three things here are decisions rather than plumbing.

**The turn is a POST that streams, not an EventSource.** EventSource speaks
GET only, and a cross origin no-cors GET carries no Origin header, so a GET
that ran a turn would be reachable from any page the person has open: they
could not read the answer, but they would pay for it. A POST carries Origin
in every browser, which the guard in `web.py` already refuses when it is not
this app. The wire format is still server sent events, only the client is
`fetch`.

**The conversation reaches disk before it reaches the screen.** Every step
that changes it is saved first and yielded second, so a browser closed mid
turn leaves a conversation a provider would still accept rather than a
dangling tool call. That property was built into the loop in slice 5.1; this
is the screen where it gets paid for, because a browser closing mid interview
is the normal case.

**Cost is shown as rate and running total, never as a forecast.** The engine
knows the price per million for the models in its table and the exact size of
what it sends every turn. It does not know how many turns somebody will take,
and a made up estimate over somebody's real bill is the failure `providers.py`
already refuses when it declines to guess a price.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, replace

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse

from . import render as _render
from .. import anchors, interview
from ..agent import Agent, AgentError, http_transport
from ..instance import InstanceError
from ..providers import (
    PRICES, ProviderError, Settings, Usage, price, problems, resolve,
)
from ..skills import SkillError, system_block
from ..tools import (
    DRAFT_TOOL, SHEET_TOOL, ToolRefused, draft_tool, instance_tools,
    lint_body, redact, sheet_tool,
)

router = APIRouter()

#: One turn at a time per interview. The person double clicking, or two tabs
#: on the same conversation, would otherwise interleave two turns into one
#: message list and leave a shape no provider accepts.
_registry = threading.Lock()


def lock_for(app, interview_id: str) -> threading.Lock:
    with _registry:
        return app.state.turn_locks.setdefault(interview_id, threading.Lock())


def forget_lock(app, interview_id: str) -> None:
    """Drop the lock of an interview that no longer exists, so the registry
    tracks what is on disk rather than everything ever opened."""
    with _registry:
        lock = app.state.turn_locks.get(interview_id)
        if lock is not None and not lock.locked():
            del app.state.turn_locks[interview_id]


# ------------------------------------------------------------------ the engine

@dataclass
class Engine:
    """What would answer, and what stops it from answering."""
    settings: Settings | None = None
    gaps: tuple = ()
    refusal: str = ""       # the machine code, the pack holds the sentence
    refusal_names: str = ""  # names and hosts, never a value
    block_size: int = 0
    block_error: str = ""

    @property
    def ready(self) -> bool:
        return self.settings is not None and not self.gaps and not self.refusal

    @property
    def rate(self):
        if self.settings is None:
            return None
        return PRICES.get(self.settings.model)


def _engine(request: Request, *, sized: bool = False) -> Engine:
    """Resolved per request on purpose: somebody who fixes their instance
    `.env` and reloads gets a working screen instead of a restart."""
    instance = request.app.state.instance
    try:
        settings = resolve(instance.root, request.app.state.environ)
    except ProviderError as refusal:
        # The code, never the message: the message is written for a terminal.
        return Engine(refusal=refusal.code or "engine-refused",
                      refusal_names=refusal.detail)
    engine = Engine(settings=settings, gaps=tuple(problems(settings)))
    if sized:
        try:
            engine.block_size = len(_block(request).text)
        except SkillError as broken:
            engine.block_error = str(broken)
    return engine


def _block(request: Request, conversation=None, sections=None):
    """The step of the skill this screen drives, assembled from the bundle.

    Both language axes are passed, always. One language for an interview held
    in French and published in English is the leak the loader was fixed for:
    the person would be asked questions in the wrong language, or written for
    against the wrong market pack.
    """
    status = request.app.state.instance.status()
    interface = (conversation.interface_language if conversation
                 else (status.interface_language if status else "en"))
    output = (conversation.output_language if conversation
              else (status.output_language_default if status else "en"))
    return system_block(request.app.state.bundle,
                        conversation.skill if conversation else interview.STEP_SKILL,
                        interface, output_lang=output,
                        sections=(sections if sections is not None
                                  else (conversation.sections if conversation
                                        else interview.STEP_SECTIONS)))


def _conversation(request: Request, interview_id: str):
    try:
        return interview.load(request.app.state.instance.root, interview_id)
    except interview.InterviewError:
        # Without a detail this is FastAPI's own "Not Found", which is English
        # prose on whatever screen renders it.
        raise HTTPException(status_code=404, detail="gone")


# ----------------------------------------------------------------- the screens

@router.get("/interview")
def hub(request: Request):
    instance = request.app.state.instance
    engine = _engine(request, sized=True)
    try:
        entries = interview.listing(instance.root)
    except interview.InterviewError:
        # The directory itself is refused, a link where a directory belongs.
        # That is a screen, the same as any other unusable configuration.
        entries = []
        engine = replace(engine, refusal="interviews-not-a-directory",
                         refusal_names="")
    return _render(request, "interview_hub.html", engine=engine,
                   entries=entries)


@router.post("/interview")
def begin(request: Request):
    engine = _engine(request)
    if not engine.ready:
        # This one is a plain form navigation, so an error body would be the
        # whole page, in whatever language it was written in here. The hub
        # already says what is missing, out of the language pack.
        return RedirectResponse("/interview", status_code=303)
    status = request.app.state.instance.status()
    try:
        conversation = interview.start(
            request.app.state.instance.root,
            skill=interview.STEP_SKILL, sections=interview.STEP_SECTIONS,
            interface_language=status.interface_language if status else "en",
            output_language=status.output_language_default if status else "en",
            provider=engine.settings.provider, model=engine.settings.model)
    except interview.InterviewError:
        # The directory is refused, so there is nowhere to start one. The hub
        # says why, out of the pack.
        return RedirectResponse("/interview", status_code=303)
    return RedirectResponse(f"/interview/{conversation.id}", status_code=303)


#: Notices a redirect may carry back to the screen. A whitelist, because the
#: query string is anybody's to write and an unknown value must render as
#: nothing rather than reach the string table.
NOTICES = ("sheet-changed", "turn-running")


def panel(conversation) -> dict:
    """The traceability panel, computed now and never read off disk.

    One function for the screen and for the frame that lands mid stream, so
    the browser is painting the same verdicts a reload would show. Nothing
    here is stored: `references/instance.md` says why, and it is the whole
    reason this panel can be trusted after somebody edits their transcript.

    Nothing here is passed through `redact` either, and that is a decision
    rather than an oversight. `redact` strikes the values of secret named
    variables out of this process's environment, and the two things that
    carry them are a subprocess's output and a provider's error body, which
    are both redacted where they arrive. A draft is written by a model that
    cannot reach the environment: `.env` is refused by the read tool by name.
    Redacting here would guard a path that does not exist, and it would
    mangle a post that legitimately quotes a value somebody chose to publish.
    """
    draft = conversation.draft
    if draft is None:
        return {}
    verdicts = interview.checked(conversation)
    #: The anchors whose quote is nowhere in the transcript, by identity.
    invented = {verdict.anchor for verdict in verdicts
                if verdict.status == "fabricated"}
    painted = anchors.lines(draft.body, draft.anchors)
    counts = {state: sum(1 for verdict in verdicts
                         if verdict.status == state)
              for state in ("anchored", "fabricated", "dangling")}
    counts["unanchored"] = sum(1 for row in painted for piece in row
                               if not piece.covered)
    return {
        "body": draft.body,
        "written": draft.written,
        "problems": list(draft.problems),
        "lines": [[{"text": piece.text, "covered": piece.covered,
                    "status": _claim(piece, invented)}
                   for piece in row] for row in painted],
        "verdicts": [{"post": verdict.anchor.fragment,
                      "said": verdict.anchor.quote,
                      "status": verdict.status} for verdict in verdicts],
        "counts": counts,
    }


def _claim(piece, invented) -> str:
    """What to paint one claim of the post as.

    A claim backed by a fabricated quote is worse off than a bare one, and a
    body that showed it clean would hide the loudest of the three alarms
    behind the quietest reading of `uncovered`. So a fabricated backer wins
    over every other, and only a claim really backed comes out anchored.

    `invented` holds anchors, not positions in a verdict list: the claim and
    the verdict are computed by two different functions, and an index that
    has to stay in step across that distance eventually will not.
    """
    if not piece.covered:
        return "unanchored"
    if any(anchor in invented for anchor in piece.by):
        return "fabricated"
    return "anchored"


def _screen(request: Request, conversation, **extra):
    """The interview screen. Built here rather than in the handler because
    three of them render it: the plain visit, and the two form posts that
    have something to show without changing anything."""
    instance = request.app.state.instance
    try:
        bank = instance.ideas()
    except InstanceError:
        bank = None
    asked = request.query_params.get("notice", "")
    fields = dict(conversation=conversation,
                  moments=interview.timeline(conversation),
                  spent=conversation.spent,
                  awaiting=_awaiting_answer(conversation),
                  notice=asked if asked in NOTICES else "",
                  engine=_engine(request), bank=bank,
                  trace=panel(conversation), findings="",
                  lint_failed=False,
                  strings=_frame_strings(request.app.state.t))
    fields.update(extra)
    return _render(request, "interview.html", **fields)


@router.get("/interview/{interview_id}")
def screen(request: Request, interview_id: str):
    return _screen(request, _conversation(request, interview_id))


@router.post("/interview/{interview_id}/discard")
def discard(request: Request, interview_id: str):
    try:
        interview.discard(request.app.state.instance.root, interview_id)
    except interview.InterviewError:
        # Already gone is the state that was asked for, so this is not a
        # failure worth a page of its own.
        return RedirectResponse("/interview", status_code=303)
    except OSError:
        # It is still there, which the hub will show. A raw error body on a
        # plain form navigation would say less and read worse.
        return RedirectResponse("/interview", status_code=303)
    forget_lock(request.app, interview_id)
    return RedirectResponse("/interview", status_code=303)


@router.post("/interview/{interview_id}/sheet/approve")
def approve_sheet(request: Request, interview_id: str, sheet: str = Form("")):
    """The person's click, the only writer of `approved`.

    Taken under the turn lock: a running turn is saving this conversation,
    and an approval written beside it would be overwritten by the turn's next
    save, an approval lost in silence. Losing the lock loses nothing: the
    screen comes back showing the sheet still proposed, and the click can
    happen again once the turn is done.

    `sheet` is the digest of the sheet as the page showed it. The disk can be
    newer than the screen, one tab or two, and an approval that lands on a
    replacement the person never read would put their signature under the
    model's unreviewed text. A mismatch approves nothing and the screen says
    why, showing what is actually there now.
    """
    root = request.app.state.instance.root
    try:
        interview.load(root, interview_id)
    except interview.InterviewError:
        # Discarded from another tab. The hub is the screen that says so.
        return RedirectResponse("/interview", status_code=303)
    lock = lock_for(request.app, interview_id)
    if lock.acquire(blocking=False):
        try:
            try:
                conversation = interview.load(root, interview_id)
                if interview.approve(conversation, sheet):
                    interview.save(root, conversation)
            except interview.SheetChanged:
                # The code travels in the URL, the sentence lives in the pack.
                return RedirectResponse(
                    f"/interview/{interview_id}?notice=sheet-changed",
                    status_code=303)
            except interview.InterviewError:
                # No sheet, or a closed interview: the screen already shows
                # what is actually there, and a plain form navigation gets a
                # screen, not a sentence written here.
                pass
        finally:
            lock.release()
        return RedirectResponse(f"/interview/{interview_id}", status_code=303)
    # The lock lost to a running turn. Approving nothing is right; saying
    # nothing about it would send the person a page that looks identical to
    # the one they clicked, minus their click.
    return RedirectResponse(f"/interview/{interview_id}?notice=turn-running",
                            status_code=303)


@router.post("/interview/{interview_id}/sheet/propose")
def propose_sheet(request: Request, interview_id: str):
    """The person asks for the sheet, and the turn requires the tool.

    This is the mechanism that replaces asking a model nicely. A weak model
    reads `The validation sheet` and answers it in prose, which fires nothing:
    no proposal, no panel, no approval, and a person left believing the guard
    ran. Requiring the tool for this one turn leaves it no prose to write, and
    it stays the person's decision to ask, because they are the one who knows
    the interview has enough material in it.
    """
    return _start(request, interview_id, require=SHEET_TOOL)


@router.post("/interview/{interview_id}/draft")
def draft(request: Request, interview_id: str):
    """Write the post. Refused until the sheet is signed, which is the
    sentence `linkedin-post` opens the sheet with, made mechanical."""
    return _start(request, interview_id, require=DRAFT_TOOL, drafting=True)


@router.post("/interview/{interview_id}/draft/lint")
def lint(request: Request, interview_id: str):
    """The deterministic pass, run by the person on the draft in front of
    them. It reports and they decide, exactly as the skill says, so nothing
    here writes anything: a POST because it starts a subprocess, and a plain
    page back because the findings are longer than a query string.
    """
    conversation = _conversation(request, interview_id)
    if conversation.draft is None:
        return RedirectResponse(f"/interview/{interview_id}", status_code=303)
    try:
        findings = lint_body(request.app.state.bundle,
                             request.app.state.instance.root,
                             conversation.draft.body,
                             conversation.output_language,
                             environ=request.app.state.environ)
    except ToolRefused as refusal:
        # A refusal from lint.py is written for the model, in English, and it
        # would land on a French screen as it is. So the pack says what kind
        # of thing this is and the tool's own words follow it, named as the
        # engine failing rather than as a finding about somebody's post.
        return _screen(request, conversation, lint_failed=True,
                       findings=redact(str(refusal),
                                       request.app.state.environ))
    return _screen(request, conversation, findings=findings)


@router.post("/interview/{interview_id}/turn")
def turn(request: Request, interview_id: str, text: str = Form("")):
    """Validate here, write inside the stream.

    Nothing is committed on this side of the `StreamingResponse`, and the lock
    is not taken here either. A body that is never read closes a generator that
    never started, and a generator that never started does not run its
    `finally`: a lock acquired here would be held for the life of the process
    and that interview would answer 409 forever. So this end only refuses what
    it can refuse with a status code, and the turn itself takes the lock.
    """
    engine = _engine(request)
    if not engine.ready:
        raise HTTPException(status_code=503, detail="not-configured")
    conversation = _conversation(request, interview_id)
    if conversation.state != interview.OPEN:
        raise HTTPException(status_code=409, detail="closed")
    if interview.sheet_approved(conversation):
        # The skill's rule made mechanical: an approved sheet ends the
        # questions. Drafting reads the sheet; it does not reopen the turn.
        raise HTTPException(status_code=409, detail="sheet-approved")
    if not text.strip() and not _awaiting_answer(conversation):
        raise HTTPException(status_code=422, detail="nothing-to-send")
    lock = lock_for(request.app, interview_id)
    if lock.locked():
        # A peek, not the decision. The generator takes the lock for real, so
        # losing this race costs a frame rather than a corrupted conversation.
        raise HTTPException(status_code=409, detail="turn-running")

    return StreamingResponse(
        _run(request, engine, interview_id, text, lock),
        media_type="text/event-stream",
        headers={"cache-control": "no-store", "x-accel-buffering": "no"})


def _start(request: Request, interview_id: str, *, require: str = "",
           drafting: bool = False):
    """Refuse what a status code can refuse, then stream.

    Same reasoning as `turn` above and for the same reason: nothing is
    committed on this side of the `StreamingResponse`, and the lock is taken
    inside the generator, never here.
    """
    engine = _engine(request)
    if not engine.ready:
        raise HTTPException(status_code=503, detail="not-configured")
    conversation = _conversation(request, interview_id)
    if conversation.state != interview.OPEN:
        raise HTTPException(status_code=409, detail="closed")
    if drafting and not interview.sheet_approved(conversation):
        raise HTTPException(status_code=409, detail="sheet-not-approved")
    if not drafting and interview.sheet_approved(conversation):
        raise HTTPException(status_code=409, detail="sheet-approved")
    if not drafting and not conversation.messages:
        # A sheet asked for before anybody said anything is a sheet the model
        # has to invent, and inventing it is the failure the sheet exists to
        # catch.
        raise HTTPException(status_code=422, detail="nothing-to-send")
    lock = lock_for(request.app, interview_id)
    if lock.locked():
        raise HTTPException(status_code=409, detail="turn-running")
    return StreamingResponse(
        _run(request, engine, interview_id, "", lock, require=require,
             drafting=drafting),
        media_type="text/event-stream",
        headers={"cache-control": "no-store", "x-accel-buffering": "no"})


def _awaiting_answer(conversation) -> bool:
    """Whether the model still owes a reply: the browser was closed before the
    answer arrived, and reopening the screen continues rather than repeats."""
    return bool(conversation.messages) and \
        conversation.messages[-1].get("role") == "user"


# -------------------------------------------------------------------- the wire

def _running(so_far, model: str, this_turn):
    """What has been spent, or None once any turn had no price."""
    if so_far is None:
        return None
    cost = price(model, this_turn)
    return None if cost is None else so_far + cost


def _sheet_fields(sheet) -> dict:
    """What the browser fills the sheet panel with. Values only: the labels
    are on the page already, rendered from the language pack."""
    return dict(state=sheet.state, angle=sheet.angle,
                elements=list(sheet.elements), moment=sheet.moment,
                conviction=sheet.conviction,
                first_lines=list(sheet.first_lines),
                digest=sheet.digest())


def _frame(kind: str, **fields) -> str:
    return "data: " + json.dumps(dict(kind=kind, **fields),
                                 ensure_ascii=False) + "\n\n"


def _run(request: Request, engine: Engine, interview_id: str, text: str, lock,
         *, require: str = "", drafting: bool = False):
    """The loop, one frame at a time, with the disk kept ahead of the screen.

    `drafting` swaps what the turn is about without swapping the machinery
    around it. Two things change and both are load bearing. The step becomes
    the skill's writing sections, and the message list becomes one fresh
    message built from `interview.material` instead of the interview's own:
    a message the engine appended to that list would be credited to the
    person by `timeline`, and `timeline` is the anchoring source. The engine
    does not get to put words in somebody's mouth and then quote them.
    """
    root = request.app.state.instance.root
    if not lock.acquire(blocking=False):
        yield _frame("error", code="turn-running")
        return
    agent = None
    conversation = None
    base = Usage()
    base_spent = 0.0
    #: What this turn has reported but the loop has not folded in yet. The
    #: loop adds a turn's figures to `Agent.usage` only when that turn ends, so
    #: a turn abandoned while its answer is still streaming would contribute
    #: nothing at all: the tokens are spent, the provider bills them, and
    #: dropping them silently is the thing this file says out loud is worse
    #: than showing no figure. A browser closing mid turn is the normal case.
    pending = Usage()

    def keep():
        if conversation is None:
            return
        if agent is not None:
            spent_now = agent.usage + pending
            conversation.usage = base + spent_now
            # Priced at the model that ran this turn, and added to what the
            # earlier turns cost at theirs. Somebody who changes VERBATIM_MODEL
            # between two turns does not retroactively re-price the first one,
            # and one unpriced turn takes the whole figure away rather than
            # quietly dropping itself out of it.
            conversation.spent = _running(base_spent, conversation.model,
                                          spent_now)
        interview.save(root, conversation)

    try:
        # Reloaded under the lock: the copy the handler validated is only as
        # fresh as the moment it lost the race for this lock.
        conversation = interview.load(root, interview_id)
        if conversation.state != interview.OPEN:
            yield _frame("error", code="closed")
            return
        if not drafting and interview.sheet_approved(conversation):
            # Re-checked under the lock, like `closed` above: the copy the
            # handler refused on is only as fresh as losing the race left it.
            yield _frame("error", code="sheet-approved")
            return
        if drafting and not interview.sheet_approved(conversation):
            # Re-checked under the lock, like `closed` above.
            yield _frame("error", code="sheet-not-approved")
            return
        if text.strip():
            interview.say(conversation, text)
        conversation.provider = engine.settings.provider
        conversation.model = engine.settings.model
        base = conversation.usage
        base_spent = conversation.spent
        sections = interview.DRAFT_SECTIONS if drafting else None
        # What somebody typed is on disk before a single token is spent on it,
        # and the frame that says so is the seam the screen needs: before it,
        # a refusal means nothing was written and the words stay in the box;
        # after it, every failure is a failure of a turn that really happened.
        keep()
        yield _frame("accepted")

        block = _block(request, conversation, sections=sections)
        tools = instance_tools(root, request.app.state.bundle,
                               environ=request.app.state.environ)
        # Bound to this conversation, not to the instance: what they write
        # lands on the object the turn is saving, so the next `keep` writes it.
        tools.append(draft_tool(
            lambda arguments: interview.write(conversation, arguments))
            if drafting else sheet_tool(
            lambda arguments: interview.propose(conversation, arguments)))
        agent = Agent(engine.settings, tools,
                      transport=request.app.state.transport or http_transport())
        # A drafting turn is a fresh request, so this list is thrown away
        # with the generator. Nothing is lost by that: what a draft leaves
        # behind is the `draft` key, and what a revision starts from is the
        # material, every time.
        messages = ([{"role": "user",
                      "content": [{"type": "text",
                                   "text": interview.material(conversation)}]}]
                    if drafting else conversation.messages)
        for step in agent.run(block.text, messages, require=require):
            if step.kind == "text":
                yield _frame("text", text=step.text)
                continue
            if step.kind == "usage":
                pending = step.usage
                live = base + agent.usage + pending
                yield _frame("usage", input_tokens=live.input_tokens,
                             output_tokens=live.output_tokens,
                             price=_running(base_spent, conversation.model,
                                            agent.usage + pending))
                continue
            # Everything below this line changed the conversation. It reaches
            # disk before it reaches the screen, never the other way round.
            # Reaching here also means the turn ended, so the loop has folded
            # its figures into `Agent.usage` and nothing is pending any more.
            pending = Usage()
            keep()
            if step.kind == "tool_call":
                yield _frame("tool_call", id=step.call.id, name=step.call.name,
                             arguments=step.call.arguments)
            elif step.kind == "tool_result":
                yield _frame("tool_result", id=step.call.id,
                             name=step.call.name, result=step.result,
                             is_error=step.is_error)
                if step.call.name == SHEET_TOOL and not step.is_error:
                    # Already on disk: the save above ran after the tool did.
                    yield _frame("sheet", **_sheet_fields(conversation.sheet))
                elif step.call.name == DRAFT_TOOL and not step.is_error:
                    yield _frame("draft", **panel(conversation))
            elif step.kind == "stop":
                # Whether the model still owes a reply is read off the
                # conversation, never inferred from the reason it stopped: a
                # turn that produced no content stops on `end_turn` and leaves
                # the person's own message last, still waiting.
                yield _frame("stop", stop=step.stop or "truncated",
                             owing=(not drafting
                                    and _awaiting_answer(conversation)))
            elif step.kind == "ceiling":
                yield _frame("ceiling", turns=agent.max_turns,
                             owing=(not drafting
                                    and _awaiting_answer(conversation)))
        if drafting and _prose_draft(conversation, messages):
            # A runtime that ignored the required tool answered in prose, and
            # the answer carried an anchors block. Local runtimes do exactly
            # this, so it is a path the multi provider claim has to hold, and
            # `references/instance.md` says it is degraded and shows it.
            keep()
            yield _frame("draft", **panel(conversation))
    except (AgentError, ProviderError) as failure:
        # The provider's own words, redacted the same way a subprocess answer
        # is: a gateway that echoes an Authorization header into a debug body
        # would otherwise put it on the page. The headers left with the first
        # byte, so a failure cannot change the status code any more: it becomes
        # a frame or it becomes silence.
        yield _frame("error", technical=redact(str(failure),
                                               request.app.state.environ))
    except interview.InterviewError:
        # The interview went away underneath its own turn, discarded from
        # another tab. Its message names a path, so the code travels instead.
        yield _frame("error", code="gone")
    except SkillError:
        yield _frame("error", code="bundle-broken")
    except Exception as failure:
        yield _frame("error", code="engine-failed",
                     technical=type(failure).__name__)
    finally:
        try:
            keep()
        except Exception:
            # The interview was discarded while its own turn was running. There
            # is nothing left to write to and nothing left to lose; raising
            # here would only tear the response down on the way out.
            pass
        finally:
            lock.release()


def _prose_draft(conversation, messages) -> bool:
    """Read a draft out of an answer that ignored the tool, if there is one.

    Only ever tried once the turn is over and nothing was offered through
    `propose_draft`, and only when the answer really carried an `ANCHORS`
    block: prose with no block is somebody's model talking, not a post, and
    storing it as one would put the engine's chatter in front of the person
    with a traceability panel drawn around it.

    Whatever could not be read travels with the draft rather than into
    silence, which is the only thing that makes this path honest.
    """
    if conversation.draft is not None:
        return False
    said = ""
    for message in messages:
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, list):
            said = "\n".join(block.get("text", "") for block in content
                              if isinstance(block, dict)
                              and block.get("type") == "text") or said
    out = anchors.split_output(said)
    if not out.block or not out.draft.strip():
        return False
    try:
        interview.write(
            conversation,
            {"body": out.draft,
             "anchors": [{"post": anchor.fragment, "said": anchor.quote}
                         for anchor in out.anchors]},
            problems=out.problems)
    except interview.InterviewError:
        # The sheet went unapproved underneath, or the block held nothing a
        # draft can be made of. Neither is worth taking the turn down for.
        return False
    return True


#: The strings the browser needs to label frames it receives. They live in the
#: language pack like every other string; the page carries them across so no
#: user facing text is ever written in a script file.
FRAME_KEYS = (
    "interview.said", "interview.asked", "interview.tool_call",
    "interview.tool_result", "interview.tool_failed", "interview.thinking",
    "interview.stop_truncated", "interview.stop_max_tokens",
    "interview.stop_other", "interview.stop_tool_use",
    "interview.stop_refusal",
    "interview.stop_unknown", "interview.ceiling", "interview.error",
    "interview.error_turn_running", "interview.error_closed",
    "interview.error_not_configured", "interview.error_nothing_to_send",
    "interview.error_gone", "interview.error_engine_failed",
    "interview.error_bundle_broken", "interview.error_sheet_approved",
    "interview.error_sheet_not_approved",
    "interview.error_unknown", "interview.tokens", "interview.spent",
)


def _frame_strings(t) -> str:
    """Serialised for a script block, so a `<` in a pack cannot end it early.
    The placeholders are left unfilled on purpose: the browser fills them,
    because it is the one that knows the numbers."""
    table = {key.split(".", 1)[1]: t(key) for key in FRAME_KEYS}
    return json.dumps(table, ensure_ascii=False).replace("<", "\\u003c")
