"""Send a simulated alert to n8n (or directly to the service).
Usage: python -m simulator.send_alert --url http://localhost:5678/webhook/ops-alert --scenario oom_checkout
"""
import argparse
import json
import urllib.request

from .scenarios import SCENARIOS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    ap.add_argument("--token", default="", help="X-Service-Token (only needed when posting to the service directly)")
    a = ap.parse_args()
    req = urllib.request.Request(a.url, data=json.dumps(SCENARIOS[a.scenario]).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **({"X-Service-Token": a.token} if a.token else {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        print(r.status, r.read().decode()[:2000])


if __name__ == "__main__":
    main()
