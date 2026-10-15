import io
import json
import unittest
import urllib.error
from unittest import mock

from opsguard.llm import (AnthropicProvider, LLMOutputError, LLMTransportError, call_with_retry, parse_llm_json)

GOOD = {"summary": "s", "probable_cause": "c", "confidence": 0.5,
        "steps": [{"description": "d", "command": "kubectl get pods"}]}


class ParseTests(unittest.TestCase):
    def test_plain_and_fenced(self):
        self.assertEqual(parse_llm_json(json.dumps(GOOD))["summary"], "s")
        self.assertEqual(parse_llm_json("```json\n" + json.dumps(GOOD) + "\n```")["summary"], "s")

    def test_rejects_garbage(self):
        for bad in ["hello", "[]", json.dumps({**GOOD, "confidence": 7}), json.dumps({**GOOD, "summary": ""}),
                    json.dumps({**GOOD, "steps": [{"description": 1}]}),
                    json.dumps({**GOOD, "steps": [GOOD["steps"][0]] * 7})]:
            with self.assertRaises(LLMOutputError, msg=bad):
                parse_llm_json(bad)


class Flaky:
    def __init__(self, fail_times, error):
        self.n, self.fail_times, self.error = 0, fail_times, error

    def complete(self, s, u):
        self.n += 1
        if self.n <= self.fail_times:
            raise self.error
        return json.dumps(GOOD), {"input_tokens": 10, "output_tokens": 5}


class RetryTests(unittest.TestCase):
    def test_recovers_after_transient_failures(self):
        p = Flaky(2, LLMTransportError("boom"))
        parsed, usage, attempts = call_with_retry(p, "s", "u", retries=2, sleep=lambda _x: None)
        self.assertEqual(attempts, 3)

    def test_gives_up_and_reports_attempts(self):
        p = Flaky(99, LLMTransportError("boom"))
        with self.assertRaises(LLMTransportError) as cm:
            call_with_retry(p, "s", "u", retries=2, sleep=lambda _x: None)
        self.assertEqual(cm.exception.attempts, 3)

    def test_backoff_is_exponential(self):
        waits = []
        with self.assertRaises(LLMTransportError):
            call_with_retry(Flaky(99, LLMTransportError("x")), "s", "u", retries=3, backoff=1, sleep=waits.append)
        self.assertEqual(waits, [1, 2, 4])


class AnthropicProviderTests(unittest.TestCase):
    def test_requires_key(self):
        with self.assertRaises(ValueError):
            AnthropicProvider("", "m")

    def test_parses_response_and_sends_expected_request(self):
        resp = io.BytesIO(json.dumps({"content": [{"type": "text", "text": "{}"}],
                                      "usage": {"input_tokens": 12, "output_tokens": 3}}).encode())
        with mock.patch("urllib.request.urlopen", return_value=mock.MagicMock(
                __enter__=lambda s: resp, __exit__=lambda *a: False)) as uo:
            text, usage = AnthropicProvider("k", "claude-haiku-5-5").complete("sys", "usr")
        req = uo.call_args[0][0]
        self.assertEqual(req.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(req.get_header("X-api-key"), "k")
        body = json.loads(req.data)
        self.assertEqual(body["model"], "claude-haiku-5-5")
        self.assertEqual(body["system"], "sys")
        self.assertEqual((text, usage), ("{}", {"input_tokens": 12, "output_tokens": 3}))

    def test_network_error_becomes_transport_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(LLMTransportError):
                AnthropicProvider("k", "m").complete("s", "u")


if __name__ == "__main__":
    unittest.main()
