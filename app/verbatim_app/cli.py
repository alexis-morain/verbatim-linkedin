"""The `verbatim` command: serve one instance directory on loopback.

The host is not configurable on purpose. This is a local application; the
day somebody wants to host it, the answer is "it is your machine".
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8747


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="verbatim",
        description="Local web app over a Verbatim instance directory.",
    )
    parser.add_argument("instance", nargs="?", default=".",
                        help="instance directory (default: current directory)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--lang", default=None,
                        help="interface language override (default: the profile's)")
    args = parser.parse_args(argv)

    root = Path(args.instance).expanduser().resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    if not (root / "profile.md").is_file():
        print(f"no profile.md in {root}: the app will open on the conformance "
              "report and point you to linkedin-setup", file=sys.stderr)

    # Before anything opens a port. references/instance.md promises that an
    # instance holding a credential, or pointing a credential somewhere it was
    # not sent, stops the app rather than starting degraded.
    from .providers import ProviderError, problems, resolve
    try:
        settings = resolve(root, os.environ)
    except ProviderError as refusal:
        print(f"{refusal}", file=sys.stderr)
        return 2
    gaps = problems(settings)
    if gaps:
        print("no model is configured yet ("
              + ", ".join(g.code for g in gaps)
              + "); the screens work, the interview waits. See .env.example",
              file=sys.stderr)
    else:
        print(f"model {settings.model} at {settings.base_url}")

    from .web import create_app
    import uvicorn

    app = create_app(root, lang=args.lang)
    print(f"Verbatim on http://{HOST}:{args.port} over {root}")
    uvicorn.run(app, host=HOST, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
