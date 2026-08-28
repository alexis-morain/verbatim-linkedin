"""The agent loop. One loop, every provider.

Ask, stream the answer, run whatever tools were asked for, hand the results
back, repeat until the model stops asking. That is the whole mechanism, and it
is deliberately the only one: the multi provider decision was paid for by
writing this once rather than keeping a premium path and a degraded one.

What this file does not hold is anything to say. Every instruction the model
reads comes from `skills/` and `locales/` at the bundle root, loaded by the
caller and handed in as the `system` argument. This package carries mechanics
and never text, which `check.sh` enforces with a grep.

Three properties matter more than speed here:

- A failing tool answers, it never crashes the run. Somebody is mid interview.
- Results of calls made together come back together, in one message. Splitting
  them teaches a model to stop asking for them together.
- The loop has a ceiling. A weaker model will call the same tool forever, and
  the person paying for the tokens is the one running it.
- `messages` is a conversation a provider would accept at every single yield,
  including the one where the consumer walks away. A browser closing mid turn
  is the normal case, not the exception, and a dangling call left behind is a
  400 the next time somebody opens that draft.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from typing import Callable

from .providers import Settings, ToolCall, Usage, wire_for

DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_TURNS = 12
DEFAULT_TIMEOUT = 600.0


class AgentError(Exception):
    pass


class ToolRefused(Exception):
    """A tool declining on purpose: out of contract, not configured, refused.

    The message reaches the model as the tool result, so it says what to do
    differently rather than only what went wrong.
    """


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    run: Callable[[dict], str]

    def declaration(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": self.input_schema}


@dataclass(frozen=True)
class Step:
    """What the loop emits upward, one frame at a time.

    kind is one of: text, tool_call, tool_result, usage, stop, ceiling.

    A usage step carries the running total of the turn it belongs to, not an
    increment, so a turn emits several and the last one is its figure. Adding
    them up double counts. `Agent.usage` already holds the total across every
    turn and is what a screen should show.
    """
    kind: str
    text: str = ""
    call: ToolCall | None = None
    result: str = ""
    is_error: bool = False
    usage: Usage | None = None
    stop: str = ""


INTERRUPTED = "this call was not run: the conversation was left mid turn"


def http_transport(timeout: float = DEFAULT_TIMEOUT):
    """The only code in this package that opens a socket.

    Returns lines, so everything above it can be driven by a recorded stream.
    That seam is what lets the loop be tested without a key, and it is also
    the reason no test in this repository can prove an endpoint: a recording
    proves the parser. Proving the endpoint is a manual call per provider.
    """
    import httpx

    def transport(url, headers, payload):
        with httpx.Client(timeout=timeout) as client:
            with client.stream("POST", url, headers=headers,
                               json=payload) as response:
                if response.status_code >= 400:
                    response.read()
                    raise AgentError(
                        f"{url} answered {response.status_code}: "
                        f"{response.text[:400]}")
                for line in response.iter_lines():
                    yield line

    return transport


class Agent:
    def __init__(self, settings: Settings, tools, transport, *,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 max_turns: int = DEFAULT_MAX_TURNS):
        self.settings = settings
        self.wire = wire_for(settings.provider)
        self.tools = {tool.name: tool for tool in tools}
        self.transport = transport
        self.max_tokens = max_tokens
        self.max_turns = max_turns
        self.usage = Usage()

    def run(self, system: str, messages: list):
        """Drive the conversation to a stop, appending to `messages` as it goes.

        The caller owns the list, so a screen can persist it after any turn and
        pick the conversation back up from disk.
        """
        declarations = [tool.declaration() for tool in self.tools.values()]
        for turn in range(self.max_turns):
            blocks, calls, stop = yield from self._turn(system, messages,
                                                        declarations)
            if not blocks:
                # An empty content array is rejected on the next request, so a
                # turn that produced nothing leaves nothing behind either.
                yield Step("stop", stop=stop)
                return
            messages.append({"role": "assistant", "content": blocks})
            if not calls:
                yield Step("stop", stop=stop)
                return
            # One message for every result of this turn, never one each, and
            # it is appended already answered: whatever happens between here
            # and the last tool, the conversation on disk stays valid.
            results = [{"type": "tool_result", "tool_use_id": call.id,
                        "content": INTERRUPTED, "is_error": True}
                       for call in calls]
            messages.append({"role": "user", "content": results})
            for index, call in enumerate(calls):
                yield Step("tool_call", call=call)
                text, failed = self._call(call)
                results[index] = {"type": "tool_result",
                                  "tool_use_id": call.id,
                                  "content": text, "is_error": failed}
                yield Step("tool_result", call=call, result=text,
                           is_error=failed)
        yield Step("ceiling",
                   result=f"stopped after {self.max_turns} turns without an "
                          "answer; the conversation is kept, nothing is lost")

    def _turn(self, system, messages, declarations):
        """One request. Yields as the answer arrives, returns what it held."""
        payload = self.wire.payload(self.settings, system=system,
                                    messages=messages, tools=declarations,
                                    max_tokens=self.max_tokens)
        lines = self.transport(self.wire.url(self.settings),
                               self.wire.headers(self.settings), payload)
        text_parts, calls, stop = [], [], ""
        counted = Usage()
        for event in self.wire.events(lines):
            if event.kind == "text":
                text_parts.append(event.text)
                yield Step("text", text=event.text)
            elif event.kind == "tool_call":
                calls.append(event.call)
            elif event.kind == "usage":
                # A wire reports the running total of one message, so the turn
                # keeps the last figure and only turns are added up.
                counted = event.usage
                yield Step("usage", usage=event.usage)
            elif event.kind == "stop":
                stop = event.stop
        self.usage = self.usage + counted
        if not stop:
            # The stream ended without the provider saying why. That is a cut
            # answer, and calling it an end of turn would store half a
            # sentence as if it were the whole one.
            stop = "truncated"
            calls = []
        blocks = []
        text = "".join(text_parts)
        if text:
            blocks.append({"type": "text", "text": text})
        for call in calls:
            blocks.append({"type": "tool_use", "id": call.id,
                           "name": call.name, "input": call.arguments})
        return blocks, calls, stop

    def _call(self, call: ToolCall):
        """Run one tool. Returns (text for the model, whether it failed)."""
        tool = self.tools.get(call.name)
        if tool is None:
            known = ", ".join(sorted(self.tools)) or "none"
            return (f"there is no tool called {call.name!r} here; "
                    f"the tools are: {known}"), True
        try:
            return _as_text(tool.run(call.arguments)), False
        except ToolRefused as refusal:
            return str(refusal), True
        except Exception as failure:  # a broken tool ends a turn, not a session
            return (f"{type(failure).__name__}: {failure}"
                    f"\n{traceback.format_exc(limit=3)}"), True


def _as_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)
