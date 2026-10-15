import email
import email.policy
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from opsguard.app import make_server
from opsguard.config import Settings
from opsguard.notify import configured_channels, notify
from tests.fakes import FakeHTTP, FakeSMTP
from tests.helpers import make_ctx

REPORT = ("🔴 *CRITICAL* `checkout-api` — alert `alrt-0001`\n*Summary:* Pods are OOMKilled & restarting <often>\n"
          "1. Restart — `kubectl rollout restart deployment/checkout-api -n prod` [⛔ needs approval]")
TO = "adhit.adhya01@gmail.com"


def parse(raw):
    return email.message_from_string(raw, policy=email.policy.default)


class NotifyTests(unittest.TestCase):
    def setUp(self):
        self.tg, self.slack, self.smtp = FakeHTTP(), FakeHTTP(body=b"ok"), FakeSMTP()
        self.addCleanup(self.tg.close)
        self.addCleanup(self.slack.close)
        self.addCleanup(self.smtp.close)
        self.s = Settings(telegram_bot_token="123:SECRETTOKEN", telegram_chat_id="999", telegram_api_base=self.tg.url,
                          slack_webhook_url=self.slack.url + "/hooks/T0/B0/XXXX", smtp_host="127.0.0.1",
                          smtp_port=self.smtp.port, smtp_security="none", email_from="ops@example.com", email_to=TO)

    def test_nothing_configured_means_no_channels(self):
        self.assertEqual(configured_channels(Settings()), [])
        self.assertEqual(notify(Settings(), "hi"), {})

    def test_partial_config_does_not_activate_channel(self):
        self.assertEqual(configured_channels(Settings(telegram_bot_token="x")), [])
        self.assertEqual(configured_channels(Settings(smtp_host="h", email_to="not-an-email")), [])

    def test_all_three_channels_deliver(self):
        r = notify(self.s, REPORT)
        self.assertEqual({k: v["ok"] for k, v in r.items()}, {"telegram": True, "slack": True, "email": True})

    def test_telegram_request_shape_and_html_escaping(self):
        notify(self.s, REPORT)
        req = self.tg.requests[0]
        self.assertEqual(req["path"], "/bot123:SECRETTOKEN/sendMessage")
        self.assertEqual(req["body"]["chat_id"], "999")
        self.assertEqual(req["body"]["parse_mode"], "HTML")
        self.assertIn("<b>CRITICAL</b>", req["body"]["text"])
        self.assertIn("<code>checkout-api</code>", req["body"]["text"])
        self.assertIn("&lt;often&gt;", req["body"]["text"])          # user data cannot inject HTML
        self.assertIn("&amp;", req["body"]["text"])

    def test_slack_payload(self):
        notify(self.s, REPORT)
        self.assertEqual(self.slack.requests[0]["path"], "/hooks/T0/B0/XXXX")
        self.assertIn("*CRITICAL*", self.slack.requests[0]["body"]["text"])

    def test_email_goes_to_recipient_with_clean_subject(self):
        notify(self.s, REPORT)
        m = self.smtp.messages[0]
        self.assertEqual(m["rcpts"], [TO])
        msg = parse(m["data"])
        self.assertEqual(msg["To"], TO)
        self.assertTrue(msg["Subject"].startswith("[Ops Alert] 🔴 CRITICAL checkout-api"))
        self.assertNotIn("\n", msg["Subject"])
        body = msg.get_content()
        self.assertIn("Summary: Pods are OOMKilled", body)
        self.assertNotIn("*", body)

    def test_multiple_recipients(self):
        self.s.email_to = f"{TO}, second@example.com"
        notify(self.s, REPORT)
        self.assertEqual(self.smtp.messages[0]["rcpts"], [TO, "second@example.com"])

    def test_secrets_redacted_before_sending(self):
        notify(self.s, "password=hunter2hunter2 from 10.9.8.7 by bob@corp.io")
        for sent in (json.dumps(self.tg.requests[0]), json.dumps(self.slack.requests[0]), self.smtp.messages[0]["data"]):
            for secret in ("hunter2hunter2", "10.9.8.7", "bob@corp.io"):
                self.assertNotIn(secret, sent)

    def test_long_text_truncated_for_telegram_limit(self):
        notify(self.s, "x" * 20000)
        self.assertLess(len(self.tg.requests[0]["body"]["text"]), 4096)

    def test_one_channel_failing_does_not_block_others_and_leaks_nothing(self):
        self.tg.status, self.tg.body = 401, b'{"ok":false}'
        r = notify(self.s, REPORT, sleep=lambda _x: None)
        self.assertFalse(r["telegram"]["ok"])
        self.assertEqual(r["telegram"]["attempts"], 2)
        self.assertTrue(r["slack"]["ok"] and r["email"]["ok"])
        self.assertNotIn("SECRETTOKEN", json.dumps(r))

    def test_telegram_ok_false_with_http_200_is_a_failure(self):
        self.tg.body = b'{"ok":false,"description":"chat not found"}'
        self.assertFalse(notify(self.s, REPORT, sleep=lambda _x: None)["telegram"]["ok"])

    def test_retry_succeeds_on_second_attempt(self):
        calls = {"n": 0}
        real = urllib.request.urlopen

        def flaky(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.URLError("temporary")
            return real(req, timeout=timeout)
        with mock.patch("urllib.request.urlopen", flaky):
            r = notify(Settings(slack_webhook_url=self.slack.url + "/h"), "x", sleep=lambda _x: None)
        self.assertEqual(r["slack"], {"ok": True, "attempts": 2})

    def test_unreachable_smtp_reported_not_raised(self):
        self.s.smtp_port = 1
        r = notify(self.s, REPORT, sleep=lambda _x: None)
        self.assertFalse(r["email"]["ok"])
        self.assertTrue(r["telegram"]["ok"])

    def test_starttls_and_login_used_for_gmail_style_config(self):
        s = Settings(smtp_host="smtp.gmail.com", smtp_port=587, smtp_security="starttls", smtp_user="me@gmail.com",
                     smtp_password="app-password-1234", email_to=TO)
        with mock.patch("smtplib.SMTP") as smtp_cls:
            r = notify(s, REPORT)
        inst = smtp_cls.return_value
        smtp_cls.assert_called_once_with("smtp.gmail.com", 587, timeout=10.0)
        inst.starttls.assert_called_once()
        inst.login.assert_called_once_with("me@gmail.com", "app-password-1234")
        self.assertTrue(r["email"]["ok"])

    def test_smtp_password_never_appears_in_errors(self):
        s = Settings(smtp_host="h", smtp_security="none", smtp_password="pw-should-hide", email_to=TO)
        with mock.patch("smtplib.SMTP", side_effect=OSError("auth failed for pw-should-hide")):
            r = notify(s, "x", sleep=lambda _x: None)
        self.assertNotIn("pw-should-hide", json.dumps(r))


class NotifyEndpointTests(unittest.TestCase):
    def setUp(self):
        self.slack = FakeHTTP(body=b"ok")
        self.addCleanup(self.slack.close)
        self.ctx = make_ctx(slack_webhook_url=self.slack.url + "/h")
        self.srv = make_server(self.ctx, "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def post(self, body):
        req = urllib.request.Request(self.base + "/notify", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_ok_and_audited_without_message_content(self):
        code, r = self.post({"text": "hello secret-ish text"})
        self.assertEqual((code, r["results"]["slack"]["ok"]), (200, True))
        with open(self.ctx.settings.audit_path) as f:
            raw = f.read()
        self.assertIn("notification_sent", raw)
        self.assertNotIn("secret-ish", raw)

    def test_bad_body_400(self):
        self.assertEqual(self.post({"text": ""})[0], 400)
        self.assertEqual(self.post({"nope": 1})[0], 400)

    def test_all_configured_channels_failing_returns_502(self):
        self.slack.status = 500
        self.ctx.sleep = lambda _x: None
        self.assertEqual(self.post({"text": "x"})[0], 502)


if __name__ == "__main__":
    unittest.main()
