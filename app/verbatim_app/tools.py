"""The tool set the loop hands to a model, built for one instance.

Five tools, each with a hard boundary, and every refusal says what to do
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
from . import interview
from .interview import InterviewError
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


def lint_body(bundle_root, instance_root, body: str, lang: str, *,
              environ=None, timeout: float = SUBPROCESS_TIMEOUT) -> str:
    """The deterministic pass over a post body, the real `lib/lint.py`.

    Public because the screen runs it too: the person's inline pass and the
    model's tool have to be the same pass, or the findings somebody reads are
    not the findings the engine answered to. The skill's rule holds on both
    sides, it reports and the human decides.
    """
    environ = os.environ if environ is None else environ
    bundle = Path(bundle_root)
    packs = available_langs(bundle)
    if lang not in packs:
        raise ToolRefused(f"there is no {lang!r} language pack; "
                          f"the packs are: {', '.join(packs)}")
    done = _run(bundle / "lib" / "lint.py", ["--lang", lang, "-"], body,
                instance_root, environ, timeout)
    answer = (done.stdout + ("\n" + done.stderr if done.stderr else "")).strip()
    if done.returncode not in (0, 1):
        raise ToolRefused(redact(answer, environ))
    return redact(answer, environ)


def _lint(bundle: Path, inst: Instance, arguments: dict, environ,
          timeout: float) -> str:
    return lint_body(bundle, inst.root, _required(arguments, "body"),
                     _required(arguments, "lang"), environ=environ,
                     timeout=timeout)


def _publish_plan(bundle: Path, inst: Instance, arguments: dict, environ,
                  timeout: float) -> str:
    text = _required(arguments, "text")
    done = _run(bundle / "lib" / "publish.py", ["-", "--plan"], text,
                inst.root, environ, timeout)
    if done.returncode != 0:
        raise ToolRefused(redact(
            (done.stderr or done.stdout).strip(), environ))
    return redact(done.stdout.strip(), environ)


# ---------------------------------------------- the two that hold state

SHEET_TOOL = "propose_sheet"


def sheet_tool(propose) -> Tool:
    """The validation sheet's tool, bound to one conversation, not to the
    instance: `propose` is `interview.propose` closed over the conversation
    the turn is running on. It can only ever propose. Approval is the
    person's click on their screen, and no argument to this tool reaches
    that value, the same shape of boundary as `publish_plan` and its
    missing `--confirm`."""
    def run(arguments: dict) -> str:
        try:
            propose(arguments)
        except InterviewError as refusal:
            raise ToolRefused(str(refusal)) from None
        return ("the sheet is on the person's screen; approval happens "
                "there, never in this conversation")
    return Tool(
        name=SHEET_TOOL,
        description=(
            "Put the validation sheet on the person's screen for approval. "
            "One field per line of the sheet; first_lines takes one or two "
            "proposals. A new proposal replaces a sheet not yet approved."),
        input_schema={
            "type": "object",
            "properties": {
                "angle": {"type": "string"},
                "elements": {"type": "array", "items": {"type": "string"}},
                "moment": {"type": "string"},
                "conviction": {"type": "string"},
                "first_lines": {"type": "array",
                                "items": {"type": "string"}},
            },
            "required": ["angle", "elements", "moment", "conviction",
                         "first_lines"],
        },
        run=run)


DRAFT_TOOL = "propose_draft"


def draft_tool(write) -> Tool:
    """The draft's tool, bound to one conversation the way `sheet_tool` is.

    It offers a post and the anchors it claims for it, and that is all it can
    do: archiving the draft into `posts/` is its own step, and the person's.
    The engine points a model at this tool by requiring it for the turn
    rather than by asking, since a model weak enough to answer in prose is
    exactly the one the traceability panel exists for.
    """
    def run(arguments: dict) -> str:
        try:
            write(arguments)
        except InterviewError as refusal:
            raise ToolRefused(str(refusal)) from None
        return ("the draft is on the person's screen, next to the anchors "
                "it claims; they decide what happens to it")
    return Tool(
        name=DRAFT_TOOL,
        description=(
            "Put the post on the person's screen, with the anchors backing "
            "it. 'body' is the post as it would be published, without the "
            "signature block, which is concatenated from the profile and "
            "never written here. Each anchor pairs 'post', a fragment of "
            "the body copied exactly, with 'said', the interview sentence "
            "backing it, quoted word for word in the language of the "
            "interview. A claim nothing backs stays bare: bare is honest, "
            "an invented quote is not. 'photos' and 'tips' are what the "
            "session leaves behind rather than part of the post: they are "
            "filed under its session notes and never concatenated into it. "
            "One entry per kind at most, and what is left out is shown as "
            "left out rather than refusing the post."),
        input_schema={
            "type": "object",
            "properties": {
                "body": {"type": "string"},
                "anchors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"post": {"type": "string"},
                                       "said": {"type": "string"}},
                        "required": ["post", "said"],
                    },
                },
                "photos": _notes_schema(interview.PHOTO_KINDS),
                "tips": _notes_schema(interview.TIP_KINDS),
            },
            "required": ["body"],
        },
        run=run)


def _notes_schema(kinds) -> dict:
    """The shape `photos` and `tips` share. Kinds are the vocabulary the
    interview store enforces, read from there rather than repeated here: two
    lists that have to agree eventually will not."""
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"kind": {"type": "string",
                                    "enum": list(kinds)},
                           "text": {"type": "string"}},
            "required": ["kind", "text"],
        },
    }


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
