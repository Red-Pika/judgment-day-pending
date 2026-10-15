import json
import unittest

from opsguard.audit import verify_file
from opsguard.triage import decide_approval, run_triage
from opsguard.validation import ValidationError
from tests.helpers import FailingProvider, RecordingProvider, make_ctx, scenario


def events(ctx):
    with open(ctx.settings.audit_path) as f:
        return [json.loads(l)["event"] for l in f]


class TriageTests(unittest.TestCase):
    def test_happy_path_gates_risky_step(self):
        ctx = make_ctx()
        r = run_triage(scenario("oom_checkout"), ctx)
        self.assertEqual(r["status"], "ok")
        risks = {s["index"]: (s["risk"], s["requires_approval"]) for s in r["steps"]}
        self.assertEqual(risks[0], ("low", False))
        self.assertEqual(risks[2], ("high", True))
        self.assertTrue(r["requires_approval"])
        self.assertEqual(r["approval"]["step_indexes"], [2])
        self.assertGreater(r["estimated_cost_usd"], 0)

    def test_secrets_never_reach_the_llm(self):
        prov = RecordingProvider()
        run_triage(scenario("oom_checkout"), make_ctx(prov))
        sent = prov.prompts[0]
        for secret in ("S3cr3tP@ssw0rd", "alice@example.com", "10.2.3.4", "abcdef1234567890XYZ"):
            self.assertNotIn(secret, sent)
        self.assertIn("[REDACTED:", sent)

    def test_secrets_never_reach_the_audit_log(self):
        ctx = make_ctx()
        run_triage(scenario("oom_checkout"), ctx)
        with open(ctx.settings.audit_path) as f:
            raw = f.read()
        for secret in ("S3cr3tP@ssw0rd", "alice@example.com", "abcdef1234567890XYZ"):
            self.assertNotIn(secret, raw)

    def test_prompt_injection_cannot_cause_dangerous_action(self):
        ctx = make_ctx()
        r = run_triage(scenario("prompt_injection"), ctx)
        self.assertEqual(len(r["blocked_steps"]), 2)
        for s in r["steps"]:
            self.assertNotIn("rm -rf", s["command"])
            self.assertNotIn("evil.example", s["command"])
        self.assertIn("step_blocked", events(ctx))
        self.assertNotIn("abc123SECRETvalue", json.dumps(r))      # secret echoed by model is scrubbed

    def test_llm_outage_degrades_gracefully(self):
        prov = FailingProvider()
        ctx = make_ctx(prov, llm_retries=2)
        r = run_triage(scenario("oom_checkout"), ctx)
        self.assertEqual(r["status"], "degraded")
        self.assertEqual(r["steps"], [])
        self.assertFalse(r["requires_approval"])
        self.assertEqual(prov.calls, 3)
        self.assertIn("llm_call_failed", events(ctx))
        self.assertIn("degraded", r["markdown"])

    def test_invalid_alert_rejected_and_audited(self):
        ctx = make_ctx()
        with self.assertRaises(ValidationError):
            run_triage(scenario("invalid_alert"), ctx)
        self.assertEqual(events(ctx), ["alert_rejected"])

    def test_approval_flow_dry_run_and_audit(self):
        ctx = make_ctx()
        r = run_triage(scenario("oom_checkout"), ctx)
        d = decide_approval(ctx, r["approval"]["id"], "approved", "alice")
        self.assertEqual(d["results"][0]["executed"], False)
        self.assertEqual(d["results"][0]["mode"], "dry-run")
        ev = events(ctx)
        for e in ("approval_requested", "approval_decided", "step_executed_dry_run"):
            self.assertIn(e, ev)
        self.assertEqual(verify_file(ctx.settings.audit_path), (True, None))

    def test_rejection_executes_nothing(self):
        ctx = make_ctx()
        r = run_triage(scenario("db_timeout"), ctx)
        d = decide_approval(ctx, r["approval"]["id"], "rejected", "bob")
        self.assertEqual(d["results"], [])
        self.assertNotIn("step_executed_dry_run", events(ctx))

    def test_failed_approval_attempt_is_audited(self):
        ctx = make_ctx()
        r = run_triage(scenario("oom_checkout"), ctx)
        decide_approval(ctx, r["approval"]["id"], "approved", "alice")
        with self.assertRaises(Exception):
            decide_approval(ctx, r["approval"]["id"], "approved", "mallory")
        self.assertIn("approval_decision_failed", events(ctx))

    def test_advisory_only_alert_needs_no_approval(self):
        ctx = make_ctx()
        r = run_triage(scenario("oom_checkout", summary="odd", logs=["something unusual"], alert_id="alrt-9"), ctx)
        self.assertFalse(r["requires_approval"])


if __name__ == "__main__":
    unittest.main()
