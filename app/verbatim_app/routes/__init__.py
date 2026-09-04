"""What every screen puts on the page before its own content.

The conformance report and the language pack warning belong to the instance,
not to one screen, so they are built here once and every route gets them.
"""

from __future__ import annotations

from fastapi import Request

#: "This route did not pass one", told apart from a route that passed None
#: because it read the block and found none. The two are different answers
#: and only one of them means "read it yourself".
UNREAD = object()


def context(request: Request, **extra) -> dict:
    instance = request.app.state.instance
    # A route that had to read the Status block to build its own screen hands
    # it over rather than leaving this to read it again: `Instance.status`
    # re-reads profile.md and re-parses the block every call, so two reads are
    # two answers to one question, and the file can change between them.
    given = extra.pop("status", UNREAD)
    values = {
        "request": request,
        "gaps": instance.conformance(),
        "status": instance.status() if given is UNREAD else given,
        "pack_missing": len(request.app.state.t.missing),
    }
    values.update(extra)
    return values


def render(request: Request, template: str, **extra):
    return request.app.state.templates.TemplateResponse(
        request, template, context(request, **extra))
