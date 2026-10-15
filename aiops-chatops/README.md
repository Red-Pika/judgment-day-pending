# AIOps + ChatOps MVP

A Docker-first, read-only AIOps starter connecting Telegram, Slack Socket Mode, Prometheus, and the OpenAI Responses API. It supports alert intake, AI-assisted triage, and monitoring commands. It does not execute remediation.

## Architecture

- FastAPI: health endpoints, read-only monitoring APIs, incident analysis API, and a protected Alertmanager webhook.
- Telegram: long polling; commands /help, /status, /alerts, /ask incident.
- Slack: Socket Mode; mention the bot with help, status, alerts, ask incident, or explain incident.
- Prometheus: starter scrape target and read-only query source.
- OpenAI Responses API: AI incident summary when OPENAI_API_KEY is configured; otherwise a transparent fallback response.

## Repository layout

    aiops-chatops/
    ├── app/
    │   ├── __init__.py
    │   ├── core.py
    │   └── main.py
    ├── prometheus/prometheus.yml
    ├── tests/test_core.py
    ├── .env.example
    ├── Dockerfile
    ├── compose.yaml
    ├── pytest.ini
    └── requirements.txt

## 1. Prerequisites

- Docker Engine and Docker Compose plugin.
- Telegram bot token from https://t.me/BotFather.
- A Slack test app/workspace (optional for first boot).
- OpenAI API key for live AI analysis (optional for first boot; API usage may incur charges).

## 2. Configure environment

From this directory, copy .env.example to .env and edit it. Never commit real secrets.

- OPENAI_API_KEY: API key.
- TELEGRAM_BOT_TOKEN: Telegram token; TELEGRAM_CHAT_ID is the notification destination.
- SLACK_BOT_TOKEN: xoxb bot token.
- SLACK_APP_TOKEN: xapp app token with connections:write; enable Socket Mode.
- SLACK_CHANNEL_ID: destination channel ID; invite the bot to the channel.
- ALERTMANAGER_WEBHOOK_TOKEN: generate a long random secret; requests must send it in the X-Alertmanager-Token header.

Slack app setup:
1. Create a Slack app in a development workspace.
2. Enable Socket Mode and create an app-level token with connections:write.
3. Add bot scopes chat:write, app_mentions:read, and channels:history; add groups:history or im:history only if needed.
4. Subscribe to app_mention and message.im bot events, then reinstall the app after changing scopes.
5. Invite the bot to a test channel. Socket Mode receives events without exposing a public request URL.

## 3. Start with Docker Compose

    docker compose up --build -d
    docker compose ps
    docker compose logs -f app

Verify:

    curl http://localhost:8080/healthz
    curl http://localhost:8080/readyz
    curl http://localhost:8080/api/status
    curl http://localhost:8080/api/alerts

Prometheus UI is bound to localhost only: http://localhost:9090.

If chat credentials are not configured, the API and Prometheus still start; chat integrations remain disabled.

## 4. Try AI analysis

    curl -X POST http://localhost:8080/api/analyze -H 'Content-Type: application/json' -d '{"description":"CPU usage reached 95% on api-01 for 10 minutes","context":"Recent deployment 15 minutes ago"}'

Without an API key, the endpoint returns a safe fallback. With a valid key, the response is generated using the configured model (default: gpt-5-mini).

## 5. Alertmanager webhook contract

Configure Alertmanager to POST its standard webhook payload to:

    http://app:8080/webhook/alertmanager

Send the shared secret in the X-Alertmanager-Token header. Example local smoke test:

    curl -X POST http://localhost:8080/webhook/alertmanager -H 'Content-Type: application/json' -H "X-Alertmanager-Token: $ALERTMANAGER_WEBHOOK_TOKEN" -d '{"status":"firing","alerts":[{"status":"firing","labels":{"alertname":"DemoHighCPU","severity":"warning"},"annotations":{"summary":"CPU usage exceeded threshold"}}]}'

Only configured destinations receive messages. The delivered response field counts successful destination deliveries, not the number of alerts.

## 6. Run tests locally

    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    pip install -r requirements.txt
    pytest -q

## Security and operational notes

- This MVP is read-only. It does not SSH to hosts, execute shell commands, restart services, or modify cloud resources.
- Do not put secrets in prompts, source control, screenshots, or chat messages.
- Restrict access to port 8080. The analysis API is intended for a trusted local network; put authentication and TLS in front of it before exposing it beyond localhost.
- Keep Slack in a development workspace until scopes and channel behavior are verified.
- OpenAI API use is billed separately from ChatGPT subscriptions; set a usage limit in your API account.
- Prometheus currently scrapes itself only. Add exporters/targets and alert rules before expecting infrastructure health data.
- AI output is advisory. Verify metrics/logs before acting on any proposed cause.
- Pin image/dependency versions and add integration tests before production use.

## Next milestones

1. Add node_exporter and safe alert rules.
2. Configure Alertmanager with secret injection and test delivery end-to-end.
3. Add authentication/RBAC for API endpoints.
4. Add incident history (PostgreSQL) and runbooks/RAG.
5. Add approval-gated remediation only after explicit policy and audit design.
