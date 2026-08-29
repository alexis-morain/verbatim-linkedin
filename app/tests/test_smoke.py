"""Tests for scripts/smoke.py, the one thing here that talks to a real wire.

The script exists because the recorded streams prove the parser and not the
endpoint. That makes it the only piece of this repository nothing else covers,
and the piece somebody reaches for once, under pressure, with a real key. A
smoke test that dies on a typo the first time it is run is worse than none, so
its plumbing is exercised here against the same replayed transport everything
else uses.

What is not tested here, and cannot be, is the thing the script is for.

Runs with the standard library only:  python3 app/tests/test_smoke.py
"""

import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "app"))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_agent import Replay, asks, says  # noqa: E402

import smoke  # noqa: E402
from verbatim_app.providers import Settings  # noqa: E402

ANTHROPIC = Settings("anthropic", "claude-opus-5", "https://api.anthropic.com",
                     "sk-test")


class TestTheProbes(unittest.TestCase):
    def test_a_plain_turn_comes_back_as_text_and_a_figure(self):
        text, calls, usage, stop = smoke.run(ANTHROPIC, Replay(says("ready.")))
        self.assertEqual(text, "ready.")
        self.assertEqual(calls, [])
        self.assertEqual(stop, "end_turn")
        self.assertEqual((usage.input_tokens, usage.output_tokens), (100, 10))

    def test_a_required_tool_is_asked_for_on_the_wire(self):
        transport = Replay(asks(("c1", smoke.PROBE_TOOL, {"word": "ready"})),
                           says("done"))
        _, calls, _, _ = smoke.run(ANTHROPIC, transport,
                                   require=smoke.PROBE_TOOL)
        self.assertEqual(calls, [smoke.PROBE_TOOL])
        self.assertEqual(transport.calls[0]["payload"]["tool_choice"],
                         {"type": "tool", "name": smoke.PROBE_TOOL})

    def test_the_probe_tool_runs_without_raising(self):
        # It is a lambda over `append`, which returns None. A tool whose run
        # returns None is a tool result of "None" on the wire, so the `or` in
        # it is load bearing rather than decorative.
        seen = []
        self.assertEqual(smoke.probe_tool(seen).run({"word": "ready"}), "noted")
        self.assertEqual(seen, ["ready"])


class TestTheReport(unittest.TestCase):
    """What the script prints. Nothing here reaches a network."""

    def run_main(self, environ):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = smoke.main_with(environ, lambda: Replay(
                says("ready."),
                asks(("c1", smoke.PROBE_TOOL, {"word": "ready"})),
                says("done")))
        return code, out.getvalue(), err.getvalue()

    def test_a_clean_run_passes_every_probe_and_prints_a_row(self):
        code, out, _ = self.run_main({"ANTHROPIC_API_KEY": "sk-test"})
        self.assertEqual(code, 0)
        self.assertEqual(out.count(smoke.PASS), 3)
        self.assertNotIn(smoke.FAIL, out)
        self.assertIn("| anthropic | claude-opus-5 |", out)

    def test_nothing_configured_says_so_and_asks_for_nothing(self):
        code, _, err = self.run_main({})
        self.assertEqual(code, 2)
        self.assertIn("key-missing", err)

    def test_an_instance_env_cannot_change_what_is_being_proved(self):
        # A throwaway directory, so the answer is about the environment the
        # person set and not about whichever instance they happen to be in.
        code, out, _ = self.run_main({"ANTHROPIC_API_KEY": "sk-test",
                                      "VERBATIM_MODEL": "some-other-model"})
        self.assertEqual(code, 0)
        self.assertIn("some-other-model", out)


class TestARuntimeThatIgnoresTheRequirement(unittest.TestCase):
    """The documented degraded path. Not a pass, and not a failure of the
    endpoint: the engine reads the anchors out of prose instead."""

    def test_it_is_reported_as_degraded_and_the_run_still_succeeds(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = smoke.main_with(
                {"ANTHROPIC_API_KEY": "sk-test"},
                lambda: Replay(says("ready."), says("ready.")))
        self.assertEqual(code, 0)
        self.assertIn(smoke.DEGRADED, out.getvalue())
        self.assertNotIn(smoke.FAIL, out.getvalue())


class TestAProviderFailing(unittest.TestCase):
    def test_the_key_never_reaches_the_terminal(self):
        # The failure body is the provider's, and a gateway that echoes an
        # Authorization header into it would otherwise put the key on a screen
        # somebody pastes into an issue.
        def boom():
            class Angry:
                def __call__(self, url, headers, payload):
                    raise smoke.ProviderError(
                        "500 from the gateway: bearer sk-secret-value")
            return Angry()

        out = io.StringIO()
        with redirect_stdout(out):
            code = smoke.main_with({"ANTHROPIC_API_KEY": "sk-secret-value"},
                                   boom)
        self.assertEqual(code, 1)
        self.assertIn(smoke.FAIL, out.getvalue())
        self.assertNotIn("sk-secret-value", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
