"""The cold screens: overview, profile, ideas, posts, corpus.

No model, no network, no state outside the instance directory. Reading is
free; the only writes are profile.md (whole file, verbatim) and the
measurement lines of a post's front matter.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..instance import InstanceError

router = APIRouter()


def _ctx(request: Request, **extra):
    instance = request.app.state.instance
    context = {
        "request": request,
        "gaps": instance.conformance(),
        "status": instance.status(),
        "pack_missing": len(request.app.state.t.missing),
    }
    context.update(extra)
    return context


def _render(request: Request, template: str, **extra):
    return request.app.state.templates.TemplateResponse(
        request, template, _ctx(request, **extra))


def _int_or_none(raw: str):
    raw = raw.strip()
    if raw == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"not a count: {raw!r}")
    if value < 0:
        raise HTTPException(status_code=422, detail=f"not a count: {raw!r}")
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


@router.get("/posts/{name}")
def post_detail(request: Request, name: str, saved: int = 0):
    instance = request.app.state.instance
    matches = [p for p in instance.posts() if p.filename == name]
    if not matches:
        raise HTTPException(status_code=404)
    try:
        body = instance.post_body(name)
    except InstanceError:
        raise HTTPException(status_code=404)
    return _render(request, "post.html", post=matches[0], body=body, saved=saved)


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
    except InstanceError:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/posts/{name}?saved=1", status_code=303)


@router.get("/corpus")
def corpus(request: Request):
    return _render(request, "corpus.html", names=request.app.state.instance.corpus())


@router.get("/corpus/{name}")
def corpus_file(request: Request, name: str):
    try:
        text = request.app.state.instance.corpus_text(name)
    except InstanceError:
        raise HTTPException(status_code=404)
    return _render(request, "corpus_file.html", name=name, text=text)
