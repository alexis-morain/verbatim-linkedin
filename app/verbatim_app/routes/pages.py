"""The cold screens: overview, profile, ideas, posts, corpus.

No model, no network, no state outside the instance directory. Reading is
free; the only writes are profile.md (whole file, verbatim) and the
measurement lines of a post's front matter. Publishing is the one screen
that can leave this machine, and it has its own module for that reason;
`post_screen` below is shared with it, so both land on the same page.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import render as _render
from ..archive import notes_only, post_only
from ..instance import STATES, InstanceError, UnreadableError

router = APIRouter()


def _int_or_none(raw: str):
    raw = raw.strip()
    if raw == "":
        return None
    # A machine code, not a sentence. This screen is a plain form post, so a
    # detail written here would be rendered as the whole page, in English,
    # whatever language the person reads.
    try:
        value = int(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail="not-a-count")
    if value < 0:
        raise HTTPException(status_code=422, detail="not-a-count")
    return value


@router.get("/")
def overview(request: Request):
    instance = request.app.state.instance
    try:
        bank = instance.ideas()
    except InstanceError:
        bank = None
    return _render(
        request, "overview.html",
        next_session=bank.next_session if bank else "",
        counter=instance.pillar_counter(),
        posts=instance.posts()[:5],
    )


@router.get("/profile")
def profile(request: Request, saved: int = 0):
    instance = request.app.state.instance
    try:
        text = instance.read("profile.md")
    except InstanceError:
        text = ""
    return _render(request, "profile.html", text=text, saved=saved)


@router.post("/profile")
def save_profile(request: Request, content: str = Form(...)):
    request.app.state.instance.write("profile.md", content)
    return RedirectResponse("/profile?saved=1", status_code=303)


@router.get("/ideas")
def ideas(request: Request):
    instance = request.app.state.instance
    try:
        bank = instance.ideas()
    except InstanceError:
        bank = None
    sections: dict = {}
    if bank:
        for angle in bank.angles:
            sections.setdefault(angle.section, []).append(angle)
    return _render(request, "ideas.html", bank=bank, sections=sections)


@router.get("/posts")
def posts(request: Request):
    return _render(request, "posts.html", posts=request.app.state.instance.posts())


def post_screen(request: Request, name: str, **extra):
    """One post's screen, built the same way whichever route lands on it.

    Shared with the publishing routes, which come back to this page carrying
    a plan or what a tier answered. Every key a template branch reads is
    defaulted here rather than in the template: a screen whose section
    appears only because another route happened to pass a variable is a
    screen nobody can reason about.
    """
    instance = request.app.state.instance
    matches = [p for p in instance.posts() if p.filename == name]
    if not matches:
        raise HTTPException(status_code=404)
    # A file that is there and will not read is a file to repair, not a file
    # that is missing: 404 would send somebody looking for the wrong thing,
    # and the row that links here is rendered whether or not it reads.
    #
    # Cut at the seam here rather than on the screen, and by the same two
    # functions the publishing step uses. The post is what a tier would
    # receive, byte for byte, which is what makes the copy button on this
    # page the `copy` tier brought to the screen rather than a second idea of
    # where a post stops.
    try:
        raw = instance.post_body(name)
        post_text, notes, unreadable = post_only(raw), notes_only(raw), ""
    except UnreadableError as broken:
        post_text, notes, unreadable = "", "", str(broken)
    except InstanceError:
        raise HTTPException(status_code=404)
    values = dict(post=matches[0], post_text=post_text, notes=notes,
                  unreadable=unreadable, saved=0,
                  plan="", shown="", token="", publish_when="",
                  publish_problem="",
                  plan_changed=False, sent="", publish_words="",
                  state_problem="", states=STATES)
    values.update(extra)
    return _render(request, "post.html", **values)


@router.get("/posts/{name}")
def post_detail(request: Request, name: str, saved: int = 0):
    return post_screen(request, name, saved=saved)


@router.post("/posts/{name}/measure")
def save_measure(request: Request, name: str,
                 measured: str = Form(""),
                 inbound_connections: str = Form(""),
                 inbound_dms: str = Form(""),
                 meeting_mentions: str = Form(""),
                 note: str = Form("")):
    try:
        request.app.state.instance.update_post_measurement(
            name,
            measured=measured.strip() or None,
            inbound_connections=_int_or_none(inbound_connections),
            inbound_dms=_int_or_none(inbound_dms),
            meeting_mentions=_int_or_none(meeting_mentions),
            note=note.strip() or None,
        )
    except UnreadableError:
        # Nothing was written, and saying so beats a page of English.
        return RedirectResponse(f"/posts/{name}", status_code=303)
    except InstanceError:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/posts/{name}?saved=1", status_code=303)


@router.get("/corpus")
def corpus(request: Request):
    return _render(request, "corpus.html", names=request.app.state.instance.corpus())


@router.get("/corpus/{name}")
def corpus_file(request: Request, name: str):
    # corpus/ is where somebody's older writing lands, so a file exported from
    # another tool in another encoding is the expected accident, not the exotic
    # one. The index links every name it globs, so this is where that lands.
    try:
        text, unreadable = request.app.state.instance.corpus_text(name), ""
    except UnreadableError as broken:
        text, unreadable = "", str(broken)
    except InstanceError:
        raise HTTPException(status_code=404)
    return _render(request, "corpus_file.html", name=name, text=text,
                   unreadable=unreadable)
