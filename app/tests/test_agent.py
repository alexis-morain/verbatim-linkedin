"""Tests for the agent loop, against a transport that replays a stream.

The loop never opens a socket here. Every test hands it a recorded provider
stream and reads back what it did with it, which is also how the interview
screen will be tested once it exists.

    python3 app/tests/test_agent.py
"""

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

try:
    import httpx  # noqa: F401
    HAS_HTTPX = True
except ImportError:  # the transport test needs it, the loop tests do not
    HAS_HTTPX = False

from verbatim_app.agent import (  # noqa: E402
    INTERRUPTED, Agent, AgentError, Tool, ToolRefused, http_transport,
)
from verbatim_app.providers import (  # noqa: E402
    ProviderError, Settings, ToolCall, Usage,
)

ANTHROPIC = Settings("anthropic", "claude-opus-5",
                     "https://api.anthropic.com", "sk-test")
OPENAI = Settings("openai", "qwen2.5:14b", "http://127.0.0.1:11434/v1", None)


class Replay:
    """A transport that hands back scripted streams and keeps every request."""

    def __init__(self, *scripts):
        self.scripts = list(scripts)
        self.calls = []

    def __call__(self, url, headers, payload):
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        if not self.scripts:
            raise AssertionError("the loop asked for more turns than scripted")
        return iter(self.scripts.pop(0))


def says(text, stop="end_turn"):
    return [
        'data: {"type":"message_start","message":{"usage":'
        '{"input_tokens":100,"output_tokens":1}}}',
        'data: {"type":"content_block_start","index":0,'
        '"content_block":{"type":"text","text":""}}',
        'data: {"type":"content_block_delta","index":0,"delta":'
        '{"type":"text_delta","text":%s}}' % json.dumps(text),
        'data: {"type":"content_block_stop","index":0}',
        'data: {"type":"message_delta","delta":{"stop_reason":"%s"},'
        '"usage":{"output_tokens":10}}' % stop,
    ]


def asks(*calls):
    """A turn whose only content is tool calls. Each call is (id, name, args)."""
    lines = ['data: {"type":"message_start","message":{"usage":'
             '{"input_tokens":100,"output_tokens":1}}}']
    for index, (call_id, name, arguments) in enumerate(calls):
        lines += [
            'data: {"type":"content_block_start","index":%d,"content_block":'
            '{"type":"tool_use","id":%s,"name":%s,"input":{}}}'
            % (index, json.dumps(call_id), json.dumps(name)),
            'data: {"type":"content_block_delta","index":%d,"delta":'
            '{"type":"input_json_delta","partial_json":%s}}'
            % (index, json.dumps(json.dumps(arguments))),
            'data: {"type":"content_block_stop","index":%d}' % index,
        ]
    lines.append('data: {"type":"message_delta","delta":'
                 '{"stop_reason":"tool_use"},"usage":{"output_tokens":10}}')
    return lines


def echo_tool(seen=None):
    def run(arguments):
        if seen is not None:
            seen.append(arguments)
        return f"read {arguments.get('name', '')}"
    return Tool(name="read_instance", description="Read one file.",
                input_schema={"type": "object",
                              "properties": {"name": {"type": "string"}},
                              "required": ["name"]},
                run=run)


def user(text):
    return [{"role": "user", "content": [{"type": "text", "text": text}]}]


class TestOneTurn(unittest.TestCase):
    def test_a_plain_answer_streams_its_text_then_stops(self):
        transport = Replay(says("Which client, and when?"))
        agent = Agent(ANTHROPIC, tools=[], transport=transport)
        steps = list(agent.run("The step.", user("hello")))
        self.assertEqual("".join(s.text for s in steps if s.kind == "text"),
                         "Which client, and when?")
        self.assertEqual([s.kind for s in steps][-1], "stop")
        self.assertEqual([s.stop for s in steps if s.kind == "stop"],
                         ["end_turn"])

    def test_the_answer_lands_in_the_conversation(self):
        transport = Replay(says("Which client?"))
        messages = user("hello")
        agent = Agent(ANTHROPIC, tools=[], transport=transport)
        list(agent.run("The step.", messages))
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"],
                         [{"type": "text", "text": "Which client?"}])

    def test_the_request_goes_to_the_provider_the_settings_name(self):
        transport = Replay(says("ok"))
        list(Agent(ANTHROPIC, tools=[], transport=transport)
             .run("The step.", user("hello")))
        self.assertEqual(transport.calls[0]["url"],
                         "https://api.anthropic.com/v1/messages")
        self.assertEqual(transport.calls[0]["payload"]["system"], "The step.")

    def test_tools_are_declared_with_their_schema(self):
        transport = Replay(says("ok"))
        list(Agent(ANTHROPIC, tools=[echo_tool()], transport=transport)
             .run("The step.", user("hello")))
        declared = transport.calls[0]["payload"]["tools"]
        self.assertEqual(declared[0]["name"], "read_instance")
        self.assertEqual(declared[0]["input_schema"]["required"], ["name"])

    def test_usage_is_totalled_and_reported(self):
        transport = Replay(says("ok"))
        agent = Agent(ANTHROPIC, tools=[], transport=transport)
        steps = list(agent.run("The step.", user("hello")))
        self.assertEqual(agent.usage, Usage(input_tokens=100, output_tokens=10))
        # Reported as the turn goes; the last one is the turn's figure.
        self.assertEqual([s.usage for s in steps if s.kind == "usage"][-1],
                         Usage(100, 10))

    def test_a_provider_error_is_not_swallowed(self):
        transport = Replay(['data: {"type":"error","error":'
                            '{"type":"overloaded_error","message":"busy"}}'])
        agent = Agent(ANTHROPIC, tools=[], transport=transport)
        with self.assertRaises(ProviderError):
            list(agent.run("The step.", user("hello")))


class TestToolTurn(unittest.TestCase):
    def test_a_tool_call_runs_and_the_loop_goes_round_again(self):
        transport = Replay(asks(("toolu_1", "read_instance", {"name": "voice.md"})),
                           says("Got it."))
        seen = []
        agent = Agent(ANTHROPIC, tools=[echo_tool(seen)], transport=transport)
        steps = list(agent.run("The step.", user("hello")))
        self.assertEqual(seen, [{"name": "voice.md"}])
        self.assertEqual(len(transport.calls), 2)
        kinds = [s.kind for s in steps]
        self.assertEqual(kinds.index("tool_call") + 1, kinds.index("tool_result"))
        self.assertIn("Got it.", "".join(s.text for s in steps))

    def test_the_call_and_its_result_are_both_in_the_conversation(self):
        transport = Replay(asks(("toolu_1", "read_instance", {"name": "voice.md"})),
                           says("Got it."))
        messages = user("hello")
        list(Agent(ANTHROPIC, tools=[echo_tool()], transport=transport)
             .run("The step.", messages))
        assistant = messages[1]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(assistant["content"][-1],
                         {"type": "tool_use", "id": "toolu_1",
                          "name": "read_instance", "input": {"name": "voice.md"}})
        self.assertEqual(messages[2]["content"][0],
                         {"type": "tool_result", "tool_use_id": "toolu_1",
                          "content": "read voice.md", "is_error": False})

    def test_the_second_request_carries_the_result(self):
        transport = Replay(asks(("toolu_1", "read_instance", {"name": "voice.md"})),
                           says("Got it."))
        list(Agent(ANTHROPIC, tools=[echo_tool()], transport=transport)
             .run("The step.", user("hello")))
        sent = transport.calls[1]["payload"]["messages"]
        self.assertEqual(sent[-1]["content"][0]["content"], "read voice.md")

    def test_two_calls_in_one_turn_return_in_a_single_message(self):
        # Splitting parallel results across messages teaches a model to stop
        # asking for them in parallel.
        transport = Replay(asks(("toolu_1", "read_instance", {"name": "voice.md"}),
                                ("toolu_2", "read_instance", {"name": "pillars.md"})),
                           says("Both read."))
        messages = user("hello")
        list(Agent(ANTHROPIC, tools=[echo_tool()], transport=transport)
             .run("The step.", messages))
        results = messages[2]["content"]
        self.assertEqual(len(results), 2)
        self.assertEqual([r["tool_use_id"] for r in results],
                         ["toolu_1", "toolu_2"])

    def test_usage_adds_up_across_turns(self):
        transport = Replay(asks(("toolu_1", "read_instance", {"name": "voice.md"})),
                           says("Got it."))
        agent = Agent(ANTHROPIC, tools=[echo_tool()], transport=transport)
        list(agent.run("The step.", user("hello")))
        self.assertEqual(agent.usage, Usage(input_tokens=200, output_tokens=20))


class TestToolFailure(unittest.TestCase):
    def test_a_tool_that_refuses_reports_instead_of_crashing(self):
        def run(arguments):
            raise ToolRefused("profile.md is not a file this consumer may write")
        tool = Tool(name="write_instance", description="Write one file.",
                    input_schema={"type": "object"}, run=run)
        transport = Replay(asks(("toolu_1", "write_instance", {"name": "x"})),
                           says("Understood."))
        messages = user("hello")
        steps = list(Agent(ANTHROPIC, tools=[tool], transport=transport)
                     .run("The step.", messages))
        result = [s for s in steps if s.kind == "tool_result"][0]
        self.assertTrue(result.is_error)
        self.assertIn("may write", result.result)
        self.assertTrue(messages[2]["content"][0]["is_error"])
        self.assertEqual(len(transport.calls), 2)

    def test_an_unexpected_failure_is_also_handed_back_not_raised(self):
        def run(arguments):
            raise ZeroDivisionError("boom")
        tool = Tool(name="read_instance", description="", input_schema={},
                    run=run)
        transport = Replay(asks(("toolu_1", "read_instance", {})),
                           says("Understood."))
        steps = list(Agent(ANTHROPIC, tools=[tool], transport=transport)
                     .run("The step.", user("hello")))
        result = [s for s in steps if s.kind == "tool_result"][0]
        self.assertTrue(result.is_error)
        self.assertIn("ZeroDivisionError", result.result)

    def test_an_invented_tool_name_is_answered_not_fatal(self):
        # A weaker model invents tool names. That is a turn to recover from,
        # not a crash of somebody's interview.
        transport = Replay(asks(("toolu_1", "delete_everything", {})),
                           says("Sorry."))
        steps = list(Agent(ANTHROPIC, tools=[echo_tool()], transport=transport)
                     .run("The step.", user("hello")))
        result = [s for s in steps if s.kind == "tool_result"][0]
        self.assertTrue(result.is_error)
        self.assertIn("delete_everything", result.result)
        self.assertEqual(len(transport.calls), 2)

    def test_a_tool_returning_something_other_than_text_is_made_text(self):
        tool = Tool(name="read_instance", description="", input_schema={},
                    run=lambda arguments: 42)
        transport = Replay(asks(("toolu_1", "read_instance", {})), says("ok"))
        steps = list(Agent(ANTHROPIC, tools=[tool], transport=transport)
                     .run("The step.", user("hello")))
        self.assertEqual([s for s in steps if s.kind == "tool_result"][0].result,
                         "42")


class TestTheConversationStaysValid(unittest.TestCase):
    """`messages` is written to disk between turns and reopened later, so it
    has to be a conversation a provider would accept at every yield, not only
    at the end. A browser closing mid turn is the normal case."""

    def test_walking_away_mid_turn_leaves_every_call_answered(self):
        transport = Replay(asks(("toolu_1", "read_instance", {"name": "voice.md"}),
                                ("toolu_2", "read_instance", {"name": "pillars.md"})),
                           says("done"))
        messages = user("hello")
        run = Agent(ANTHROPIC, tools=[echo_tool()], transport=transport) \
            .run("The step.", messages)
        for step in run:
            if step.kind == "tool_call":
                break
        run.close()
        calls = [b["id"] for m in messages if m["role"] == "assistant"
                 for b in m["content"] if b["type"] == "tool_use"]
        answered = [b["tool_use_id"] for m in messages if m["role"] == "user"
                    and isinstance(m["content"], list)
                    for b in m["content"] if b.get("type") == "tool_result"]
        self.assertEqual(calls, ["toolu_1", "toolu_2"])
        self.assertEqual(answered, calls)
        self.assertIn(INTERRUPTED, [b["content"] for m in messages
                                    if m["role"] == "user"
                                    and isinstance(m["content"], list)
                                    for b in m["content"]
                                    if b.get("type") == "tool_result"])

    def test_a_turn_that_produced_nothing_leaves_nothing_behind(self):
        # An empty content array is refused on the next request.
        transport = Replay(['data: {"type":"message_start","message":{"usage":'
                            '{"input_tokens":10,"output_tokens":1}}}',
                            'data: {"type":"message_delta","delta":'
                            '{"stop_reason":"end_turn"},"usage":'
                            '{"output_tokens":0}}'])
        messages = user("hello")
        steps = list(Agent(ANTHROPIC, tools=[], transport=transport)
                     .run("The step.", messages))
        self.assertEqual(len(messages), 1)
        self.assertEqual(steps[-1].kind, "stop")

    def test_a_cut_stream_is_reported_as_cut_not_as_an_answer(self):
        transport = Replay(['data: {"type":"content_block_start","index":0,'
                            '"content_block":{"type":"text","text":""}}',
                            'data: {"type":"content_block_delta","index":0,'
                            '"delta":{"type":"text_delta","text":"half a sen"}}'])
        steps = list(Agent(ANTHROPIC, tools=[], transport=transport)
                     .run("The step.", user("hello")))
        self.assertEqual([s.stop for s in steps if s.kind == "stop"],
                         ["truncated"])

    def test_a_call_lost_to_a_cut_stream_is_never_run(self):
        # The tool block opened and the stream died before it closed. Running
        # a call assembled from half its arguments is worse than not running.
        transport = Replay(['data: {"type":"content_block_start","index":0,'
                            '"content_block":{"type":"tool_use","id":"toolu_1",'
                            '"name":"read_instance","input":{}}}',
                            'data: {"type":"content_block_delta","index":0,'
                            '"delta":{"type":"input_json_delta",'
                            '"partial_json":"{\\"name\\":"}}'])
        seen = []
        messages = user("hello")
        steps = list(Agent(ANTHROPIC, tools=[echo_tool(seen)],
                           transport=transport).run("The step.", messages))
        self.assertEqual(seen, [])
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual([s.stop for s in steps if s.kind == "stop"],
                         ["truncated"])

    def test_a_running_total_is_not_added_to_itself(self):
        # A wire reports the total so far for one message. Two reports of the
        # same message are one figure, not two.
        transport = Replay(['data: {"type":"message_start","message":{"usage":'
                            '{"input_tokens":10,"output_tokens":1}}}',
                            'data: {"type":"content_block_start","index":0,'
                            '"content_block":{"type":"text","text":""}}',
                            'data: {"type":"content_block_delta","index":0,'
                            '"delta":{"type":"text_delta","text":"ok"}}',
                            'data: {"type":"message_delta","delta":{},'
                            '"usage":{"output_tokens":5}}',
                            'data: {"type":"message_delta","delta":'
                            '{"stop_reason":"end_turn"},'
                            '"usage":{"output_tokens":9}}'])
        agent = Agent(ANTHROPIC, tools=[], transport=transport)
        list(agent.run("The step.", user("hello")))
        self.assertEqual(agent.usage, Usage(input_tokens=10, output_tokens=9))


class TestCeiling(unittest.TestCase):
    def test_a_loop_that_never_finishes_is_cut_and_says_so(self):
        wants_more = asks(("toolu_1", "read_instance", {"name": "voice.md"}))
        transport = Replay(wants_more, wants_more, wants_more)
        agent = Agent(ANTHROPIC, tools=[echo_tool()], transport=transport,
                      max_turns=3)
        steps = list(agent.run("The step.", user("hello")))
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(steps[-1].kind, "ceiling")
        self.assertIn("3", steps[-1].result)

    def test_a_normal_conversation_never_reaches_the_ceiling(self):
        transport = Replay(says("done"))
        steps = list(Agent(ANTHROPIC, tools=[], transport=transport, max_turns=3)
                     .run("The step.", user("hello")))
        self.assertNotIn("ceiling", [s.kind for s in steps])


class TestTheOtherWire(unittest.TestCase):
    """The loop is written once. Swapping the settings swaps the wire and
    nothing else, which is the whole point of the multi provider decision."""

    def test_the_same_loop_drives_an_openai_endpoint(self):
        transport = Replay(
            ['data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
             '"id":"call_1","function":{"name":"read_instance",'
             '"arguments":"{\\"name\\":\\"voice.md\\"}"}}]}}]}',
             'data: {"choices":[{"index":0,"delta":{},'
             '"finish_reason":"tool_calls"}]}',
             'data: {"usage":{"prompt_tokens":100,"completion_tokens":10}}',
             'data: [DONE]'],
            ['data: {"choices":[{"index":0,"delta":{"content":"Got it."},'
             '"finish_reason":"stop"}]}',
             'data: {"usage":{"prompt_tokens":100,"completion_tokens":10}}',
             'data: [DONE]'])
        seen = []
        agent = Agent(OPENAI, tools=[echo_tool(seen)], transport=transport)
        steps = list(agent.run("The step.", user("hello")))
        self.assertEqual(seen, [{"name": "voice.md"}])
        self.assertIn("Got it.", "".join(s.text for s in steps))
        self.assertEqual(agent.usage, Usage(200, 20))

    def test_the_result_reaches_that_endpoint_in_its_own_shape(self):
        transport = Replay(
            ['data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
             '"id":"call_1","function":{"name":"read_instance",'
             '"arguments":"{\\"name\\":\\"voice.md\\"}"}}]}}]}',
             'data: {"choices":[{"index":0,"delta":{},'
             '"finish_reason":"tool_calls"}]}'],
            ['data: {"choices":[{"index":0,"delta":{"content":"ok"},'
             '"finish_reason":"stop"}]}'])
        list(Agent(OPENAI, tools=[echo_tool()], transport=transport)
             .run("The step.", user("hello")))
        sent = transport.calls[1]["payload"]["messages"]
        self.assertEqual(sent[-1], {"role": "tool", "tool_call_id": "call_1",
                                    "content": "read voice.md"})
        self.assertEqual(transport.calls[1]["url"],
                         "http://127.0.0.1:11434/v1/chat/completions")


@unittest.skipUnless(HAS_HTTPX, "httpx not installed; run this suite through uv")
class TestHttpTransport(unittest.TestCase):
    """The one function here that opens a socket, against a server that
    answers like a provider. Everything else in this file is a recording;
    this is what proves the recording ever reaches the parser."""

    def serve(self, status, lines):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", 0))
                received["body"] = json.loads(self.rfile.read(length))
                received["headers"] = dict(self.headers)
                self.send_response(status)
                self.send_header("content-type", "text/event-stream")
                self.end_headers()
                for line in lines:
                    self.wfile.write((line + "\n\n").encode())
                    self.wfile.flush()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}", received

    def test_a_full_turn_travels_over_real_http(self):
        base, received = self.serve(200, says("Which client, and when?"))
        settings = Settings("anthropic", "claude-opus-5", base, "sk-test")
        agent = Agent(settings, tools=[echo_tool()],
                      transport=http_transport(timeout=10))
        steps = list(agent.run("The step.", user("hello")))
        self.assertEqual("".join(s.text for s in steps if s.kind == "text"),
                         "Which client, and when?")
        self.assertEqual(agent.usage, Usage(100, 10))
        self.assertEqual(received["body"]["model"], "claude-opus-5")
        self.assertEqual(received["headers"]["x-api-key"], "sk-test")

    def test_a_refused_request_says_the_status_and_the_body(self):
        base, _ = self.serve(401, ['{"error":{"message":"invalid key"}}'])
        settings = Settings("anthropic", "claude-opus-5", base, "sk-wrong")
        agent = Agent(settings, tools=[], transport=http_transport(timeout=10))
        with self.assertRaises(AgentError) as caught:
            list(agent.run("The step.", user("hello")))
        self.assertIn("401", str(caught.exception))
        self.assertIn("invalid key", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
