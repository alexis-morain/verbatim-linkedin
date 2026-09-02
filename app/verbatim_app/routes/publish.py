"""The one screen in this app that can leave the machine.

Everything else here reads and writes one directory. This module runs
`lib/publish.py` with `--confirm`, and on the `command` tier that is a
program of the person's choosing receiving their post on its stdin. So the
whole design is two clicks with a reading between them.

**Plan first, always.** The plan names the tier and the target channel, and
it is printed by the script rather than rebuilt here: a second rendering of
the target would be a second thing to keep true, and the one it is checked
against is the one that would be wrong. This project has already published
three test posts to a company page, and a personal profile and a company
page are two lines in a config file.

**The confirm carries a digest of what was on the screen**, the plan and the
post together. Between reading a plan and clicking, the environment can move,
another tab can rewrite the file, a shell can export a different channel.
Confirming against a digest means the send either matches what somebody read
or does not happen, and a mismatch shows the plan as it stands now instead of
sending against a target nobody looked at. Same shape as approving a
validation sheet, and for the same reason.

**What goes to a tier is the post, never the file.** A post file carries the
session notes under `archive.NOTES_MARKER`: the sheet, every anchor the
engine claimed, and the interview sentence behind each one. `post_only` cuts
there. Nothing here builds a payload either: `publish.to_scheduler_html`
does, inside the script, which is where the empty paragraph separators and
the NFC normalisation live.

**One plan, one confirm, and only the last plan drawn can be confirmed.** The
digest says what is being sent, never how many times, and a double click, a
reloaded POST, a second tab or the back button would each send the same post
twice. So a send takes a lock over the post, the way a turn takes one over an
interview, and every plan carries a token that is spent the moment it is
confirmed and retired the moment another plan is drawn for that post.

The token is what the digest cannot be. A digest is a pure function of the
plan and the post, so drawing the same plan twice produces the same digest,
and refusing a digest already seen would refuse the post for the life of the
process, with nothing the person could do about it. Found in review: the
first version of this did exactly that, and both recovery sentences it
pointed at were false. A token is minted per plan, so redrawing really is the
way back, and it is spent before the send rather than after, because the
outcome nobody can read is a dispatch that failed.

**No GET reaches any of this**, like everywhere else in this app, and here
the rule is at its sharpest: a cross origin no-cors GET carries no Origin,
and a GET that publishes somebody's post is reachable from any tab they have
open.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from .pages import post_screen
from ..agent import ToolRefused
from ..archive import post_only
from ..instance import STATES, InstanceError, UnreadableError
from ..shown import shown as shown_digest
from ..tools import ToolUnfinished, publish_plan_text, publish_send

router = APIRouter()

_registry = threading.Lock()


def lock_for(app, name: str) -> threading.Lock:
    """One lock per post file. Same shape as the interview turn lock, and for
    a sharper reason: what sits behind that one is somebody's API budget, and
    what sits behind this one is a post in a feed."""
    with _registry:
        return app.state.publish_locks.setdefault(name, threading.Lock())


def mint(app, name: str) -> str:
    """A token for one plan, good for one confirm, and it retires the token of
    any earlier plan for the same post.

    One live token per post, kept by storing them the post's way round rather
    than the token's. Handing out a second one without retiring the first is
    how the guard came back apart in review: the same plan redrawn has the
    same digest, so two tokens meant two confirms that both passed, and a
    person with the post open in two tabs, or one who read the plan twice and
    then used the back button, published twice. It also bounds the store to
    the posts somebody has planned rather than to every plan ever drawn.
    """
    token = secrets.token_hex(8)
    with _registry:
        app.state.publish_tokens[name] = token
    return token


def spend(app, token: str, name: str) -> bool:
    """Take the token, once. False when it was never minted, was minted for
    another post, or has been retired by a later plan or an earlier confirm."""
    with _registry:
        if not token or app.state.publish_tokens.get(name) != token:
            return False
        del app.state.publish_tokens[name]
        return True

#: The shapes a scheduled time may arrive in. `datetime-local` gives the
#: first, a person pasting from another tool gives one of the others. Checked
#: before the value becomes an argv element: `publish.py` reads `--when` with
#: argparse, so an unchecked value beginning with a dash is read as an option
#: rather than as a time, and the option it would be read as is `--confirm`.
#:
#: The two with an offset are here because a naked time says nothing about
#: which clock it is in, and the tier that reads it may well pick UTC. The
#: engine does not add one: a guessed offset is a post an hour out, silently.
WHEN_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M:%S%z")


def _when(raw: str) -> str:
    when = raw.strip()
    if not when:
        return ""
    for shape in WHEN_FORMATS:
        try:
            datetime.strptime(when, shape)
        except ValueError:
            continue
        return when
    raise ValueError("bad-when")


def _shown(plan: str, post: str) -> str:
    """What the person had in front of them when they clicked: the plan, and
    the post the plan is about. Both, because the plan quotes the first line
    and the length rather than the whole post, and the whole post is what
    would be sent."""
    return shown_digest(plan, post)


def _publishable(request: Request, name: str) -> str:
    """The post as it would go out, or a 404. The measurement screen already
    renders a file that will not decode; a tier is not offered one."""
    try:
        return post_only(request.app.state.instance.post_body(name))
    except InstanceError:
        # `UnreadableError` included: the publish section is not on the screen
        # for such a file, so arriving here is a stale form or a hand written
        # request, and neither is a state to explain.
        raise HTTPException(status_code=404) from None


@router.post("/posts/{name}/publish/plan")
def plan(request: Request, name: str, when: str = Form("")):
    """What publishing this post would do. Costs nothing, sends nothing."""
    post = _publishable(request, name)
    try:
        moment = _when(when)
    except ValueError:
        return post_screen(request, name, publish_when=when,
                           publish_problem="bad-when")
    try:
        text = publish_plan_text(request.app.state.bundle,
                                 request.app.state.instance.root, post,
                                 when=moment or None,
                                 environ=request.app.state.environ)
    except ToolRefused as refusal:
        # A tier that is not usable as configured, or a post the platform
        # would refuse. The script's own words, in English, framed by the pack
        # as the engine talking rather than as a finding about the post.
        return post_screen(request, name, publish_when=moment,
                           publish_problem="refused", publish_words=str(refusal))
    return post_screen(request, name, plan=text, publish_when=moment,
                       shown=_shown(text, post),
                       token=mint(request.app, name))


@router.post("/posts/{name}/publish")
def send(request: Request, name: str, when: str = Form(""),
         shown: str = Form(""), token: str = Form("")):
    """Publish, for real. The only caller of `publish_send` in this app.

    The plan is drawn again here rather than trusted from the form. A digest
    is only worth what it is compared against, and comparing a form field to
    another form field would check that nothing was edited in a browser, which
    is not the thing that goes wrong.
    """
    post = _publishable(request, name)
    try:
        moment = _when(when)
    except ValueError:
        return post_screen(request, name, publish_when=when,
                           publish_problem="bad-when")
    bundle, root = request.app.state.bundle, request.app.state.instance.root
    environ = request.app.state.environ
    try:
        current = publish_plan_text(bundle, root, post, when=moment or None,
                                    environ=environ)
    except ToolRefused as refusal:
        return post_screen(request, name, publish_when=moment,
                           publish_problem="refused", publish_words=str(refusal))
    if not shown or shown != _shown(current, post):
        # Nothing was sent. The plan below is the one that holds now, which is
        # the whole point: what moved is what the person has to read again.
        return post_screen(request, name, plan=current, publish_when=moment,
                           shown=_shown(current, post), plan_changed=True,
                           token=mint(request.app, name))
    lock = lock_for(request.app, name)
    if not lock.acquire(blocking=False):
        # A send is already running for this post. Two of them are two posts.
        return post_screen(request, name, publish_when=moment,
                           publish_problem="running")
    try:
        if not spend(request.app, token, name):
            # A reloaded POST, or a second click on a button that was already
            # pressed. Drawing the plan again mints another token, which is
            # what the sentence on the screen tells them to do.
            return post_screen(request, name, publish_when=moment,
                               publish_problem="spent")
        try:
            done = publish_send(bundle, root, post, when=moment or None,
                                environ=environ)
        except ToolUnfinished as unknown:
            # Its own screen, and the one refusal that must not say nothing
            # was sent: something reached the tier and nothing here knows what
            # it did.
            return post_screen(request, name, publish_when=moment,
                               publish_problem="unfinished",
                               publish_words=str(unknown))
        except ToolRefused as refusal:
            # Nothing was dispatched, so this really is a refusal and the
            # sentence for it is true.
            return post_screen(request, name, publish_when=moment,
                               publish_problem="refused",
                               publish_words=str(refusal))
    finally:
        lock.release()
    # No state is written here. What a tier accepted is not what a person
    # published: the copy tier printed a post nobody has pasted yet, and the
    # postiz tier built a payload the agent still has to send. The state form
    # below is the person saying what actually happened, which is the same
    # rule the archive form follows about everything it cannot derive.
    return post_screen(request, name, sent=done.payload, publish_words=done.note,
                       publish_when=moment)


@router.post("/posts/{name}/state")
def set_state(request: Request, name: str, state: str = Form(""),
              published_ref: str = Form("")):
    """Where a post is in its life, as the person states it.

    The only guard is the vocabulary, and it is here rather than in the
    instance because this form is the only thing that reaches that write:
    `posts/` is outside `WRITABLE` and no tool touches it.
    """
    if state.strip() not in STATES:
        return post_screen(request, name, state_problem="bad-state")
    try:
        request.app.state.instance.update_post_state(
            name, state=state.strip(), published_ref=published_ref.strip())
    except UnreadableError:
        # Nothing was written. Writing here would replace what is in the file
        # with what could be parsed out of it, which is the measurement
        # screen's rule and the same file.
        return RedirectResponse(f"/posts/{name}", status_code=303)
    except InstanceError:
        raise HTTPException(status_code=404) from None
    return RedirectResponse(f"/posts/{name}?saved=1", status_code=303)
