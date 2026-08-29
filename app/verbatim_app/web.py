"""The FastAPI application factory.

One instance directory, one app. Bound to loopback by design: any request
whose Origin is not exactly this app, port included, is refused, so neither a
hostile web page nor another program's local server can post into the
instance.

Two seams are injected here rather than reached for: the environment the
engine configuration is read from, and the transport the agent loop speaks
over. Both default to the real thing and both are replaced wholesale in the
tests, which is how a screen that drives a model gets tested without a key.

**No GET in this app changes anything or costs anything.** That is a rule, not
an observation. A cross origin no-cors GET, the kind an `<img>` on a hostile
page makes, carries no Origin header at all, so the first guard below cannot
see it; the second one catches it in every browser that sends Sec-Fetch-Site,
and the rule is what holds where a browser does not. It is the reason the
interview turn is a POST that streams rather than the EventSource the plan
sketched: EventSource only speaks GET, and a GET that spends somebody's API
budget is reachable from any tab they have open.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, markup
from .i18n import bundle_root, load_strings
from .instance import Instance
from .routes import interview as interview_screen
from .routes import pages
from .routes import publish as publish_screen

PACKAGE = Path(__file__).resolve().parent

LOCAL = ("127.0.0.1", "localhost")


def create_app(instance_path, lang: str | None = None, *,
               environ=None, transport=None) -> FastAPI:
    instance = Instance(instance_path)
    status = instance.status()
    language = lang or (status.interface_language if status else "en")
    strings = load_strings(language)

    # No docs, no schema: this app has one consumer and it is the screens
    # in this package.
    app = FastAPI(title="Verbatim", version=__version__, docs_url=None,
                  redoc_url=None, openapi_url=None)
    app.state.instance = instance
    app.state.t = strings
    app.state.environ = os.environ if environ is None else environ
    app.state.transport = transport
    app.state.bundle = bundle_root()
    app.state.turn_locks = {}
    app.state.publish_locks = {}
    # One live publish token per post: the plan most recently drawn for it,
    # spent by the confirm that follows. Keyed by post rather than by token so
    # that drawing a plan retires the one before it, which is what stops two
    # outstanding plans confirming twice, and what keeps this bounded by the
    # posts somebody has planned. In memory and per process on purpose: what
    # it guards is a double click, a reloaded POST and a second tab, all of
    # which happen inside one run of this app. It is not an idempotency key
    # and does not pretend to be one across restarts.
    app.state.publish_tokens = {}
    app.state.templates = Jinja2Templates(directory=PACKAGE / "templates")
    # `markdown` returns Markup, so no template ever writes `| safe` for it.
    # Both come from `markup`, which is the only module in this package
    # allowed to import a markdown parser; check.sh holds that rule.
    app.state.templates.env.globals.update(t=strings, lang=language,
                                           instance_root=str(instance.root),
                                           markdown=markup.render,
                                           plain=markup.plain)

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):
        # Host first: it names which origin this request thinks it reached, so
        # everything below is compared against it. A hostile name resolved to
        # 127.0.0.1, the DNS rebinding case, gives itself away here.
        host = request.headers.get("host", "")
        if host.split(":", 1)[0] not in LOCAL:
            return PlainTextResponse("unexpected host refused", status_code=403)
        # Origin is compared whole, port included. A hostname test would accept
        # http://localhost:3000, which is somebody else's local server, not
        # this app: close enough to look same-site to a browser and far enough
        # to be a different program. Since 5.3 what sits behind these routes is
        # a paid provider call and an rmtree over somebody's own words.
        # The scheme is part of it. This app serves plain http on loopback and
        # nothing else, so an https origin on the same host and port is not it
        # either: it is some other program that happens to hold a certificate.
        origin = request.headers.get("origin")
        if origin is not None and origin != f"http://{host}":
            return PlainTextResponse("cross-origin request refused",
                                     status_code=403)
        # Browsers omit Origin on same-origin GETs, which is why the check
        # above cannot be made mandatory: requiring it would refuse this app's
        # own screens. Sec-Fetch-Site names what Origin cannot, for the no-cors
        # GET a hostile page makes with an <img> or a <script>. Navigation is
        # exempt: following a link into this app is somebody arriving, and a
        # navigation that changes something is a POST, which carries Origin.
        site = request.headers.get("sec-fetch-site")
        if site in ("cross-site", "same-site") and \
                request.headers.get("sec-fetch-mode") != "navigate":
            return PlainTextResponse("cross-site request refused",
                                     status_code=403)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
    app.include_router(pages.router)
    app.include_router(publish_screen.router)
    app.include_router(interview_screen.router)
    return app
