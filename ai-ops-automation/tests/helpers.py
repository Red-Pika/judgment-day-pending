import os
import tempfile

from opsguard.audit import AuditLog
from opsguard.approvals import ApprovalStore
from opsguard.config import Settings
from opsguard.llm import LLMTransportError, MockProvider
from opsguard.triage import Context
from simulator.scenarios import SCENARIOS


class RecordingProvider(MockProvider):
    """Mock that remembers exactly what would have been sent to the LLM."""
    def __init__(self):
        self.prompts = []

    def complete(self, system, user):
        self.prompts.append(user)
        return super().complete(system, user)


class FailingProvider:
    name = "failing"

    def __init__(self):
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        raise LLMTransportError("simulated outage")


def make_ctx(provider=None, **overrides):
    d = tempfile.mkdtemp()
    s = Settings(audit_path=os.path.join(d, "audit.jsonl"), llm_backoff=0, price_in_per_mtok=1.0,
                 price_out_per_mtok=5.0, **overrides)
    return Context(s, provider or MockProvider(), AuditLog(s.audit_path), ApprovalStore(s.approval_ttl),
                   sleep=lambda _s: None)


def scenario(name, **changes):
    import copy
    p = copy.deepcopy(SCENARIOS[name])
    p.update(changes)
    return p
