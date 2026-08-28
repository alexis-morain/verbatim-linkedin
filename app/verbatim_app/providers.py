"""The provider seam: configuration, the two wire formats, token prices.

One loop serves every provider, so the differences between them are confined
to this file. A wire turns the engine's own message shape into a request body
and turns a response stream back into engine events. Nothing above this file
knows which vendor is answering.

Two wires ship. `anthropic` speaks the native Messages format. `openai` speaks
the chat completions format, which is what OpenAI, Mistral, OpenRouter, Ollama
and LM Studio all answer to, so local inference costs nothing extra here.

This is raw HTTP on purpose, not a vendor library. A vendor library would mean
two code paths, and the plan bought one loop tested once instead. The recorded
streams in the tests are written from the published formats, so they prove the
parser and not the endpoint: only a real call proves the endpoint, and that is
a manual step per provider before a release.

Standard library only. The transport that actually opens a socket lives in
agent.py, which is the only place this package touches the network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

API_VERSION = "2023-06-01"

DEFAULT_BASE_URL = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
}

# Only the native wire gets a default. There is no model name that would be
# right for "any endpoint speaking the OpenAI format", so that one is asked for.
DEFAULT_MODEL = {"anthropic": "claude-opus-5"}

# Per million tokens, input and output. Prices are shown only for a model that
# is in this table; everywhere else the screens show tokens and no price, which
# is the honest answer rather than a zero over somebody's real bill. There are
# no OpenAI-format entries because this project has not verified any, and a
# guessed price is worse than none.
PRICES = {
    "claude-fable-5": (10.0, 50.0),
    "claude-mythos-5": (10.0, 50.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# A name holding any of these is a credential. The instance directory gets
# copied, synced and sometimes committed, so none of them may live there.
# references/instance.md carries the rule; this is its enforcement.
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")

# The same reasoning, one step further, and it is the step that is easy to
# miss: if the instance file is not trusted to hold a key, it is not trusted
# to say where the key is sent either. An endpoint read from it earns the key
# only when it is the provider's own, or a runtime on this machine. Anything
# else has to be named from the process environment, next to the key it will
# receive, because that pairing is the whole decision.
ENDPOINT_OK = "VERBATIM_ENDPOINT_OK"

LOOPBACK = ("127.0.0.1", "localhost", "::1", "0.0.0.0")

DEFAULT_PORTS = {"https": 443, "http": 80}


class ProviderError(Exception):
    """A refusal, with a machine handle on it.

    The message is written for a terminal, where the engine speaks in its own
    voice and there is no language pack. A screen has one, so a refusal that
    can reach a screen also carries a `code` naming which refusal it is and a
    `detail` holding only machine facts, variable names and hosts. The screen
    renders the pack's sentence around those; printing the message would put
    English prose on a French page.
    """

    def __init__(self, message, code: str = "", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    base_url: str
    api_key: str | None


@dataclass(frozen=True)
class Problem:
    code: str
    detail: str = ""


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens,
                     self.output_tokens + other.output_tokens)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Event:
    """What a wire emits, whichever vendor produced it.

    kind is one of: text, tool_call, usage, stop.
    """
    kind: str
    text: str = ""
    call: ToolCall | None = None
    usage: Usage | None = None
    stop: str = ""


# ------------------------------------------------------------- configuration

def read_env_file(path) -> dict:
    """Parse a .env file into a map. An empty value counts as unset, because
    .env.example ships every key empty and copying it must not blank the
    defaults."""
    path = Path(path)
    if not path.is_file():
        return {}
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            found[name] = value
    return found


def _refuse_secrets(raw: str, path) -> None:
    """Scan the file for a credential written as an assignment.

    A commented out key is still a key in a file that gets committed, so
    comments are read too. But only assignments: a name in UPPER_SNAKE with a
    value after it. Prose is not scanned, because the sentence a person writes
    after being told to keep keys elsewhere ("# Keys live in my shell
    profile") would otherwise stop their app, and `.env.example` invites being
    copied while naming all three key variables with empty values.

    The no equals form is out of scope, and that is a trade rather than a
    free win: a secret written on such a line is committed just as thoroughly.
    But `cli.py` makes a refusal fatal, and the false positives were real, so
    precision wins over reach here. This guards an accident, not a determined
    author: a key parked in `NOTE=` still gets through, and no rule that reads
    names fixes that.
    """
    named = []
    for line in raw.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped.startswith("export "):
            stripped = stripped[len("export "):].lstrip()
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(\S.*)?$", stripped)
        if match is None or not (match.group(2) or "").strip():
            continue
        name = match.group(1)
        # Case and hyphens do not make a credential something else. Prose
        # stays out because a sentence does not put an equals sign after its
        # first word.
        if any(marker in name.upper() for marker in SECRET_MARKERS):
            named.append(name)
    if named:
        # The names, never the values: this message reaches a browser screen.
        raise ProviderError(
            f"{path} holds credentials: {', '.join(sorted(set(named)))}. "
            "An instance is a directory people copy, sync and sometimes "
            "commit, so it never carries a key. Move those lines to your "
            "shell environment and delete them here, comments included.",
            code="secrets-in-instance", detail=", ".join(sorted(set(named)))
        )


def resolve(instance_root, environ) -> Settings:
    """Read the engine configuration for one instance.

    The instance .env carries the choice of provider, model and endpoint. The
    process environment overrides it key by key and is the only place a key is
    ever read from. references/instance.md is the contract.
    """
    root = Path(instance_root)
    path = root / ".env"
    if path.is_file():
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, ValueError) as unreadable:
            # Saved in another encoding, or a mode that came across wrong. The
            # screen that would show the fix is the one that reads this file,
            # so a traceback here takes away the way out.
            raise ProviderError(
                f"{path} cannot be read: {type(unreadable).__name__}",
                code="env-unreadable") from None
        _refuse_secrets(raw, path)
    from_file = read_env_file(path)

    def setting(name, default=""):
        return environ.get(name) or from_file.get(name) or default

    provider = setting("VERBATIM_PROVIDER", "anthropic")
    base_url = setting("VERBATIM_BASE_URL", DEFAULT_BASE_URL.get(provider, ""))
    _refuse_userinfo(base_url)
    api_key = _api_key(provider, environ)
    # Whether the endpoint came from the environment is decided exactly the
    # way setting() decided it. An exported but empty variable falls through
    # to the file, and testing for the name alone would disarm the guard for
    # anybody who sources the shipped .env.example.
    if api_key and not environ.get("VERBATIM_BASE_URL"):
        _refuse_untrusted_endpoint(base_url, provider, environ, path)
    return Settings(provider=provider,
                    model=setting("VERBATIM_MODEL", DEFAULT_MODEL.get(provider, "")),
                    base_url=base_url, api_key=api_key)


def _refuse_userinfo(base_url: str) -> None:
    """A credential smuggled into the endpoint itself, as userinfo or as a
    query parameter, would slip past the name check and then get rendered on
    a screen as part of the endpoint."""
    parts = urlsplit(base_url)
    if parts.username or parts.password:
        raise ProviderError(
            "the endpoint carries a user and password in the URL; that is a "
            "credential in a file that is not allowed to hold one",
            code="credential-in-endpoint")
    if any(marker in (parts.query or "").upper() for marker in SECRET_MARKERS):
        raise ProviderError(
            "the endpoint carries what looks like a credential in its query "
            "string; put it in the process environment instead",
            code="credential-in-endpoint")


def _authority(parts):
    """Host and port, with the port written out treated as the port implied."""
    return (parts.hostname, parts.port or DEFAULT_PORTS.get(parts.scheme))


def _refuse_untrusted_endpoint(base_url, provider, environ, path) -> None:
    if not base_url:
        # Nothing to send anywhere. problems() names this properly, and a
        # complaint about a scheme on an empty string points at the wrong
        # thing entirely.
        return
    parts = urlsplit(base_url)
    host = parts.hostname or ""
    if is_loopback(base_url):
        return
    if parts.scheme != "https":
        raise ProviderError(
            f"{path} would send the key to {host!r} in clear text. A file that "
            "travels between machines does not get to downgrade the transport "
            "carrying a credential.",
            code="endpoint-in-clear", detail=host)
    # Port included: the provider's name on another port is another endpoint.
    if _authority(parts) == _authority(urlsplit(DEFAULT_BASE_URL.get(provider, ""))):
        return
    allowed = {h.strip().lower() for h in
               (environ.get(ENDPOINT_OK) or "").split(",") if h.strip()}
    if host.lower() in allowed:
        return
    raise ProviderError(
        f"{path} sends the key to {host!r}, and that file is not trusted to "
        "decide where a credential goes. Either export VERBATIM_BASE_URL "
        f"yourself, or name the host in {ENDPOINT_OK} next to the key it is "
        "allowed to receive.",
        code="endpoint-untrusted", detail=host)


def _api_key(provider: str, environ) -> str | None:
    names = ["VERBATIM_API_KEY"]
    if provider == "anthropic":
        names.append("ANTHROPIC_API_KEY")
    elif provider == "openai":
        names.append("OPENAI_API_KEY")
    for name in names:
        value = environ.get(name)
        if value:
            return value
    return None


def is_loopback(base_url: str) -> bool:
    host = urlsplit(base_url).hostname or ""
    return host in LOOPBACK


def problems(settings: Settings) -> list:
    """What stops this configuration from being usable. Reported, never
    guessed around: an unconfigured install is a normal state with a screen
    of its own, not a crash."""
    found = []
    if settings.provider not in DEFAULT_BASE_URL:
        found.append(Problem("provider-unknown", settings.provider))
    if not settings.model:
        found.append(Problem("model-missing"))
    if not settings.base_url:
        found.append(Problem("endpoint-missing"))
    elif not settings.api_key and not is_loopback(settings.base_url):
        found.append(Problem("key-missing", settings.provider))
    return found


def price(model: str, usage: Usage):
    """Dollars for this usage, or None when the model is not in the table."""
    rates = PRICES.get(model)
    if rates is None:
        return None
    return (usage.input_tokens * rates[0] + usage.output_tokens * rates[1]) / 1e6


# ---------------------------------------------------------------------- wires

#: The end of stream marker of the chat format. It is proof that a stream
#: ended on purpose, which is the only thing that tells a runtime forgetting
#: finish_reason apart from a connection cut in the middle of an answer.
DONE = object()


def _payloads(lines):
    """Yield the parsed data payloads of a server sent event stream.

    Both formats put their JSON on `data:` lines. Named event lines, comments
    and keepalives carry nothing this loop needs.
    """
    for line in lines:
        line = line.rstrip("\r\n") if isinstance(line, str) else line.decode()
        if not line.strip() or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        body = line[len("data:"):].strip()
        if body == "[DONE]":
            yield DONE
            continue
        if not body:
            continue
        try:
            yield json.loads(body)
        except json.JSONDecodeError as error:
            raise ProviderError(f"unreadable stream line: {body[:120]}") from error


def _join_url(base_url: str, path: str) -> str:
    """Join without repeating a segment the base already ends with.

    The two wires disagree by convention: the native endpoint is under /v1
    and the chat one is usually configured with /v1 already in it. Somebody
    will write the base URL the other way round, and /v1/v1/messages is a
    404 nobody enjoys reading.
    """
    parts = urlsplit(base_url)
    base = parts.path.rstrip("/")
    for segment in path.strip("/").split("/"):
        if base.endswith("/" + segment):
            base = base[: -len(segment) - 1]
        break
    return urlunsplit((parts.scheme, parts.netloc, base + path,
                       parts.query, parts.fragment))


class Wire:
    name = ""

    def url(self, settings: Settings) -> str:
        raise NotImplementedError

    def headers(self, settings: Settings) -> dict:
        raise NotImplementedError

    def payload(self, settings, system, messages, tools, *,
                max_tokens) -> dict:
        raise NotImplementedError

    def events(self, lines):
        raise NotImplementedError


class AnthropicWire(Wire):
    """The native Messages format. The engine's message shape is this one, so
    the body is close to a passthrough and the parser does the work."""

    name = "anthropic"

    STOPS = {
        "end_turn": "end_turn",
        "stop_sequence": "end_turn",
        "tool_use": "tool_use",
        "max_tokens": "max_tokens",
        "refusal": "refusal",
    }

    def url(self, settings):
        return _join_url(settings.base_url, "/v1/messages")

    def headers(self, settings):
        found = {"content-type": "application/json",
                 "anthropic-version": API_VERSION,
                 "accept": "text/event-stream"}
        if settings.api_key:
            found["x-api-key"] = settings.api_key
        return found

    def payload(self, settings, system, messages, tools, *, max_tokens):
        body = {"model": settings.model, "max_tokens": max_tokens,
                "stream": True, "messages": list(messages)}
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [{"name": t["name"],
                              "description": t.get("description", ""),
                              "input_schema": t["input_schema"]} for t in tools]
        return body

    def events(self, lines):
        blocks: dict = {}
        seen_ids: set = set()
        usage = Usage()
        for data in _payloads(lines):
            if data is DONE:
                continue
            kind = data.get("type")
            if kind == "error":
                detail = data.get("error", {})
                raise ProviderError(
                    f"{detail.get('type', 'error')}: {detail.get('message', '')}")
            if kind == "message_start":
                counted = data.get("message", {}).get("usage", {})
                usage = replace(usage,
                                input_tokens=counted.get("input_tokens", 0))
                # Reported now as well as at the end: a stream cut before the
                # closing event still billed these, and silence would read as
                # a free turn.
                yield Event("usage", usage=usage)
            elif kind == "content_block_start":
                block = data.get("content_block", {})
                blocks[data.get("index")] = {"type": block.get("type"),
                                             "id": block.get("id", ""),
                                             "name": block.get("name", ""),
                                             "json": ""}
            elif kind == "content_block_delta":
                delta = data.get("delta", {})
                if delta.get("type") == "text_delta":
                    yield Event("text", text=delta.get("text", ""))
                elif delta.get("type") == "input_json_delta":
                    block = blocks.setdefault(data.get("index"),
                                              {"type": "tool_use", "id": "",
                                               "name": "", "json": ""})
                    block["json"] += delta.get("partial_json", "")
            elif kind == "content_block_stop":
                block = blocks.pop(data.get("index"), None)
                if block and block["type"] == "tool_use":
                    seen_ids.add(block["id"])
                    yield Event("tool_call",
                                call=_tool_call(
                                    block["id"] or _spare_id(seen_ids),
                                    block["name"], block["json"]))
            elif kind == "message_delta":
                counted = data.get("usage", {})
                usage = replace(usage,
                                output_tokens=counted.get("output_tokens", 0))
                yield Event("usage", usage=usage)
                reason = data.get("delta", {}).get("stop_reason") or ""
                yield Event("stop", stop=self.STOPS.get(reason, "other"))
        # No stop event is emitted when the stream simply ended. A cut stream
        # is not an answer, and the loop above turns that silence into one.


class OpenAIWire(Wire):
    """The chat completions format, as spoken by OpenAI and by every runtime
    that copied it, local ones included.

    Two conversions matter and both are lossy in one direction. A tool result
    is a message here, not a block, so one engine message can become several.
    And an error has no status of its own on a tool message, so it is spelled
    into the text.
    """

    name = "openai"

    STOPS = {
        "stop": "end_turn",
        "tool_calls": "tool_use",
        "length": "max_tokens",
        "content_filter": "refusal",
    }

    def url(self, settings):
        return _join_url(settings.base_url, "/chat/completions")

    def headers(self, settings):
        found = {"content-type": "application/json",
                 "accept": "text/event-stream"}
        if settings.api_key:
            found["Authorization"] = f"Bearer {settings.api_key}"
        return found

    def payload(self, settings, system, messages, tools, *, max_tokens):
        body = {"model": settings.model, "max_tokens": max_tokens,
                "stream": True,
                "stream_options": {"include_usage": True},
                "messages": self._messages(system, messages)}
        if tools:
            body["tools"] = [{"type": "function",
                              "function": {"name": t["name"],
                                           "description": t.get("description", ""),
                                           "parameters": t["input_schema"]}}
                             for t in tools]
        return body

    def _messages(self, system, messages):
        out = []
        if system:
            out.append({"role": "system", "content": system})
        for message in messages:
            role = message.get("role")
            blocks = message.get("content")
            if isinstance(blocks, str):
                out.append({"role": role, "content": blocks})
                continue
            text = "".join(b.get("text", "") for b in blocks
                           if b.get("type") == "text")
            if role == "assistant":
                calls = [{"id": b["id"], "type": "function",
                          "function": {"name": b["name"],
                                       "arguments": json.dumps(b.get("input", {}))}}
                         for b in blocks if b.get("type") == "tool_use"]
                # A strict implementation wants a null content next to
                # tool calls, not an empty string.
                built = {"role": "assistant", "content": text or None}
                if calls:
                    built["tool_calls"] = calls
                elif not text:
                    built["content"] = ""
                out.append(built)
                continue
            # Results first: a runtime expects them straight after the call.
            for block in blocks:
                if block.get("type") != "tool_result":
                    continue
                content = block.get("content", "")
                if block.get("is_error"):
                    content = f"error: {content}"
                out.append({"role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": content})
            if text:
                out.append({"role": role, "content": text})
        return out

    def events(self, lines):
        calls: dict = {}
        usage = None
        reason = ""
        opened = None
        ended = False
        for data in _payloads(lines):
            if data is DONE:
                ended = True
                continue
            if "error" in data and data.get("error"):
                detail = data["error"]
                message = detail.get("message", "") if isinstance(detail, dict) \
                    else str(detail)
                raise ProviderError(f"endpoint refused: {message}")
            counted = data.get("usage")
            if counted:
                usage = Usage(input_tokens=counted.get("prompt_tokens", 0),
                              output_tokens=counted.get("completion_tokens", 0))
            for choice in data.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    yield Event("text", text=delta["content"])
                for fragment in delta.get("tool_calls") or []:
                    function = fragment.get("function") or {}
                    key = fragment.get("index")
                    opens = bool(fragment.get("id") or function.get("name"))
                    if key is not None:
                        # An indexed opener is still the call last opened: a
                        # runtime may index the first fragment and leave it
                        # off the ones carrying arguments.
                        if opens:
                            opened = key
                    else:
                        # A runtime that copied the format without the index
                        # field. Only the opening fragment of a call carries a
                        # name or an id; the ones after it carry arguments
                        # alone and continue the call already open. Keys made
                        # up here are strings, so they can never collide with
                        # a real integer index.
                        if opens:
                            key = f"unindexed-{len(calls)}"
                            opened = key
                        else:
                            key = opened if opened is not None else "unindexed-0"
                    slot = calls.setdefault(key,
                                            {"id": "", "name": "", "json": ""})
                    if fragment.get("id"):
                        slot["id"] = fragment["id"]
                    function = fragment.get("function") or {}
                    if function.get("name"):
                        slot["name"] = function["name"]
                    slot["json"] += function.get("arguments") or ""
                if choice.get("finish_reason"):
                    reason = choice["finish_reason"]
        ordered = sorted(calls.items(), key=_call_order)
        for call_id, slot in zip(_identify(s for _, s in ordered), ordered):
            yield Event("tool_call",
                        call=_tool_call(call_id, slot[1]["name"],
                                        slot[1]["json"]))
        if usage is not None:
            yield Event("usage", usage=usage)
        # Either the endpoint said why it stopped, or it closed the stream
        # on purpose. Runtimes that copied the format without finish_reason
        # still send the end marker, and that is the difference between one
        # of those and a connection cut mid answer, which stays unreported so
        # the loop can call it a truncation.
        if reason:
            yield Event("stop", stop=self.STOPS.get(reason, "other"))
        elif ended:
            yield Event("stop", stop="tool_use" if calls else "end_turn")


def _spare_id(taken: set) -> str:
    made = 0
    while f"unnamed-{made}" in taken:
        made += 1
    taken.add(f"unnamed-{made}")
    return f"unnamed-{made}"


def _identify(slots):
    """Give every call an id, without a made up one shadowing a real one."""
    slots = list(slots)
    taken = {s["id"] for s in slots if s["id"]}
    out, made = [], 0
    for slot in slots:
        if slot["id"]:
            out.append(slot["id"])
            continue
        candidate = f"unnamed-{made}"
        while candidate in taken:
            made += 1
            candidate = f"unnamed-{made}"
        taken.add(candidate)
        made += 1
        out.append(candidate)
    return out


def _call_order(item):
    key = item[0]
    return (0, key, "") if isinstance(key, int) else (1, 0, str(key))


def _tool_call(call_id: str, name: str, raw: str) -> ToolCall:
    raw = (raw or "").strip()
    if not raw:
        return ToolCall(id=call_id, name=name, arguments={})
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ProviderError(
            f"tool call {name!r} sent arguments that are not JSON: {raw[:120]}"
        ) from error
    if not isinstance(arguments, dict):
        raise ProviderError(f"tool call {name!r} sent {type(arguments).__name__} "
                            "arguments, expected an object")
    return ToolCall(id=call_id, name=name, arguments=arguments)


WIRES = {"anthropic": AnthropicWire, "openai": OpenAIWire}


def wire_for(name: str) -> Wire:
    try:
        return WIRES[name]()
    except KeyError:
        known = ", ".join(sorted(WIRES))
        raise ProviderError(f"unknown provider {name!r}; this bundle speaks "
                            f"{known}") from None
