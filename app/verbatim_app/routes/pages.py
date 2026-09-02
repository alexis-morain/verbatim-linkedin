"""The cold screens: overview, profile, voice, pillars, page, ideas, posts,
corpus.

No model, no network, no state outside the instance directory. Reading is
free; the writes are one section of a contract file at a time, the Status
block of the profile, the angle bank, and the measurement lines of a post's
front matter. Publishing is the one screen that can leave this machine, and it
has its own module for that reason; `post_screen` below is shared with it, so
both land on the same page.

**A section is edited, not a file.** The whole file textarea is still there,
folded, because somebody moving a heading needs it. What it is not is the
normal way to change one paragraph: a form holding a whole profile saves
everything on the screen, including the half somebody had already fixed in
another tab.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import render as _render
from ..archive import notes_only, post_only
from ..instance import (
    LABELS, PILLARS, STATES, InstanceError, SectionChanged, UnreadableError,
    sections_of,
)

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


#: What a redirect may say went wrong, and the pack key that says it. A
#: whitelist, because the query string is anybody's to write: an unknown value
#: renders as nothing rather than reaching the string table.
PROBLEMS = {
    "section-changed": "profile.section_changed",
    "bad-language": "profile.bad_language",
    "bad-angle": "ideas.bad_angle",
    "angle-gone": "ideas.angle_gone",
}


def _document(request: Request, name: str):
    """One contract file, read once, in the three states a screen shows.

    Returns (text, sections, unreadable, missing). A file that is not there
    and a file that will not decode are two different screens: one is a file
    to create, the other a file to repair.
    """
    try:
        text = request.app.state.instance.read(name)
    except UnreadableError as broken:
        return "", [], str(broken), False
    except InstanceError:
        return "", [], "", True
    return text, sections_of(text), "", False


def _save_section(request: Request, name: str, back: str, heading: str,
                  shown: str, content: str):
    """One section written, or nothing written and the screen saying why."""
    try:
        request.app.state.instance.replace_section(
            name, heading, content, shown, today=date.today().isoformat())
    except SectionChanged:
        # The code travels in the URL, the sentence lives in the pack.
        return RedirectResponse(f"{back}?problem=section-changed",
                                status_code=303)
    except UnreadableError:
        # Nothing was written, and the screen already says the file will not
        # read. A page of English here would say less.
        return RedirectResponse(back, status_code=303)
    except InstanceError:
        # A heading this file does not have, or has twice: the screen offers
        # no form for either, so this is a stale form or a hand written
        # request, and neither is a state to explain.
        raise HTTPException(status_code=404)
    return RedirectResponse(f"{back}?saved=1", status_code=303)


@router.get("/profile")
def profile(request: Request, saved: int = 0, problem: str = ""):
    text, sections, unreadable, missing = _document(request, "profile.md")
    # The Status block has its own form above, so it is not offered twice.
    return _render(request, "profile.html", text=text,
                   sections=[s for s in sections if s.heading != "Status"],
                   unreadable=unreadable, missing=missing, saved=saved,
                   problem=PROBLEMS.get(problem, ""))


def _save_whole(request: Request, name: str, back: str, content: str):
    """The escape hatch: the file, whole, as typed.

    It is read before it is written. A file that will not decode is a file
    to repair, and the screen for it offers no form, so a save arriving here
    is a stale tab; the pack sentence on that screen promises nothing is
    written over it, and this is where the promise is kept.
    """
    instance = request.app.state.instance
    try:
        instance.read(name)
    except UnreadableError:
        return RedirectResponse(back, status_code=303)
    except InstanceError:
        # Not there yet. Writing it is creating it, which is what the person
        # asked for.
        pass
    instance.write(name, content)
    return RedirectResponse(f"{back}?saved=1", status_code=303)


@router.post("/profile")
def save_profile(request: Request, content: str = Form(...)):
    return _save_whole(request, "profile.md", "/profile", content)


@router.post("/voice")
def save_voice(request: Request, content: str = Form(...)):
    return _save_whole(request, "voice.md", "/voice", content)


@router.post("/pillars")
def save_pillars(request: Request, content: str = Form(...)):
    return _save_whole(request, "pillars.md", "/pillars", content)


@router.post("/profile/status")
def save_status(request: Request, interface_language: str = Form(""),
                output_language_default: str = Form("")):
    try:
        request.app.state.instance.update_status(
            interface_language=interface_language.strip(),
            output_language_default=output_language_default.strip(),
            today=date.today().isoformat())
    except UnreadableError:
        return RedirectResponse("/profile", status_code=303)
    except InstanceError:
        return RedirectResponse("/profile?problem=bad-language",
                                status_code=303)
    return RedirectResponse("/profile?saved=1", status_code=303)


@router.post("/profile/section")
def save_profile_section(request: Request, heading: str = Form(""),
                         shown: str = Form(""), content: str = Form("")):
    # The Status block has the form above and no section form, so a post
    # naming it is a stale form or a hand written request. Two writers for one
    # block is how the two start disagreeing about what a language code is.
    if heading.strip() == "Status":
        raise HTTPException(status_code=404)
    return _save_section(request, "profile.md", "/profile", heading, shown,
                         content)


def _sections_screen(request: Request, name: str, screen: str, saved: int,
                     problem: str):
    """The section editor, for a file that is nothing but sections."""
    text, sections, unreadable, missing = _document(request, name)
    return _render(request, "sections.html", name=name, screen=screen,
                   text=text, sections=sections, unreadable=unreadable,
                   missing=missing, saved=saved,
                   problem=PROBLEMS.get(problem, ""))


@router.get("/voice")
def voice(request: Request, saved: int = 0, problem: str = ""):
    return _sections_screen(request, "voice.md", "voice", saved, problem)


@router.post("/voice/section")
def save_voice_section(request: Request, heading: str = Form(""),
                       shown: str = Form(""), content: str = Form("")):
    return _save_section(request, "voice.md", "/voice", heading, shown, content)


@router.get("/pillars")
def pillars(request: Request, saved: int = 0, problem: str = ""):
    return _sections_screen(request, "pillars.md", "pillars", saved, problem)


@router.post("/pillars/section")
def save_pillars_section(request: Request, heading: str = Form(""),
                         shown: str = Form(""), content: str = Form("")):
    return _save_section(request, "pillars.md", "/pillars", heading, shown,
                         content)


@router.get("/page")
def page(request: Request):
    # Written by linkedin-profile and only by it, so this screen reads and
    # does not offer to write. Optional: an instance that never ran that skill
    # does not have the file, which is not a gap.
    text, _, unreadable, missing = _document(request, "linkedin-page.md")
    return _render(request, "page.html", text=text, unreadable=unreadable,
                   missing=missing)


def _pillar(raw: str) -> int:
    try:
        return int(raw.strip())
    except ValueError:
        # Not a pillar, which `add_angle` says better than a parse error does.
        return 0


def _angle_problem(request: Request, text: str) -> str:
    """Which of the two refusals to show for an angle that would not write.

    Asked of the bank rather than of the exception, because the person needs
    to know whether their own line was refused or whether the line they
    clicked is not there any more, and those want different next moves.
    """
    try:
        angles = request.app.state.instance.ideas().angles
    except InstanceError:
        return "angle-gone"
    return "bad-angle" if any(a.text == text for a in angles) else "angle-gone"


@router.get("/ideas")
def ideas(request: Request, saved: int = 0, problem: str = ""):
    instance = request.app.state.instance
    try:
        bank = instance.ideas()
    except InstanceError:
        bank = None
    sections: dict = {}
    if bank:
        for angle in bank.angles:
            sections.setdefault(angle.section, []).append(angle)
    return _render(request, "ideas.html", bank=bank, sections=sections,
                   labels=LABELS, pillars=PILLARS, saved=saved,
                   problem=PROBLEMS.get(problem, ""))


@router.post("/ideas/add")
def add_angle(request: Request, section: str = Form(""),
              pillar: str = Form(""), label: str = Form(""),
              text: str = Form("")):
    try:
        request.app.state.instance.add_angle(section, _pillar(pillar), label,
                                             text)
    except UnreadableError:
        return RedirectResponse("/ideas", status_code=303)
    except InstanceError:
        return RedirectResponse("/ideas?problem=bad-angle", status_code=303)
    return RedirectResponse("/ideas?saved=1", status_code=303)


@router.post("/ideas/edit")
def edit_angle(request: Request, old: str = Form(""), pillar: str = Form(""),
               label: str = Form(""), text: str = Form("")):
    try:
        request.app.state.instance.edit_angle(old, pillar=_pillar(pillar),
                                              label=label, text=text)
    except UnreadableError:
        return RedirectResponse("/ideas", status_code=303)
    except InstanceError:
        return RedirectResponse(
            "/ideas?problem=" + _angle_problem(request, old), status_code=303)
    return RedirectResponse("/ideas?saved=1", status_code=303)


@router.post("/ideas/remove")
def remove_angle(request: Request, text: str = Form("")):
    try:
        request.app.state.instance.remove_angle(text)
    except UnreadableError:
        return RedirectResponse("/ideas", status_code=303)
    except InstanceError:
        return RedirectResponse("/ideas?problem=angle-gone", status_code=303)
    return RedirectResponse("/ideas?saved=1", status_code=303)


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
