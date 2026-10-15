"""Run every simulated scenario end-to-end over HTTP (mock LLM) and write evidence/ files."""
import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request

from opsguard.app import make_server
from opsguard.audit import AuditLog, verify_file
from opsguard.approvals import ApprovalStore
from opsguard.config import Settings
from opsguard.llm import LLMTransportError, MockProvider
from opsguard.triage import Context
from simulator.scenarios import SCENARIOS

OUT = "evidence"
TOKEN = "demo-token"


class Outage:
    name = "simulated-outage"

    def complete(self, s, u):
        raise LLMTransportError("simulated LLM outage (HTTP 529)")


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                headers={"Content-Type": "application/json", "X-Service-Token": TOKEN})
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r), int((time.monotonic() - t) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e), int((time.monotonic() - t) * 1000)


def main():
    shutil.rmtree(OUT + "/reports", ignore_errors=True)
    os.makedirs(OUT + "/reports")
    audit_path = f"{OUT}/audit.jsonl"
    if os.path.exists(audit_path):
        os.remove(audit_path)
    s = Settings(service_token=TOKEN, audit_path=audit_path, llm_backoff=0.0, price_in_per_mtok=1.0,
                 price_out_per_mtok=5.0)   # ILLUSTRATIVE prices, not real ones
    audit, approvals = AuditLog(audit_path), ApprovalStore(s.approval_ttl)
    ctx = Context(s, MockProvider(), audit, approvals, sleep=lambda _x: None)
    outage_ctx = Context(s, Outage(), audit, approvals, sleep=lambda _x: None)

    servers = []
    for c in (ctx, outage_ctx):
        srv = make_server(c, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append((srv, f"http://127.0.0.1:{srv.server_address[1]}"))
    base, base_out = servers[0][1], servers[1][1]

    rows, decisions = [], {}
    runs = [(n, base, n) for n in SCENARIOS] + [("llm_outage", base_out, "oom_checkout")]
    for label, url, scen in runs:
        payload = dict(SCENARIOS[scen])
        if label == "llm_outage":
            payload["alert_id"] = "alrt-0006"
        code, rep, ms = post(url, "/triage", payload)
        with open(f"{OUT}/reports/{label}.json", "w") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        if code == 200:
            with open(f"{OUT}/reports/{label}.md", "w") as f:
                f.write(rep["markdown"] + "\n")
        rows.append((label, code, rep, ms))

    # human decisions: approve the OOM restart, reject the DB proxy restart
    by = {r[0]: r[2] for r in rows}
    for label, decision, who in (("oom_checkout", "approved", "alice"), ("db_timeout", "rejected", "bob")):
        aid = by[label]["approval"]["id"]
        code, d, _ = post(base, f"/approvals/{aid}/decision", {"decision": decision, "approver": who})
        decisions[label] = (code, d)
        # a second decision on the same ticket must be refused
        code2, d2, _ = post(base, f"/approvals/{aid}/decision", {"decision": "approved", "approver": "mallory"})
        decisions[label + "_replay"] = (code2, d2)
    json.dump({k: {"http": v[0], "body": v[1]} for k, v in decisions.items()},
              open(f"{OUT}/approval_decisions.json", "w"), indent=2)

    # audit integrity: verify, then tamper with a copy and verify again
    ok, bad = verify_file(audit_path)
    tampered = f"{OUT}/audit_tampered_copy.jsonl"
    lines = open(audit_path).read().splitlines()
    e = json.loads(lines[3])
    e["data"]["severity"] = "info"           # attacker downgrades a severity after the fact
    lines[3] = json.dumps(e)
    open(tampered, "w").write("\n".join(lines) + "\n")
    ok2, bad2 = verify_file(tampered)
    with open(f"{OUT}/audit_integrity_check.txt", "w") as f:
        f.write(f"original audit.jsonl : verify_file -> ok={ok}, first_bad_seq={bad}  ({len(lines)} entries)\n")
        f.write(f"tampered copy (seq 4 edited) : verify_file -> ok={ok2}, first_bad_seq={bad2}\n")
    os.remove(tampered)

    # secrets check over every artifact we produced
    secrets = ["S3cr3tP@ssw0rd", "alice@example.com", "abcdef1234567890XYZ", "10.2.3.4", "abc123SECRETvalue"]
    leaks = []
    for root, _d, files in os.walk(OUT):
        for fn in files:
            if fn.startswith("secret_scan"):
                continue
            txt = open(os.path.join(root, fn), errors="ignore").read()
            leaks += [(fn, sec) for sec in secrets if sec in txt]
    with open(f"{OUT}/secret_scan.txt", "w") as f:
        f.write("Scanned all files under evidence/ for the raw secrets planted in the simulated alerts:\n")
        f.write("  " + ", ".join(secrets) + "\n")
        f.write("RESULT: " + ("LEAKS FOUND: " + str(leaks) if leaks else "no leaks found") + "\n")

    with open(f"{OUT}/summary.md", "w") as f:
        f.write("# Scenario results (mock LLM, local run)\n\n")
        f.write("| Scenario | HTTP | Status | Redacted in | Steps (low/high) | Blocked | Approval | Latency |\n|---|---|---|---|---|---|---|---|\n")
        for label, code, rep, ms in rows:
            if code != 200:
                f.write(f"| {label} | {code} | rejected: {'; '.join(rep['details'][:2])} | - | - | - | - | {ms} ms |\n")
                continue
            low = sum(1 for x in rep["steps"] if x["risk"] in ("low", "none"))
            high = sum(1 for x in rep["steps"] if x["risk"] == "high")
            f.write(f"| {label} | {code} | {rep['status']} | {sum(rep['redactions']['input'].values())} | "
                    f"{low}/{high} | {len(rep['blocked_steps'])} | {'yes' if rep['requires_approval'] else 'no'} | {ms} ms |\n")
        f.write(f"\nAudit log integrity: {'VALID' if ok else 'BROKEN'} ({len(lines)} entries). "
                f"Tamper test: {'detected at seq ' + str(bad2) if not ok2 else 'NOT detected'}.\n")
        f.write(f"Secret scan: {'FAILED' if leaks else 'passed'}.\n")
    for srv, _b in servers:
        srv.shutdown()
        srv.server_close()
    print(open(f"{OUT}/summary.md").read())


if __name__ == "__main__":
    main()
