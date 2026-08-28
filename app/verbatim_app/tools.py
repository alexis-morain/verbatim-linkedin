"""The tool set the loop hands to a model, built for one instance.

Four tools, each with a hard boundary, and every refusal says what to do
instead of only what went wrong, because its text is the tool result the
model reads next.

- read_instance sees the contract files and nothing else. `.env` is engine
  configuration, loaded by the app itself; a tool that could read it would
  hand the model whatever somebody wrongly parked there.
- write_instance goes through `Instance.write`, so the writable set is
  `instance.WRITABLE` and the write is atomic. Posts are archived by their
  own step, never through this tool.
- lint_post and publish_plan run the real `lib/` scripts in a subprocess,
  with the instance as working directory. publish_plan is plan mode only:
  the argument list is built here and `--confirm` does not exist in it, so
  there is no input that makes this tool send anything.

Nothing that comes back from a subprocess reaches the model before the
values of secret named environment variables are struck out of it. Like
every name based rule in this project, that guards an accident, not a
determined author: a credential pasted inside an innocently named value
gets through, and the publish plan still shows its target on purpose,
because checking the target is what a plan is for.

Standard library only, like the rest of the engine seam.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .agent import Tool, ToolRefused
from .instance import Instance, InstanceError, WRITABLE
from .providers import SECRET_MARKERS

SUBPROCESS_TIMEOUT = 120.0

#: Root files a model may read: the writable set is also the readable one,
#: posts/ and corpus/ are served by their own branches below.
READABLE = WRITABLE


def available_langs(bundle_root) -> list:
    root = Path(bundle_root) / "locales"
    return sorted(path.name for path in root.iterdir()
                  if path.is_dir() and not path.name.startswith("_"))


def _required(arguments: dict, name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str):
        raise ToolRefused(f"this tool needs a {name!r} string argument")
    return value


def redact(text: str, environ) -> str:
    """Strike the values of secret named variables out of anything on its way
    to a model or to a screen. The name survives, the value never does.

    Shared with the interview screen, which puts a provider's own error body in
    front of somebody: a gateway that echoes an Authorization header into a
    debug message is the same accident as a subprocess printing its own
    environment.
    """
    for name, value in environ.items():
        if not isinstance(value, str) or len(value) < 4:
            continue
        if any(marker in name.upper() for marker in SECRET_MARKERS):
            text = text.replace(value, f"[{name}]")
    return text


def _present(names) -> str:
    return ", ".join(names) if names else "none yet"


# ------------------------------------------------------------------ the four

def _read(inst: Instance, arguments: dict) -> str:
    path = _required(arguments, "path").strip().strip("/")
    if path == ".env" or path.startswith(".env"):
        raise ToolRefused(
            ".env is engine configuration and the app loads it itself; it is "
            "never interview material. Read profile.md, voice.md, pillars.md, "
            "ideas.md, linkedin-page.md, posts/<file> or corpus/<file>.")
    if path in ("posts", "corpus"):
        names = ([post.filename for post in inst.posts()] if path == "posts"
                 else inst.corpus())
        return "\n".join(names) if names else f"{path}/ holds no file yet"
    try:
        if path.startswith("posts/"):
            return inst.post_raw(path[len("posts/"):])
        if path.startswith("corpus/"):
            return inst.corpus_text(path[len("corpus/"):])
        if path in READABLE:
            return inst.read(path)
    except InstanceError as refusal:
        raise ToolRefused(_what_exists(inst, path, refusal)) from None
    raise ToolRefused(
        f"{path!r} is not part of the instance contract. Readable: "
        f"{', '.join(READABLE)}, posts/<file>, corpus/<file>, or 'posts' "
        "and 'corpus' alone to list them.")


def _what_exists(inst: Instance, path: str, refusal: InstanceError) -> str:
    if path.startswith("posts/"):
        return (f"{refusal}. The posts are: "
                f"{_present([p.filename for p in inst.posts()])}.")
    if path.startswith("corpus/"):
        return f"{refusal}. The corpus files are: {_present(inst.corpus())}."
    here = [name for name in READABLE if (inst.root / name).is_file()]
    return f"{refusal}. The files present are: {_present(here)}."


def _write(inst: Instance, arguments: dict) -> str:
    path = _required(arguments, "path")
    text = _required(arguments, "text")
    try:
        inst.write(path, text)
    except InstanceError as refusal:
        raise ToolRefused(
            f"{refusal}. The writable files are: {', '.join(WRITABLE)}; "
            "posts are archived by their own step, and .env is edited by "
            "the person, never from here.") from None
    return f"wrote {path}, {len(text)} characters"


def _run(script: Path, args, stdin: str, cwd, environ,
         timeout: float):
    try:
        return subprocess.run(
            [sys.executable, str(script), *args], input=stdin,
            capture_output=True, text=True, cwd=str(cwd),
            env=dict(environ), timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ToolRefused(
            f"{script.name} did not answer within {timeout:g} seconds; "
            "try again, or with a shorter text") from None


def _lint(bundle: Path, inst: Instance, arguments: dict, environ,
          timeout: float) -> str:
    body = _required(arguments, "body")
    lang = _required(arguments, "lang")
    packs = available_langs(bundle)
    if lang not in packs:
        raise ToolRefused(f"there is no {lang!r} language pack; "
                          f"the packs are: {', '.join(packs)}")
    done = _run(bundle / "lib" / "lint.py", ["--lang", lang, "-"], body,
                inst.root, environ, timeout)
    answer = (done.stdout + ("\n" + done.stderr if done.stderr else "")).strip()
    if done.returncode not in (0, 1):
        raise ToolRefused(redact(answer, environ))
    return redact(answer, environ)


def _publish_plan(bundle: Path, inst: Instance, arguments: dict, environ,
                  timeout: float) -> str:
    text = _required(arguments, "text")
    done = _run(bundle / "lib" / "publish.py", ["-", "--plan"], text,
                inst.root, environ, timeout)
    if done.returncode != 0:
        raise ToolRefused(redact(
            (done.stderr or done.stdout).strip(), environ))
    return redact(done.stdout.strip(), environ)


# ------------------------------------------------------------------- factory

def instance_tools(instance_root, bundle_root, *, environ=None,
                   timeout: float = SUBPROCESS_TIMEOUT) -> list:
    environ = os.environ if environ is None else environ
    inst = Instance(instance_root)
    bundle = Path(bundle_root)
    packs = ", ".join(available_langs(bundle))
    return [
        Tool(
            name="read_instance",
            description=(
                "Read one file of the instance: profile.md, voice.md, "
                "pillars.md, ideas.md, linkedin-page.md, posts/<file> or "
                "corpus/<file>. Pass 'posts' or 'corpus' alone to list "
                "that directory."),
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            run=lambda arguments: _read(inst, arguments)),
        Tool(
            name="write_instance",
            description=(
                "Replace one instance file, atomically. Writable: "
                f"{', '.join(WRITABLE)}. The text is the whole new file."),
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"},
                               "text": {"type": "string"}},
                "required": ["path", "text"],
            },
            run=lambda arguments: _write(inst, arguments)),
        Tool(
            name="lint_post",
            description=(
                "Run the deterministic style pass, lib/lint.py, over a post "
                "body. Returns the findings; only the rules the language "
                f"pack marks hard block. Packs: {packs}."),
            input_schema={
                "type": "object",
                "properties": {"body": {"type": "string"},
                               "lang": {"type": "string"}},
                "required": ["body", "lang"],
            },
            run=lambda arguments: _lint(bundle, inst, arguments, environ,
                                        timeout)),
        Tool(
            name="publish_plan",
            description=(
                "Show what publishing this post text would do, via "
                "lib/publish.py in plan mode. Nothing is sent, ever; the "
                "person publishes from their own screen."),
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            run=lambda arguments: _publish_plan(bundle, inst, arguments,
                                                environ, timeout)),
    ]
