import unittest
from opsguard.approvals import ApprovalError, ApprovalStore

STEPS = [{"index": 2, "command": "kubectl rollout restart deployment/a"}, {"index": 4, "command": "x"}]


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.store = ApprovalStore(ttl=60, clock=lambda: self.now)

    def fails(self, code, *args, **kw):
        with self.assertRaises(ApprovalError) as cm:
            self.store.decide(*args, **kw)
        self.assertEqual(cm.exception.http_status, code)

    def test_approve_all_by_default(self):
        a = self.store.create("al-1", STEPS)
        r = self.store.decide(a["id"], "approved", "alice")
        self.assertEqual(r["approved_steps"], [2, 4])

    def test_partial_approval(self):
        a = self.store.create("al-1", STEPS)
        self.assertEqual(self.store.decide(a["id"], "approved", "alice", [2])["approved_steps"], [2])

    def test_cannot_approve_unproposed_step(self):
        a = self.store.create("al-1", STEPS)
        self.fails(400, a["id"], "approved", "alice", [99])

    def test_reject_executes_nothing(self):
        a = self.store.create("al-1", STEPS)
        self.assertEqual(self.store.decide(a["id"], "rejected", "bob")["approved_steps"], [])

    def test_no_double_decision(self):
        a = self.store.create("al-1", STEPS)
        self.store.decide(a["id"], "approved", "alice")
        self.fails(409, a["id"], "rejected", "bob")

    def test_expiry(self):
        a = self.store.create("al-1", STEPS)
        self.now += 61
        self.fails(410, a["id"], "approved", "alice")
        self.assertEqual(self.store.get(a["id"])["status"], "expired")

    def test_requires_approver_and_valid_decision(self):
        a = self.store.create("al-1", STEPS)
        self.fails(400, a["id"], "approved", "")
        self.fails(400, a["id"], "maybe", "alice")

    def test_unknown_id(self):
        self.fails(404, "nope", "approved", "alice")


if __name__ == "__main__":
    unittest.main()
