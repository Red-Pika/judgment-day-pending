from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .core import analyze_incident, format_alertmanager_payload, get_active_alerts, get_prometheus_status

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("aiops-chatops")


def _send_telegram(text: str) -> bool:
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:3900]},
            timeout=5.0,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("Telegram alert delivery failed: %s", type(exc).__name__)
        return False


def _send_slack(text: str) -> bool:
    token, channel = os.getenv("SLACK_BOT_TOKEN"), os.getenv("SLACK_CHANNEL_ID")
    if not token or not channel:
        return False
    try:
        from slack_sdk import WebClient
        response = WebClient(token=token).chat_postMessage(channel=channel, text=text[:3900])
        return bool(response.get("ok"))
    except Exception as exc:
        logger.warning("Slack alert delivery failed: %s", type(exc).__name__)
        return False


def _start_integrations() -> None:
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        threading.Thread(target=_run_telegram, name="telegram-bot", daemon=True).start()
    else:
        logger.info("Telegram integration disabled: TELEGRAM_BOT_TOKEN is empty")
    if os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_APP_TOKEN"):
        threading.Thread(target=_run_slack, name="slack-bot", daemon=True).start()
    else:
        logger.info("Slack integration disabled: Slack tokens not configured")


def _run_telegram() -> None:
    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

        async def reply(update: Update, text: str) -> None:
            if update.effective_message:
                await update.effective_message.reply_text(text[:3900])

        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            await reply(update, "AIOps ChatOps aktif. Ketik /help untuk daftar perintah.")

        async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            await reply(update, HELP_TEXT)

        async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            status = get_prometheus_status()
            text = (
                f"Prometheus reachable\nTargets UP: {status['targets_up']}/{status['targets_total']}"
                if status["ok"] else f"Monitoring belum tersedia: {status['message']}"
            )
            await reply(update, text)

        async def alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            result = get_active_alerts()
            if not result["ok"]:
                text = result["message"]
            elif not result["alerts"]:
                text = "Tidak ada alert aktif yang dilaporkan Prometheus."
            else:
                text = "\n".join(
                    f"• [{a['severity']}] {a['name']} ({a['state']}): {a['summary']}"
                    for a in result["alerts"][:10]
                )
            await reply(update, text)

        async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            await reply(update, analyze_incident(" ".join(context.args)))

        async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
            message = update.effective_message.text if update.effective_message else ""
            if message and not message.startswith("/"):
                await reply(update, analyze_incident(message))

        application = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("alerts", alerts_command))
        application.add_handler(CommandHandler("ask", ask_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
        application.run_polling(drop_pending_updates=True, stop_signals=None)
    except Exception as exc:
        logger.exception("Telegram bot stopped: %s", type(exc).__name__)


def _run_slack() -> None:
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        slack = App(token=os.environ["SLACK_BOT_TOKEN"])

        def handle_text(text: str) -> str:
            normalized = re.sub(r"<@[^>]+>", "", text or "").strip()
            command, _, argument = normalized.partition(" ")
            command = command.lower().lstrip("/")
            if command in {"help", "start"}:
                return HELP_TEXT
            if command == "status":
                status = get_prometheus_status()
                return (
                    f"Prometheus reachable; targets UP {status['targets_up']}/{status['targets_total']}."
                    if status["ok"] else f"Monitoring belum tersedia: {status['message']}"
                )
            if command == "alerts":
                result = get_active_alerts()
                if not result["ok"]:
                    return result["message"]
                if not result["alerts"]:
                    return "Tidak ada alert aktif yang dilaporkan Prometheus."
                return "\n".join(
                    f"• [{a['severity']}] {a['name']} ({a['state']}): {a['summary']}"
                    for a in result["alerts"][:10]
                )
            if command == "ask":
                return analyze_incident(argument)
            if command == "explain":
                return analyze_incident(argument or "Jelaskan status monitoring saat ini.")
            return analyze_incident(normalized)

        @slack.event("app_mention")
        def mention_handler(event: dict[str, Any], say: Any) -> None:
            say(handle_text(event.get("text", "")))

        @slack.message(re.compile(r"(?i)^\s*(help|status|alerts|ask\s+.+|explain\s+.+)\s*$"))
        def direct_message_handler(message: dict[str, Any], say: Any) -> None:
            say(handle_text(message.get("text", "")))

        SocketModeHandler(slack, os.environ["SLACK_APP_TOKEN"]).start()
    except Exception as exc:
        logger.exception("Slack bot stopped: %s", type(exc).__name__)


HELP_TEXT = (
    "AIOps ChatOps commands:\n"
    "/status — ringkasan target Prometheus\n"
    "/alerts — alert aktif dari Prometheus\n"
    "/ask <pertanyaan> — analisis AI untuk insiden\n"
    "/help — bantuan\n\n"
    "Mode awal hanya read-only; bot tidak menjalankan remediation."
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _start_integrations()
    yield


api = FastAPI(title="AIOps ChatOps", version="0.1.0", lifespan=lifespan)


@api.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@api.get("/readyz")
def readyz() -> dict[str, Any]:
    return {
        "status": "ready",
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "slack_configured": bool(os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_APP_TOKEN")),
        "prometheus_url_configured": bool(os.getenv("PROMETHEUS_URL")),
    }


@api.get("/api/status")
def api_status() -> dict[str, Any]:
    return get_prometheus_status()


@api.get("/api/alerts")
def api_alerts() -> dict[str, Any]:
    return get_active_alerts()


@api.post("/api/analyze")
async def api_analyze(request: Request) -> dict[str, str]:
    payload = await request.json()
    description = str(payload.get("description", ""))[:6000]
    context = str(payload.get("context", ""))[:4000]
    if not description.strip():
        raise HTTPException(status_code=422, detail="Field 'description' wajib diisi.")
    return {"analysis": analyze_incident(description, context)}


@api.post("/webhook/alertmanager")
async def alertmanager_webhook(
    request: Request,
    x_alertmanager_token: str | None = Header(default=None),
) -> JSONResponse:
    expected = os.getenv("ALERTMANAGER_WEBHOOK_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Alertmanager webhook belum dikonfigurasi.")
    if not x_alertmanager_token or not hmac.compare_digest(x_alertmanager_token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    messages = format_alertmanager_payload(payload if isinstance(payload, dict) else {})
    if not messages:
        return JSONResponse({"accepted": True, "alerts": 0, "delivered": 0})
    delivered = 0
    for message in messages:
        analysis = await asyncio.to_thread(analyze_incident, message)
        outbound = f"🚨 AIOps Alert\n{message}\n\nAI triage:\n{analysis}"
        results = await asyncio.gather(
            asyncio.to_thread(_send_telegram, outbound),
            asyncio.to_thread(_send_slack, outbound),
        )
        delivered += sum(1 for result in results if result)
    return JSONResponse({"accepted": True, "alerts": len(messages), "delivered": delivered})
