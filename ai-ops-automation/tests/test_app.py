import json
import threading
import unittest
import urllib.error
import urllib.request

from opsguard.app import make_server
from tests.helpers import make_ctx, scenario


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = make_ctx(service_token="s3cret", max_body_bytes=5000, enable_chat_sink=True)
        cls.srv = make_server(cls.ctx, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def call(self, method, path, body=None, token="s3cret", raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Content-Type": "application/json"}
        if token:
            h["X-Service-Token"] = token
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_health_is_public(self):
        self.assertEqual(self.call("GET", "/health", token=None)[0], 200)

    def test_requires_token(self):
        self.assertEqual(self.call("POST", "/triage", scenario("oom_checkout"), token=None)[0], 401)
        self.assertEqual(self.call("POST", "/triage", scenario("oom_checkout"), token="wrong")[0], 401)

    def test_triage_then_approve(self):
        code, r = self.call("POST", "/triage", scenario("oom_checkout"))
        self.assertEqual(code, 200)
        code, d = self.call("POST", f"/approvals/{r['approval']['id']}/decision",
                            {"decision": "approved", "approver": "alice"})
        self.assertEqual((code, d["status"]), (200, "approved"))
        code, d = self.call("POST", f"/approvals/{r['approval']['id']}/decision",
                            {"decision": "approved", "approver": "alice"})
        self.assertEqual(code, 409)

    def test_invalid_alert_422(self):
        code, r = self.call("POST", "/triage", scenario("invalid_alert"))
        self.assertEqual(code, 422)
        self.assertTrue(r["details"])

    def test_bad_json_400(self):
        self.assertEqual(self.call("POST", "/triage", raw=b"{not json")[0], 400)

    def test_oversized_body_413(self):
        big = scenario("oom_checkout", logs=["x" * 1000] * 20)
        self.assertEqual(self.call("POST", "/triage", big)[0], 413)

    def test_unknown_approval_404(self):
        self.assertEqual(self.call("POST", "/approvals/nope/decision", {"decision": "approved", "approver": "a"})[0], 404)

    def test_chat_sink(self):
        self.call("POST", "/_chat-sink", {"text": "hello"})
        self.assertEqual(self.call("GET", "/_chat-sink")[1]["messages"][-1], {"text": "hello"})


if __name__ == "__main__":
    unittest.main()
