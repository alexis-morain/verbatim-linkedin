"""What every screen puts on the page before its own content.

The conformance report and the language pack warning belong to the instance,
not to one screen, so they are built here once and every route gets them.
"""

from __future__ import annotations

from fastapi import Request


def context(request: Request, **extra) -> dict:
    instance = request.app.state.instance
    values = {
        "request": request,
        "gaps": instance.conformance(),
        "status": instance.status(),
        "pack_missing": len(request.app.state.t.missing),
    }
    values.update(extra)
    return values


def render(request: Request, template: str, **extra):
    return request.app.state.templates.TemplateResponse(
        request, template, context(request, **extra))
