"""Run triage + approval over HTTP with Telegram/Slack/SMTP *stand-ins* and save what each channel received."""
import email
import email.policy
import json
import os
import shutil
import threading
import urllib.request

from opsguard.app import make_server
from opsguard.audit import AuditLog
from opsguard.approvals import ApprovalStore
from opsguard.config import Settings
from opsguard.llm import MockProvider
from opsguard.triage import Context
from simulator.scenarios import SCENARIOS
from tests.fakes import FakeHTTP, FakeSMTP

OUT = "evidence/notifications"
TO = "adhit.adhya01@gmail.com"


def post(base, path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    tg, slack, smtp = FakeHTTP(), FakeHTTP(body=b"ok"), FakeSMTP()
    audit_path = f"{OUT}/audit.jsonl"
    s = Settings(audit_path=audit_path, telegram_bot_token="123456:FAKE-TOKEN", telegram_chat_id="-1001234",
                 telegram_api_base=tg.url, slack_webhook_url=slack.url + "/services/T000/B000/FAKE",
                 smtp_host="127.0.0.1", smtp_port=smtp.port, smtp_security="none",
                 email_from="opsguard@example.com", email_to=TO)
    ctx = Context(s, MockProvider(), AuditLog(audit_path), ApprovalStore(900), sleep=lambda _x: None)
    srv = make_server(ctx, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    # what n8n does: triage -> notify(report) -> notify(approval request) -> decision -> notify(outcome)
    rep = post(base, "/triage", SCENARIOS["oom_checkout"])
    n1 = post(base, "/notify", {"text": rep["markdown"]})
    n2 = post(base, "/notify", {"text": f"APPROVAL REQUIRED for alert {rep['alert_id']}. Resume URL: <n8n resumeUrl>"})
    dec = post(base, f"/approvals/{rep['approval']['id']}/decision", {"decision": "approved", "approver": "adhit"})
    n3 = post(base, "/notify", {"text": dec["message"]})

    json.dump(tg.requests, open(f"{OUT}/telegram_requests.json", "w"), indent=2, ensure_ascii=False)
    json.dump(slack.requests, open(f"{OUT}/slack_requests.json", "w"), indent=2, ensure_ascii=False)
    for i, m in enumerate(smtp.messages, 1):
        with open(f"{OUT}/email_{i}.eml", "w") as f:
            f.write(m["data"])
    lines = ["# Notification evidence (LOCAL STAND-INS, not real Telegram/Slack/Gmail)\n",
             "| Message | telegram | slack | email |", "|---|---|---|---|"]
    for name, n in (("triage report", n1), ("approval request", n2), ("approval outcome", n3)):
        r = n["results"]
        lines.append(f"| {name} | {'ok' if r['telegram']['ok'] else 'FAIL'} | {'ok' if r['slack']['ok'] else 'FAIL'} | {'ok' if r['email']['ok'] else 'FAIL'} |")
    first = email.message_from_string(smtp.messages[0]["data"], policy=email.policy.default)
    lines += ["", f"Telegram requests received: {len(tg.requests)}; Slack: {len(slack.requests)}; SMTP messages: {len(smtp.messages)}",
              f"Email recipient (SMTP RCPT TO): {smtp.messages[0]['rcpts']}", f"Email subject: {first['Subject']}", "",
              "First Telegram message as delivered (HTML parse mode):", "```", tg.requests[0]["body"]["text"], "```", "",
              "First email body:", "```", first.get_content().strip(), "```"]
    raw = open(f"{OUT}/telegram_requests.json").read() + open(f"{OUT}/slack_requests.json").read() + "".join(
        m["data"] for m in smtp.messages)
    lines.append("\nSecret scan of all delivered messages (raw secrets from the alert): " +
                 ("FAILED" if any(x in raw for x in ("S3cr3tP@ssw0rd", "alice@example.com", "10.2.3.4", "abcdef1234567890XYZ")) else "passed"))
    open(f"{OUT}/summary.md", "w").write("\n".join(lines) + "\n")
    srv.shutdown(); srv.server_close(); tg.close(); slack.close(); smtp.close()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
