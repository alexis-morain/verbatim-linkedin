"""The FastAPI application factory.

One instance directory, one app. Bound to loopback by design: any request
whose Origin is not this app is refused, so a hostile web page open in the
same browser cannot post into the instance.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__
from .i18n import load_strings
from .instance import Instance
from .routes import pages

PACKAGE = Path(__file__).resolve().parent


def create_app(instance_path, lang: str | None = None) -> FastAPI:
    instance = Instance(instance_path)
    status = instance.status()
    language = lang or (status.interface_language if status else "en")
    strings = load_strings(language)

    app = FastAPI(title="Verbatim", version=__version__, docs_url=None, redoc_url=None)
    app.state.instance = instance
    app.state.t = strings
    app.state.templates = Jinja2Templates(directory=PACKAGE / "templates")
    app.state.templates.env.globals.update(t=strings, lang=language,
                                           instance_root=str(instance.root))

    @app.middleware("http")
    async def loopback_only(request: Request, call_next):
        # Origin catches cross-origin form posts; Host catches DNS rebinding,
        # where a hostile name resolves to 127.0.0.1 and no Origin is sent.
        origin = request.headers.get("origin")
        if origin is not None:
            origin_host = origin.split("://", 1)[-1].split(":", 1)[0]
            if origin_host not in ("127.0.0.1", "localhost"):
                return PlainTextResponse("cross-origin request refused", status_code=403)
        host = request.headers.get("host", "").split(":", 1)[0]
        if host not in ("127.0.0.1", "localhost"):
            return PlainTextResponse("unexpected host refused", status_code=403)
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")
    app.include_router(pages.router)
    return app
