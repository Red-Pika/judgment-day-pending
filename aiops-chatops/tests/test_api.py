from fastapi.testclient import TestClient

from app.main import api


def test_healthz():
    with TestClient(api) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_requires_configured_secret(monkeypatch):
    monkeypatch.delenv("ALERTMANAGER_WEBHOOK_TOKEN", raising=False)
    with TestClient(api) as client:
        response = client.post("/webhook/alertmanager", json={"alerts": []})
    assert response.status_code == 503


def test_webhook_rejects_wrong_secret(monkeypatch):
    monkeypatch.setenv("ALERTMANAGER_WEBHOOK_TOKEN", "test-secret")
    with TestClient(api) as client:
        response = client.post(
            "/webhook/alertmanager",
            headers={"X-Alertmanager-Token": "wrong"},
            json={"alerts": []},
        )
    assert response.status_code == 401


def test_webhook_accepts_empty_alert_list(monkeypatch):
    monkeypatch.setenv("ALERTMANAGER_WEBHOOK_TOKEN", "test-secret")
    with TestClient(api) as client:
        response = client.post(
            "/webhook/alertmanager",
            headers={"X-Alertmanager-Token": "test-secret"},
            json={"alerts": []},
        )
    assert response.status_code == 200
    assert response.json() == {"accepted": True, "alerts": 0, "delivered": 0}
