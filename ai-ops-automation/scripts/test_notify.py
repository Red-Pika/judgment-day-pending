"""Send a real test message to every channel configured in your environment/.env.
Usage:  set -a; . ./.env; set +a; python3 -m scripts.test_notify
"""
import sys

from opsguard.config import Settings
from opsguard.notify import configured_channels, notify

s = Settings.from_env()
ch = configured_channels(s)
if not ch:
    sys.exit("No channel configured. Fill TELEGRAM_*, SLACK_WEBHOOK_URL and/or SMTP_* + EMAIL_TO in .env")
print("Configured channels:", ", ".join(ch))
res = notify(s, "🔵 *INFO* `opsguard` — test notification\n*Summary:* If you can read this, the channel works.")
for name, r in res.items():
    print(f"  {name:9} {'OK' if r['ok'] else 'FAILED: ' + r['error']}")
sys.exit(0 if all(r["ok"] for r in res.values()) else 1)
