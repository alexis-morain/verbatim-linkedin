"""Tests for the provider seam: configuration, the two wire formats, prices.

No network. Every wire is exercised against a recorded event stream, which is
the only way this can be tested without a key. Those recordings are written
from the published formats, not captured from a live endpoint, so they prove
the parser and not the endpoint. The smoke test per provider is what proves
the endpoint, and it is a manual step before release.

    python3 app/tests/test_providers.py
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))

from verbatim_app.providers import (  # noqa: E402
    AnthropicWire, OpenAIWire, ProviderError, Settings, ToolCall, Usage,
    _join_url, price, problems, read_env_file, resolve, wire_for,
)


def sse(*lines):
    """A recorded stream, as the transport hands it over: one line at a time,
    newlines already stripped."""
    return list(lines)


# The tool the recordings below call, in engine shape.
READ_TOOL = {
    "name": "read_instance",
    "description": "Read one file of the instance.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
}


# ------------------------------------------------------------------- config

class TestEnvFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-env-")
        self.path = Path(self.tmp) / ".env"

    def write(self, text):
        self.path.write_text(text, encoding="utf-8")
        return self.path

    def test_missing_file_is_an_empty_map(self):
        self.assertEqual(read_env_file(Path(self.tmp) / "nope"), {})

    def test_comments_and_blank_lines_are_skipped(self):
        path = self.write("# a comment\n\nVERBATIM_MODEL=gpt-4o\n\n")
        self.assertEqual(read_env_file(path), {"VERBATIM_MODEL": "gpt-4o"})

    def test_export_prefix_and_quotes_come_off(self):
        path = self.write('export VERBATIM_PROVIDER="openai"\n'
                          "VERBATIM_MODEL='qwen2.5:14b'\n")
        self.assertEqual(read_env_file(path),
                         {"VERBATIM_PROVIDER": "openai",
                          "VERBATIM_MODEL": "qwen2.5:14b"})

    def test_an_equals_sign_inside_a_value_survives(self):
        path = self.write("VERBATIM_BASE_URL=http://h/v1?a=b\n")
        self.assertEqual(read_env_file(path)["VERBATIM_BASE_URL"],
                         "http://h/v1?a=b")

    def test_an_empty_value_is_absent_not_empty(self):
        # .env.example ships every key with an empty value. An empty value
        # means "not set", otherwise copying the example blanks the defaults.
        path = self.write("VERBATIM_MODEL=\nVERBATIM_PROVIDER=openai\n")
        self.assertEqual(read_env_file(path), {"VERBATIM_PROVIDER": "openai"})


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-cfg-")
        self.root = Path(self.tmp)

    def env_file(self, text):
        (self.root / ".env").write_text(text, encoding="utf-8")

    def test_bare_instance_defaults_to_the_native_wire(self):
        found = resolve(self.root, {})
        self.assertEqual(found.provider, "anthropic")
        self.assertEqual(found.base_url, "https://api.anthropic.com")
        self.assertEqual(found.model, "claude-opus-5")
        self.assertIsNone(found.api_key)

    def test_the_instance_env_names_the_provider(self):
        self.env_file("VERBATIM_PROVIDER=openai\nVERBATIM_MODEL=qwen2.5:14b\n"
                      "VERBATIM_BASE_URL=http://127.0.0.1:11434/v1\n")
        found = resolve(self.root, {})
        self.assertEqual(found.provider, "openai")
        self.assertEqual(found.model, "qwen2.5:14b")
        self.assertEqual(found.base_url, "http://127.0.0.1:11434/v1")

    def test_openai_has_no_default_model(self):
        self.env_file("VERBATIM_PROVIDER=openai\n")
        self.assertEqual(resolve(self.root, {}).model, "")

    def test_the_process_environment_overrides_the_instance_file(self):
        self.env_file("VERBATIM_MODEL=claude-opus-5\n")
        found = resolve(self.root, {"VERBATIM_MODEL": "claude-haiku-4-5"})
        self.assertEqual(found.model, "claude-haiku-4-5")

    def test_a_key_in_the_instance_file_stops_everything(self):
        self.env_file("VERBATIM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-real\n")
        with self.assertRaises(ProviderError) as caught:
            resolve(self.root, {})
        message = str(caught.exception)
        self.assertIn("ANTHROPIC_API_KEY", message)
        self.assertIn(str(self.root / ".env"), message)

    def test_the_refusal_never_repeats_the_secret(self):
        self.env_file("OPENAI_API_KEY=sk-do-not-print-me\n")
        with self.assertRaises(ProviderError) as caught:
            resolve(self.root, {})
        self.assertNotIn("sk-do-not-print-me", str(caught.exception))

    def test_any_key_shaped_name_is_refused_not_just_the_known_ones(self):
        self.env_file("MISTRAL_API_TOKEN=abc\n")
        with self.assertRaises(ProviderError):
            resolve(self.root, {})

    def test_the_key_comes_from_the_process_environment(self):
        found = resolve(self.root, {"ANTHROPIC_API_KEY": "sk-ant"})
        self.assertEqual(found.api_key, "sk-ant")

    def test_the_generic_key_wins_over_the_provider_one(self):
        found = resolve(self.root, {"ANTHROPIC_API_KEY": "sk-ant",
                                    "VERBATIM_API_KEY": "sk-any"})
        self.assertEqual(found.api_key, "sk-any")

    def test_the_openai_provider_reads_its_own_key(self):
        self.env_file("VERBATIM_PROVIDER=openai\n")
        found = resolve(self.root, {"OPENAI_API_KEY": "sk-oai",
                                    "ANTHROPIC_API_KEY": "sk-ant"})
        self.assertEqual(found.api_key, "sk-oai")


class TestTheEndpointIsNotTrustedEither(unittest.TestCase):
    """The instance file is not trusted to hold a key. It is therefore not
    trusted to decide where the key is sent, which is the same statement and
    the easier half to forget."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-trust-")
        self.root = Path(self.tmp)

    def env_file(self, text):
        (self.root / ".env").write_text(text, encoding="utf-8")

    def test_the_instance_file_cannot_send_the_key_somewhere_else(self):
        self.env_file("VERBATIM_BASE_URL=https://collector.attacker.example\n")
        with self.assertRaises(ProviderError) as caught:
            resolve(self.root, {"ANTHROPIC_API_KEY": "sk-real"})
        message = str(caught.exception)
        self.assertIn("collector.attacker.example", message)
        self.assertNotIn("sk-real", message)

    def test_with_no_key_there_is_nothing_to_leak_and_nothing_to_refuse(self):
        self.env_file("VERBATIM_BASE_URL=https://collector.attacker.example\n")
        self.assertEqual(resolve(self.root, {}).base_url,
                         "https://collector.attacker.example")

    def test_an_endpoint_you_exported_yourself_is_trusted(self):
        self.env_file("VERBATIM_BASE_URL=https://collector.attacker.example\n")
        found = resolve(self.root, {"ANTHROPIC_API_KEY": "sk-real",
                                    "VERBATIM_BASE_URL": "https://openrouter.ai/api/v1"})
        self.assertEqual(found.base_url, "https://openrouter.ai/api/v1")

    def test_a_runtime_on_this_machine_is_trusted(self):
        self.env_file("VERBATIM_PROVIDER=openai\n"
                      "VERBATIM_BASE_URL=http://127.0.0.1:11434/v1\n")
        found = resolve(self.root, {"OPENAI_API_KEY": "sk-real"})
        self.assertEqual(found.api_key, "sk-real")

    def test_the_provider_own_endpoint_is_trusted(self):
        self.env_file("VERBATIM_BASE_URL=https://api.anthropic.com\n")
        self.assertEqual(resolve(self.root, {"ANTHROPIC_API_KEY": "sk"}).api_key,
                         "sk")

    def test_an_endpoint_exported_empty_does_not_disarm_the_guard(self):
        # Sourcing the shipped .env.example exports every key it names as an
        # empty string. Testing for the name alone would switch the guard off
        # for exactly the person who followed the documentation.
        self.env_file("VERBATIM_BASE_URL=https://collector.attacker.example\n")
        with self.assertRaises(ProviderError):
            resolve(self.root, {"ANTHROPIC_API_KEY": "sk-real",
                                "VERBATIM_BASE_URL": ""})

    def test_the_instance_cannot_downgrade_the_transport(self):
        self.env_file("VERBATIM_BASE_URL=http://api.anthropic.com/v1\n")
        with self.assertRaises(ProviderError) as caught:
            resolve(self.root, {"ANTHROPIC_API_KEY": "sk-real"})
        self.assertIn("clear text", str(caught.exception))

    def test_the_provider_name_on_another_port_is_another_endpoint(self):
        self.env_file("VERBATIM_BASE_URL=https://api.anthropic.com:8443\n")
        with self.assertRaises(ProviderError):
            resolve(self.root, {"ANTHROPIC_API_KEY": "sk-real"})

    def test_the_default_port_written_out_is_still_the_default(self):
        self.env_file("VERBATIM_BASE_URL=https://api.anthropic.com:443\n")
        self.assertEqual(resolve(self.root, {"ANTHROPIC_API_KEY": "sk"}).api_key,
                         "sk")

    def test_an_unknown_provider_is_named_as_such_not_as_a_scheme(self):
        # The complaint has to point at the real problem, and problems() is
        # what names it.
        found = resolve(self.root, {"VERBATIM_PROVIDER": "gemini",
                                    "VERBATIM_API_KEY": "sk"})
        self.assertIn("provider-unknown", [p.code for p in problems(found)])

    def test_the_instance_cannot_grant_itself_an_allowance(self):
        self.env_file("VERBATIM_BASE_URL=https://evil.example\n"
                      "VERBATIM_ENDPOINT_OK=evil.example\n")
        with self.assertRaises(ProviderError):
            resolve(self.root, {"ANTHROPIC_API_KEY": "sk-real"})

    def test_a_third_party_host_can_be_allowed_next_to_the_key(self):
        self.env_file("VERBATIM_PROVIDER=openai\n"
                      "VERBATIM_BASE_URL=https://openrouter.ai/api/v1\n")
        found = resolve(self.root, {"OPENAI_API_KEY": "sk-real",
                                    "VERBATIM_ENDPOINT_OK": "openrouter.ai"})
        self.assertEqual(found.base_url, "https://openrouter.ai/api/v1")

    def test_the_allow_list_holds_several_hosts(self):
        self.env_file("VERBATIM_PROVIDER=openai\n"
                      "VERBATIM_BASE_URL=https://api.mistral.ai/v1\n")
        found = resolve(self.root, {"OPENAI_API_KEY": "sk",
                                    "VERBATIM_ENDPOINT_OK": "openrouter.ai, api.mistral.ai"})
        self.assertEqual(found.base_url, "https://api.mistral.ai/v1")


class TestSecretsSmuggledPastTheNameCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="verbatim-smuggle-")
        self.root = Path(self.tmp)

    def env_file(self, text):
        (self.root / ".env").write_text(text, encoding="utf-8")

    def test_a_commented_out_key_is_still_a_key_in_a_committed_file(self):
        self.env_file("# ANTHROPIC_API_KEY=sk-real-key-here\n")
        with self.assertRaises(ProviderError):
            resolve(self.root, {})

    def test_prose_about_keys_is_not_a_key(self):
        # The sentence somebody writes after being told to keep keys
        # elsewhere. Refusing it would stop their app over a comment.
        self.env_file("# Keys live in my shell profile, not here.\n"
                      "# Key: use the small model on this instance.\n"
                      "VERBATIM_PROVIDER=openai\n")
        self.assertEqual(resolve(self.root, {}).provider, "openai")

    def test_the_shipped_example_can_be_copied_into_an_instance(self):
        # .env.example names all three key variables, with empty values, and
        # its first line invites copying it. Refusing that would be absurd.
        shipped = (Path(__file__).resolve().parents[2] / ".env.example")
        self.env_file(shipped.read_text(encoding="utf-8"))
        resolve(self.root, {})

    def test_a_credential_in_lower_case_is_still_a_credential(self):
        for line in ("anthropic_api_key=sk-real\n",
                     "Anthropic_Api_Key=sk-real\n",
                     "ANTHROPIC-API-KEY=sk-real\n",
                     "_OPENAI_API_KEY=sk-real\n"):
            with self.subTest(line=line):
                self.env_file(line)
                with self.assertRaises(ProviderError):
                    resolve(self.root, {})

    def test_an_empty_placeholder_is_not_a_credential(self):
        self.env_file("ANTHROPIC_API_KEY=\nVERBATIM_PROVIDER=openai\n")
        self.assertEqual(resolve(self.root, {}).provider, "openai")

    def test_a_credential_hidden_in_the_endpoint_userinfo_is_caught(self):
        self.env_file("VERBATIM_BASE_URL=https://sk-live-abc:x@proxy.example/v1\n")
        with self.assertRaises(ProviderError) as caught:
            resolve(self.root, {})
        self.assertNotIn("sk-live-abc", str(caught.exception))

    def test_a_credential_hidden_in_the_query_string_is_caught(self):
        self.env_file("VERBATIM_BASE_URL=https://openrouter.ai/v1?api_key=sk-or\n")
        with self.assertRaises(ProviderError):
            resolve(self.root, {})


class TestJoinUrl(unittest.TestCase):
    def test_a_base_url_that_already_ends_in_the_segment_does_not_repeat_it(self):
        self.assertEqual(_join_url("https://api.anthropic.com/v1", "/v1/messages"),
                         "https://api.anthropic.com/v1/messages")

    def test_a_plain_base_url_still_gets_the_whole_path(self):
        self.assertEqual(_join_url("https://api.anthropic.com", "/v1/messages"),
                         "https://api.anthropic.com/v1/messages")

    def test_the_chat_endpoint_keeps_its_own_convention(self):
        self.assertEqual(_join_url("http://127.0.0.1:11434/v1", "/chat/completions"),
                         "http://127.0.0.1:11434/v1/chat/completions")

    def test_a_query_string_stays_a_query_string(self):
        # A gateway carrying its tenant or api-version in the query would
        # otherwise get the path appended inside it.
        self.assertEqual(_join_url("https://gw.example/v1?tenant=a",
                                   "/v1/messages"),
                         "https://gw.example/v1/messages?tenant=a")

    def test_only_a_repeated_segment_comes_off(self):
        self.assertEqual(_join_url("https://gw.example/anthropic/v1",
                                   "/v1/messages"),
                         "https://gw.example/anthropic/v1/messages")


class TestProblems(unittest.TestCase):
    def test_a_configured_instance_has_none(self):
        found = Settings(provider="anthropic", model="claude-opus-5",
                         base_url="https://api.anthropic.com", api_key="sk-ant")
        self.assertEqual(problems(found), [])

    def test_a_missing_model_is_reported_not_guessed(self):
        found = Settings(provider="openai", model="",
                         base_url="http://127.0.0.1:11434/v1", api_key=None)
        self.assertIn("model-missing", [p.code for p in problems(found)])

    def test_a_missing_key_is_reported_for_a_hosted_endpoint(self):
        found = Settings(provider="anthropic", model="claude-opus-5",
                         base_url="https://api.anthropic.com", api_key=None)
        self.assertIn("key-missing", [p.code for p in problems(found)])

    def test_a_loopback_endpoint_needs_no_key(self):
        found = Settings(provider="openai", model="qwen2.5:14b",
                         base_url="http://127.0.0.1:11434/v1", api_key=None)
        self.assertEqual([p.code for p in problems(found)], [])

    def test_an_unknown_provider_is_reported(self):
        found = Settings(provider="gemini", model="x",
                         base_url="http://h", api_key="k")
        self.assertIn("provider-unknown", [p.code for p in problems(found)])


# ------------------------------------------------------------------- prices

class TestPrice(unittest.TestCase):
    def test_a_known_model_is_priced(self):
        cost = price("claude-opus-5", Usage(input_tokens=1_000_000,
                                            output_tokens=1_000_000))
        self.assertAlmostEqual(cost, 30.0)

    def test_an_unknown_model_has_no_price_and_that_is_not_zero(self):
        # Tokens are always shown; a price is shown only when it is known.
        # Returning 0.0 here would print "0.00 EUR" over a real bill.
        self.assertIsNone(price("qwen2.5:14b", Usage(1_000, 1_000)))

    def test_usage_adds_up(self):
        total = Usage(10, 20) + Usage(1, 2)
        self.assertEqual((total.input_tokens, total.output_tokens), (11, 22))


# ----------------------------------------------------------- anthropic wire

ANTHROPIC_TEXT = sse(
    'event: message_start',
    'data: {"type":"message_start","message":{"id":"msg_1","usage":'
    '{"input_tokens":412,"output_tokens":1}}}',
    '',
    'event: content_block_start',
    'data: {"type":"content_block_start","index":0,'
    '"content_block":{"type":"text","text":""}}',
    '',
    'event: content_block_delta',
    'data: {"type":"content_block_delta","index":0,'
    '"delta":{"type":"text_delta","text":"Which client"}}',
    '',
    'event: content_block_delta',
    'data: {"type":"content_block_delta","index":0,'
    '"delta":{"type":"text_delta","text":", and when?"}}',
    '',
    'event: content_block_stop',
    'data: {"type":"content_block_stop","index":0}',
    '',
    'event: message_delta',
    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
    '"usage":{"output_tokens":9}}',
    '',
    'event: message_stop',
    'data: {"type":"message_stop"}',
)

ANTHROPIC_TOOL = sse(
    'data: {"type":"message_start","message":{"id":"msg_2","usage":'
    '{"input_tokens":500,"output_tokens":1}}}',
    'data: {"type":"content_block_start","index":0,'
    '"content_block":{"type":"text","text":""}}',
    'data: {"type":"content_block_delta","index":0,'
    '"delta":{"type":"text_delta","text":"Let me read the voice file."}}',
    'data: {"type":"content_block_stop","index":0}',
    'data: {"type":"content_block_start","index":1,"content_block":'
    '{"type":"tool_use","id":"toolu_01","name":"read_instance","input":{}}}',
    'data: {"type":"content_block_delta","index":1,'
    '"delta":{"type":"input_json_delta","partial_json":"{\\"name\\":"}}',
    'data: {"type":"content_block_delta","index":1,'
    '"delta":{"type":"input_json_delta","partial_json":" \\"voice.md\\"}"}}',
    'data: {"type":"content_block_stop","index":1}',
    'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},'
    '"usage":{"output_tokens":40}}',
    'data: {"type":"message_stop"}',
)


class TestAnthropicWire(unittest.TestCase):
    def setUp(self):
        self.wire = AnthropicWire()
        self.settings = Settings("anthropic", "claude-opus-5",
                                 "https://api.anthropic.com", "sk-ant")

    def test_the_url_is_the_messages_endpoint(self):
        self.assertEqual(self.wire.url(self.settings),
                         "https://api.anthropic.com/v1/messages")

    def test_a_trailing_slash_on_the_base_url_does_not_double(self):
        settings = Settings("anthropic", "m", "https://api.anthropic.com/", None)
        self.assertEqual(self.wire.url(settings),
                         "https://api.anthropic.com/v1/messages")

    def test_the_key_travels_in_the_native_header(self):
        headers = self.wire.headers(self.settings)
        self.assertEqual(headers["x-api-key"], "sk-ant")
        self.assertIn("anthropic-version", headers)
        self.assertNotIn("Authorization", headers)

    def test_no_key_means_no_header_rather_than_an_empty_one(self):
        settings = Settings("anthropic", "m", "https://api.anthropic.com", None)
        self.assertNotIn("x-api-key", self.wire.headers(settings))

    def test_the_payload_keeps_the_engine_shape(self):
        body = self.wire.payload(
            self.settings,
            system="The step.",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "hello"}]}],
            tools=[READ_TOOL], max_tokens=4096)
        self.assertEqual(body["model"], "claude-opus-5")
        self.assertEqual(body["system"], "The step.")
        self.assertTrue(body["stream"])
        self.assertEqual(body["max_tokens"], 4096)
        self.assertEqual(body["tools"][0]["name"], "read_instance")
        self.assertEqual(body["tools"][0]["input_schema"],
                         READ_TOOL["input_schema"])
        self.assertEqual(body["messages"][0]["role"], "user")

    def test_no_tool_key_when_there_are_no_tools(self):
        body = self.wire.payload(self.settings, system="s", messages=[], tools=[],
                                 max_tokens=10)
        self.assertNotIn("tools", body)

    def test_a_required_tool_is_named_in_the_body(self):
        # The mechanism that replaces asking a model nicely: the app says
        # which tool this turn produces, in the wire's own words.
        body = self.wire.payload(self.settings, system="s", messages=[],
                                 tools=[READ_TOOL], max_tokens=10,
                                 require="read_instance")
        self.assertEqual(body["tool_choice"],
                         {"type": "tool", "name": "read_instance"})

    def test_no_choice_key_when_nothing_is_required(self):
        body = self.wire.payload(self.settings, system="s", messages=[],
                                 tools=[READ_TOOL], max_tokens=10)
        self.assertNotIn("tool_choice", body)

    def test_a_required_tool_without_tools_is_not_sent(self):
        # A choice naming a tool the body does not declare is a 400 on every
        # endpoint. Dropping the key beats sending a request nobody accepts.
        body = self.wire.payload(self.settings, system="s", messages=[],
                                 tools=[], max_tokens=10,
                                 require="read_instance")
        self.assertNotIn("tool_choice", body)

    def test_text_deltas_arrive_in_order_with_usage_and_stop(self):
        events = list(self.wire.events(ANTHROPIC_TEXT))
        text = "".join(e.text for e in events if e.kind == "text")
        self.assertEqual(text, "Which client, and when?")
        # Reported as it goes, so the last one is the turn's figure.
        usage = [e.usage for e in events if e.kind == "usage"]
        self.assertEqual(usage[-1], Usage(input_tokens=412, output_tokens=9))
        self.assertEqual([e.stop for e in events if e.kind == "stop"],
                         ["end_turn"])

    def test_a_tool_call_is_assembled_from_its_json_fragments(self):
        events = list(self.wire.events(ANTHROPIC_TOOL))
        calls = [e.call for e in events if e.kind == "tool_call"]
        self.assertEqual(calls, [ToolCall(id="toolu_01", name="read_instance",
                                          arguments={"name": "voice.md"})])
        self.assertEqual([e.stop for e in events if e.kind == "stop"],
                         ["tool_use"])

    def test_the_tool_call_is_yielded_after_the_text_that_precedes_it(self):
        kinds = [e.kind for e in self.wire.events(ANTHROPIC_TOOL)]
        self.assertLess(kinds.index("text"), kinds.index("tool_call"))

    def test_a_refusal_is_a_stop_reason_of_its_own(self):
        stream = sse('data: {"type":"message_delta","delta":'
                     '{"stop_reason":"refusal"},"usage":{"output_tokens":0}}')
        events = list(self.wire.events(stream))
        self.assertEqual([e.stop for e in events if e.kind == "stop"],
                         ["refusal"])

    def test_a_malformed_data_line_is_not_swallowed(self):
        with self.assertRaises(ProviderError):
            list(self.wire.events(sse("data: {not json")))

    def test_an_api_error_event_becomes_an_error(self):
        stream = sse('event: error',
                     'data: {"type":"error","error":{"type":"overloaded_error",'
                     '"message":"Overloaded"}}')
        with self.assertRaises(ProviderError) as caught:
            list(self.wire.events(stream))
        self.assertIn("Overloaded", str(caught.exception))


# -------------------------------------------------------------- openai wire

OPENAI_TEXT = sse(
    'data: {"choices":[{"index":0,"delta":{"role":"assistant","content":""}}]}',
    'data: {"choices":[{"index":0,"delta":{"content":"Which client"}}]}',
    'data: {"choices":[{"index":0,"delta":{"content":", and when?"}}]}',
    'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
    'data: {"choices":[],"usage":{"prompt_tokens":412,"completion_tokens":9}}',
    'data: [DONE]',
)

OPENAI_TOOL = sse(
    'data: {"choices":[{"index":0,"delta":{"content":"Let me read it."}}]}',
    'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
    '"id":"call_01","type":"function","function":'
    '{"name":"read_instance","arguments":""}}]}}]}',
    'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
    '"function":{"arguments":"{\\"name\\":"}}]}}]}',
    'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
    '"function":{"arguments":" \\"voice.md\\"}"}}]}}]}',
    'data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}',
    'data: {"usage":{"prompt_tokens":500,"completion_tokens":40}}',
    'data: [DONE]',
)


class TestOpenAIWire(unittest.TestCase):
    def setUp(self):
        self.wire = OpenAIWire()
        self.settings = Settings("openai", "gpt-4o",
                                 "https://api.openai.com/v1", "sk-oai")

    def test_the_url_is_the_chat_endpoint(self):
        self.assertEqual(self.wire.url(self.settings),
                         "https://api.openai.com/v1/chat/completions")

    def test_the_key_travels_as_a_bearer(self):
        headers = self.wire.headers(self.settings)
        self.assertEqual(headers["Authorization"], "Bearer sk-oai")

    def test_a_local_runtime_without_a_key_gets_no_authorization(self):
        settings = Settings("openai", "qwen2.5:14b",
                            "http://127.0.0.1:11434/v1", None)
        self.assertNotIn("Authorization", self.wire.headers(settings))

    def test_the_system_block_becomes_the_first_message(self):
        body = self.wire.payload(
            self.settings,
            system="The step.",
            messages=[{"role": "user",
                       "content": [{"type": "text", "text": "hello"}]}],
            tools=[], max_tokens=100)
        self.assertEqual(body["messages"][0],
                         {"role": "system", "content": "The step."})
        self.assertEqual(body["messages"][1],
                         {"role": "user", "content": "hello"})

    def test_usage_is_asked_for_explicitly(self):
        body = self.wire.payload(self.settings, system="s", messages=[], tools=[],
                                 max_tokens=10)
        self.assertEqual(body["stream_options"], {"include_usage": True})

    def test_a_required_tool_is_named_as_a_function(self):
        body = self.wire.payload(self.settings, system="s", messages=[],
                                 tools=[READ_TOOL], max_tokens=10,
                                 require="read_instance")
        self.assertEqual(
            body["tool_choice"],
            {"type": "function", "function": {"name": "read_instance"}})

    def test_no_choice_key_when_nothing_is_required(self):
        body = self.wire.payload(self.settings, system="s", messages=[],
                                 tools=[READ_TOOL], max_tokens=10)
        self.assertNotIn("tool_choice", body)

    def test_a_required_tool_without_tools_is_not_sent(self):
        body = self.wire.payload(self.settings, system="s", messages=[],
                                 tools=[], max_tokens=10,
                                 require="read_instance")
        self.assertNotIn("tool_choice", body)

    def test_a_tool_definition_is_wrapped_as_a_function(self):
        body = self.wire.payload(self.settings, system="s", messages=[], tools=[READ_TOOL],
                                 max_tokens=10)
        self.assertEqual(body["tools"][0]["type"], "function")
        self.assertEqual(body["tools"][0]["function"]["name"], "read_instance")
        self.assertEqual(body["tools"][0]["function"]["parameters"],
                         READ_TOOL["input_schema"])

    def test_an_assistant_tool_use_becomes_a_tool_calls_message(self):
        body = self.wire.payload(
            self.settings,
            system="s", tools=[], max_tokens=10,
            messages=[{"role": "assistant", "content": [
                {"type": "text", "text": "Let me read it."},
                {"type": "tool_use", "id": "call_01", "name": "read_instance",
                 "input": {"name": "voice.md"}}]}])
        message = body["messages"][1]
        self.assertEqual(message["role"], "assistant")
        self.assertEqual(message["content"], "Let me read it.")
        self.assertEqual(message["tool_calls"][0]["id"], "call_01")
        self.assertEqual(
            json.loads(message["tool_calls"][0]["function"]["arguments"]),
            {"name": "voice.md"})

    def test_calls_without_text_carry_a_null_content(self):
        # A strict implementation refuses an empty string next to tool_calls.
        body = self.wire.payload(
            self.settings, system="s", tools=[], max_tokens=10,
            messages=[{"role": "assistant", "content": [
                {"type": "tool_use", "id": "call_01", "name": "read_instance",
                 "input": {}}]}])
        self.assertIsNone(body["messages"][1]["content"])

    def test_an_assistant_saying_nothing_at_all_keeps_an_empty_string(self):
        body = self.wire.payload(
            self.settings, system="s", tools=[], max_tokens=10,
            messages=[{"role": "assistant", "content": []}])
        self.assertEqual(body["messages"][1]["content"], "")

    def test_each_tool_result_becomes_its_own_tool_message(self):
        body = self.wire.payload(
            self.settings,
            system="s", tools=[], max_tokens=10,
            messages=[{"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "call_01",
                 "content": "a file"},
                {"type": "tool_result", "tool_use_id": "call_02",
                 "content": "boom", "is_error": True}]}])
        results = [m for m in body["messages"] if m["role"] == "tool"]
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0],
                         {"role": "tool", "tool_call_id": "call_01",
                          "content": "a file"})
        self.assertIn("boom", results[1]["content"])

    def test_text_deltas_arrive_in_order_with_usage_and_stop(self):
        events = list(self.wire.events(OPENAI_TEXT))
        text = "".join(e.text for e in events if e.kind == "text")
        self.assertEqual(text, "Which client, and when?")
        self.assertEqual([e.usage for e in events if e.kind == "usage"],
                         [Usage(input_tokens=412, output_tokens=9)])
        self.assertEqual([e.stop for e in events if e.kind == "stop"],
                         ["end_turn"])

    def test_a_tool_call_is_assembled_across_chunks_by_index(self):
        events = list(self.wire.events(OPENAI_TOOL))
        calls = [e.call for e in events if e.kind == "tool_call"]
        self.assertEqual(calls, [ToolCall(id="call_01", name="read_instance",
                                          arguments={"name": "voice.md"})])
        self.assertEqual([e.stop for e in events if e.kind == "stop"],
                         ["tool_use"])

    def test_two_parallel_calls_keep_their_own_arguments(self):
        stream = sse(
            'data: {"choices":[{"index":0,"delta":{"tool_calls":['
            '{"index":0,"id":"call_a","function":{"name":"read_instance",'
            '"arguments":"{\\"name\\":\\"voice.md\\"}"}},'
            '{"index":1,"id":"call_b","function":{"name":"read_instance",'
            '"arguments":"{\\"name\\":\\"pillars.md\\"}"}}]}}]}',
            'data: {"choices":[{"index":0,"delta":{},'
            '"finish_reason":"tool_calls"}]}',
            'data: [DONE]')
        calls = [e.call for e in self.wire.events(stream) if e.kind == "tool_call"]
        self.assertEqual([c.arguments["name"] for c in calls],
                         ["voice.md", "pillars.md"])

    def test_a_stream_that_never_reports_usage_simply_has_none(self):
        # Several local runtimes drop the usage chunk. Tokens then read zero
        # and the screen says so; it is not an error.
        stream = sse('data: {"choices":[{"index":0,"delta":'
                     '{"content":"ok"},"finish_reason":"stop"}]}',
                     'data: [DONE]')
        events = list(self.wire.events(stream))
        self.assertEqual([e for e in events if e.kind == "usage"], [])

    def test_empty_arguments_parse_as_an_empty_object(self):
        stream = sse(
            'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
            '"id":"call_x","function":{"name":"list_posts","arguments":""}}]}}]}',
            'data: {"choices":[{"index":0,"delta":{},'
            '"finish_reason":"tool_calls"}]}')
        calls = [e.call for e in self.wire.events(stream) if e.kind == "tool_call"]
        self.assertEqual(calls[0].arguments, {})

    def test_arguments_that_are_not_json_are_an_error_not_a_guess(self):
        stream = sse(
            'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,'
            '"id":"call_x","function":{"name":"read_instance",'
            '"arguments":"voice.md"}}]}}]}',
            'data: {"choices":[{"index":0,"delta":{},'
            '"finish_reason":"tool_calls"}]}')
        with self.assertRaises(ProviderError):
            list(self.wire.events(stream))

    def test_a_length_stop_is_reported_as_such(self):
        stream = sse('data: {"choices":[{"index":0,"delta":{},'
                     '"finish_reason":"length"}]}')
        events = list(self.wire.events(stream))
        self.assertEqual([e.stop for e in events if e.kind == "stop"],
                         ["max_tokens"])

    def test_an_error_payload_becomes_an_error(self):
        stream = sse('data: {"error":{"message":"model not found",'
                     '"type":"invalid_request_error"}}')
        with self.assertRaises(ProviderError) as caught:
            list(self.wire.events(stream))
        self.assertIn("model not found", str(caught.exception))


class TestACutStreamIsNotAnAnswer(unittest.TestCase):
    """A stream that stops without saying why must not read as a clean end of
    turn. Storing half a sentence as the whole one is the silent failure."""

    def test_the_native_wire_says_nothing_rather_than_end_turn(self):
        stream = sse('data: {"type":"message_start","message":{"usage":'
                     '{"input_tokens":10,"output_tokens":1}}}',
                     'data: {"type":"content_block_start","index":0,'
                     '"content_block":{"type":"text","text":""}}',
                     'data: {"type":"content_block_delta","index":0,'
                     '"delta":{"type":"text_delta","text":"half a sen"}}')
        events = list(AnthropicWire().events(stream))
        self.assertEqual([e for e in events if e.kind == "stop"], [])

    def test_the_chat_wire_says_nothing_rather_than_end_turn(self):
        # No finish_reason and no end marker either: the connection died.
        stream = sse('data: {"choices":[{"index":0,"delta":'
                     '{"content":"half a sen"}}]}')
        events = list(OpenAIWire().events(stream))
        self.assertEqual([e for e in events if e.kind == "stop"], [])

    def test_a_cut_native_stream_still_reports_what_it_billed(self):
        # The closing event never arrives, but those input tokens were paid
        # for and silence would read as a free turn.
        stream = sse('data: {"type":"message_start","message":{"usage":'
                     '{"input_tokens":412,"output_tokens":1}}}',
                     'data: {"type":"content_block_delta","index":0,'
                     '"delta":{"type":"text_delta","text":"half"}}')
        usage = [e.usage for e in AnthropicWire().events(stream)
                 if e.kind == "usage"]
        self.assertEqual(usage[-1].input_tokens, 412)

    def test_a_native_tool_block_without_an_id_still_gets_one(self):
        stream = sse('data: {"type":"content_block_start","index":0,'
                     '"content_block":{"type":"tool_use","id":"",'
                     '"name":"read_instance","input":{}}}',
                     'data: {"type":"content_block_stop","index":0}')
        call = [e.call for e in AnthropicWire().events(stream)][0]
        self.assertTrue(call.id)

    def test_a_chat_call_without_an_id_still_gets_one(self):
        stream = sse('data: {"choices":[{"index":0,"delta":{"tool_calls":'
                     '[{"index":0,"function":{"name":"read_instance",'
                     '"arguments":"{}"}}]}}]}',
                     'data: {"choices":[{"index":0,"delta":{},'
                     '"finish_reason":"tool_calls"}]}')
        call = [e.call for e in OpenAIWire().events(stream) if e.kind == "tool_call"][0]
        self.assertTrue(call.id)

    def test_one_unindexed_call_split_across_chunks_stays_one_call(self):
        # The common shape when a runtime omits index: only the opening
        # fragment carries the name and the id, the rest carry arguments.
        stream = sse('data: {"choices":[{"index":0,"delta":{"tool_calls":['
                     '{"id":"call_a","function":{"name":"read_instance",'
                     '"arguments":"{\\"name\\":"}}]}}]}',
                     'data: {"choices":[{"index":0,"delta":{"tool_calls":['
                     '{"function":{"arguments":" \\"voice.md\\"}"}}]}}]}',
                     'data: {"choices":[{"index":0,"delta":{},'
                     '"finish_reason":"tool_calls"}]}')
        calls = [e.call for e in OpenAIWire().events(stream)
                 if e.kind == "tool_call"]
        self.assertEqual(calls, [ToolCall(id="call_a", name="read_instance",
                                          arguments={"name": "voice.md"})])

    def test_an_indexed_opener_owns_the_unindexed_continuation(self):
        # A runtime that indexes the first fragment and leaves it off the
        # ones carrying arguments. The last of the mixed shapes.
        stream = sse('data: {"choices":[{"index":0,"delta":{"tool_calls":['
                     '{"index":0,"id":"a","function":{"name":"f",'
                     '"arguments":"{\\"x\\":"}}]}}]}',
                     'data: {"choices":[{"index":0,"delta":{"tool_calls":['
                     '{"function":{"arguments":"1}"}}]}}]}',
                     'data: {"choices":[{"index":0,"delta":{},'
                     '"finish_reason":"tool_calls"}]}')
        calls = [e.call for e in OpenAIWire().events(stream)
                 if e.kind == "tool_call"]
        self.assertEqual(calls, [ToolCall(id="a", name="f",
                                          arguments={"x": 1})])

    def test_an_unindexed_fragment_never_collides_with_a_real_index(self):
        stream = sse('data: {"choices":[{"index":0,"delta":{"tool_calls":['
                     '{"index":1,"id":"a","function":{"name":"f",'
                     '"arguments":"{\\"x\\":1}"}},'
                     '{"function":{"name":"g","arguments":"{\\"y\\":2}"}}]}}]}',
                     'data: {"choices":[{"index":0,"delta":{},'
                     '"finish_reason":"tool_calls"}]}')
        calls = [e.call for e in OpenAIWire().events(stream)
                 if e.kind == "tool_call"]
        self.assertEqual(sorted(c.name for c in calls), ["f", "g"])
        self.assertEqual(len({c.id for c in calls}), 2)

    def test_a_made_up_id_never_shadows_a_real_one(self):
        stream = sse('data: {"choices":[{"index":0,"delta":{"tool_calls":['
                     '{"index":0,"function":{"name":"f","arguments":"{}"}},'
                     '{"index":1,"id":"unnamed-0","function":{"name":"g",'
                     '"arguments":"{}"}}]}}]}',
                     'data: {"choices":[{"index":0,"delta":{},'
                     '"finish_reason":"tool_calls"}]}')
        calls = [e.call for e in OpenAIWire().events(stream)
                 if e.kind == "tool_call"]
        self.assertEqual(len({c.id for c in calls}), 2)

    def test_a_clean_end_without_a_stated_reason_is_still_an_end(self):
        # A runtime that forgets finish_reason but closes the stream on
        # purpose. Its completed calls must survive.
        stream = sse('data: {"choices":[{"index":0,"delta":{"tool_calls":['
                     '{"index":0,"id":"c1","function":{"name":"f",'
                     '"arguments":"{}"}}]}}]}',
                     'data: {"usage":{"prompt_tokens":1,"completion_tokens":1}}',
                     'data: [DONE]')
        events = list(OpenAIWire().events(stream))
        self.assertEqual([e.stop for e in events if e.kind == "stop"],
                         ["tool_use"])
        self.assertEqual(len([e for e in events if e.kind == "tool_call"]), 1)

    def test_calls_without_an_index_field_do_not_merge_into_one(self):
        # A runtime that copied the format without index is exactly the kind
        # this wire exists to serve.
        stream = sse('data: {"choices":[{"index":0,"delta":{"tool_calls":['
                     '{"id":"call_a","function":{"name":"read_instance",'
                     '"arguments":"{\\"name\\":\\"voice.md\\"}"}},'
                     '{"id":"call_b","function":{"name":"read_instance",'
                     '"arguments":"{\\"name\\":\\"pillars.md\\"}"}}]}}]}',
                     'data: {"choices":[{"index":0,"delta":{},'
                     '"finish_reason":"tool_calls"}]}')
        calls = [e.call for e in OpenAIWire().events(stream)
                 if e.kind == "tool_call"]
        self.assertEqual(sorted(c.arguments["name"] for c in calls),
                         ["pillars.md", "voice.md"])


class TestWireFor(unittest.TestCase):
    def test_the_two_shipped_names_resolve(self):
        self.assertIsInstance(wire_for("anthropic"), AnthropicWire)
        self.assertIsInstance(wire_for("openai"), OpenAIWire)

    def test_an_unknown_name_is_refused_by_name(self):
        with self.assertRaises(ProviderError) as caught:
            wire_for("gemini")
        self.assertIn("gemini", str(caught.exception))


class TestTheAppRefusesToStart(unittest.TestCase):
    """The contract is written in the present tense, so something has to
    enforce it. This is that something, before any port is opened."""

    def setUp(self):
        from verbatim_app.cli import main
        self.main = main
        self.root = Path(tempfile.mkdtemp(prefix="verbatim-cli-"))

    def run_cli(self, environ):
        captured = io.StringIO()
        with mock.patch.dict("os.environ", environ, clear=True):
            with redirect_stderr(captured):
                code = self.main([str(self.root)])
        return code, captured.getvalue()

    def test_a_key_in_the_instance_stops_the_app(self):
        (self.root / ".env").write_text("ANTHROPIC_API_KEY=sk-real\n")
        code, said = self.run_cli({})
        self.assertEqual(code, 2)
        self.assertIn("ANTHROPIC_API_KEY", said)
        self.assertNotIn("sk-real", said)

    def test_an_endpoint_the_instance_chose_for_the_key_stops_the_app(self):
        (self.root / ".env").write_text(
            "VERBATIM_BASE_URL=https://collector.attacker.example\n")
        code, said = self.run_cli({"ANTHROPIC_API_KEY": "sk-real"})
        self.assertEqual(code, 2)
        self.assertIn("collector.attacker.example", said)
        self.assertNotIn("sk-real", said)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
