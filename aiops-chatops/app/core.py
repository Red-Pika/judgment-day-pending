"""Shared, side-effect-light logic for AIOps ChatOps."""
from __future__ import annotations
import os
from typing import Any
import httpx

SYSTEM_INSTRUCTIONS = (
    "You are an AIOps incident assistant. Be concise and operationally cautious. "
    "Separate observed facts from hypotheses, list likely causes and verification steps, "
    "and suggest safe read-only diagnostics first. Never claim to have executed an action. "
    "Never recommend exposing secrets or running destructive commands without approval."
)

def get_prometheus_status(base_url: str | None = None) -> dict[str, Any]:
    url = (base_url or os.getenv("PROMETHEUS_URL", "")).rstrip("/")
    if not url:
        return {"ok": False, "message": "PROMETHEUS_URL belum dikonfigurasi."}
    try:
        response = httpx.get(f"{url}/api/v1/query", params={"query": "up"}, timeout=3.0)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            return {"ok": False, "message": "Prometheus mengembalikan status non-success."}
        results = payload.get("data", {}).get("result", [])
        up = sum(1 for item in results if item.get("value", [None, "0"])[1] == "1")
        return {"ok": True, "targets_up": up, "targets_total": len(results)}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {"ok": False, "message": f"Prometheus tidak dapat diakses ({type(exc).__name__})."}

def get_active_alerts(base_url: str | None = None) -> dict[str, Any]:
    url = (base_url or os.getenv("PROMETHEUS_URL", "")).rstrip("/")
    if not url:
        return {"ok": False, "message": "PROMETHEUS_URL belum dikonfigurasi.", "alerts": []}
    try:
        response = httpx.get(f"{url}/api/v1/alerts", timeout=3.0)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            return {"ok": False, "message": "Prometheus mengembalikan status non-success.", "alerts": []}
        alerts = []
        for item in payload.get("data", {}).get("alerts", []):
            labels = item.get("labels", {})
            alerts.append({
                "name": labels.get("alertname", "UnknownAlert"),
                "severity": labels.get("severity", "unspecified"),
                "state": item.get("state", "unknown"),
                "summary": item.get("annotations", {}).get("summary", ""),
            })
        return {"ok": True, "alerts": alerts}
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {"ok": False, "message": f"Prometheus tidak dapat diakses ({type(exc).__name__}).", "alerts": []}

def analyze_incident(description: str, context: str = "") -> str:
    description = description.strip()[:6000]
    context = context.strip()[:4000]
    if not description:
        return "Berikan ringkasan insiden atau alert yang ingin dianalisis."
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return (
            "AI belum aktif karena OPENAI_API_KEY belum dikonfigurasi.\n"
            "Ringkasan insiden: " + description + "\n"
            "Langkah awal: verifikasi metrik/log terkait, cek perubahan terbaru, dan "
            "konfirmasi dampak sebelum melakukan perubahan."
        )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=20.0, max_retries=1)
        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            instructions=SYSTEM_INSTRUCTIONS,
            input=f"Insiden/alert:\n{description}\n\nKonteks observasi (jika ada):\n{context or 'Tidak tersedia'}",
        )
        answer = (response.output_text or "").strip()
        return answer[:5000] if answer else "AI tidak menghasilkan ringkasan. Periksa log aplikasi."
    except Exception as exc:
        return (
            f"Analisis AI sementara gagal ({type(exc).__name__}).\n"
            f"Ringkasan insiden: {description}\n"
            "Periksa konektivitas API, konfigurasi model, dan kuota API."
        )

def format_alertmanager_payload(payload: dict[str, Any]) -> list[str]:
    messages = []
    for alert in payload.get("alerts", [])[:20]:
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        name = str(labels.get("alertname", "UnknownAlert"))[:120]
        severity = str(labels.get("severity", "unspecified"))[:40]
        status = str(alert.get("status", payload.get("status", "unknown")))[:40]
        summary = str(annotations.get("summary") or annotations.get("description") or "No summary provided")[:500]
        messages.append(f"[{severity.upper()}] {name} — {status}\n{summary}")
    return messages
