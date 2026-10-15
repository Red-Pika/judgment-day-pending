import unittest
from opsguard.validation import ValidationError, validate_alert
from tests.helpers import scenario


class ValidationTests(unittest.TestCase):
    def test_valid_alert(self):
        a = validate_alert(scenario("oom_checkout"))
        self.assertEqual(a["service"], "checkout-api")
        self.assertFalse(a["logs_truncated"])

    def test_not_an_object(self):
        with self.assertRaises(ValidationError):
            validate_alert(["x"])

    def test_missing_fields_reports_all(self):
        with self.assertRaises(ValidationError) as cm:
            validate_alert({})
        self.assertGreaterEqual(len(cm.exception.errors), 5)

    def test_bad_severity(self):
        with self.assertRaises(ValidationError):
            validate_alert(scenario("oom_checkout", severity="banana"))

    def test_bad_alert_id_charset(self):
        with self.assertRaises(ValidationError):
            validate_alert(scenario("oom_checkout", alert_id="a b;rm"))

    def test_summary_too_long(self):
        with self.assertRaises(ValidationError):
            validate_alert(scenario("oom_checkout", summary="x" * 501))

    def test_logs_wrong_type(self):
        with self.assertRaises(ValidationError):
            validate_alert(scenario("oom_checkout", logs="not a list"))

    def test_metrics_reject_bool_and_strings(self):
        with self.assertRaises(ValidationError):
            validate_alert(scenario("oom_checkout", metrics={"a": True}))
        with self.assertRaises(ValidationError):
            validate_alert(scenario("oom_checkout", metrics={"a": "5"}))

    def test_logs_truncated_to_latest_200_lines(self):
        a = validate_alert(scenario("oom_checkout", logs=[f"line{i}" for i in range(500)]))
        self.assertEqual(len(a["logs"]), 200)
        self.assertEqual(a["logs"][-1], "line499")
        self.assertTrue(a["logs_truncated"])

    def test_unknown_fields_dropped(self):
        a = validate_alert(scenario("oom_checkout", evil="<script>"))
        self.assertNotIn("evil", a)


if __name__ == "__main__":
    unittest.main()
