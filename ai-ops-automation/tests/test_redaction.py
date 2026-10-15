import unittest
from opsguard.redaction import redact_obj, redact_text


class RedactionTests(unittest.TestCase):
    def check(self, raw, secret, name):
        out, counts = redact_text(raw)
        self.assertNotIn(secret, out)
        self.assertIn(name, counts)

    def test_password_kv(self):
        self.check("DB_PASSWORD=S3cr3tP@ss connecting", "S3cr3tP@ss", "SECRET_KV")

    def test_json_style_secret(self):
        self.check('{"api_key": "sk-live-123456"}', "sk-live-123456", "SECRET_KV")

    def test_bearer(self):
        self.check("Authorization: Bearer abcdef1234567890XYZ", "abcdef1234567890XYZ", "BEARER_TOKEN")

    def test_jwt(self):
        self.check("t=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEF12345_-xyz", "eyJhbGciOiJIUzI1NiJ9", "JWT")

    def test_aws_key(self):
        self.check("key AKIAIOSFODNN7EXAMPLE used", "AKIAIOSFODNN7EXAMPLE", "AWS_ACCESS_KEY")

    def test_email_and_ip(self):
        out, c = redact_text("alice@example.com from 10.2.3.4")
        self.assertEqual(out, "[REDACTED:EMAIL] from [REDACTED:IP]")
        self.assertEqual(c, {"EMAIL": 1, "IPV4": 1})

    def test_url_credentials(self):
        self.check("postgres://admin:hunter2@db:5432/app", "hunter2", "URL_CREDENTIALS")

    def test_private_key_block(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\n-----END RSA PRIVATE KEY-----"
        self.check("x " + pem, "MIIEabc", "PRIVATE_KEY")

    def test_card(self):
        self.check("card 4111 1111 1111 1111", "4111 1111 1111 1111", "CARD_NUMBER")

    def test_clean_text_unchanged(self):
        t = "Pod checkout-api restarted 5 times; latency 2300ms; version 1.2"
        self.assertEqual(redact_text(t), (t, {}))

    def test_nested_objects(self):
        obj, c = redact_obj({"a": ["pwd=abc12345"], "b": {"c": "bob@x.io"}, "n": 5})
        self.assertNotIn("abc12345", str(obj))
        self.assertNotIn("bob@x.io", str(obj))
        self.assertEqual(obj["n"], 5)
        self.assertEqual(c, {"SECRET_KV": 1, "EMAIL": 1})


if __name__ == "__main__":
    unittest.main()
