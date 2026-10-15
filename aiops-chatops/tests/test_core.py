from app.core import format_alertmanager_payload

def test_format_alertmanager_payload():
    payload = {"status": "firing", "alerts": [{
        "status": "firing",
        "labels": {"alertname": "HighCPU", "severity": "warning"},
        "annotations": {"summary": "CPU above threshold"},
    }]}
    messages = format_alertmanager_payload(payload)
    assert len(messages) == 1
    assert "[WARNING] HighCPU" in messages[0]
    assert "CPU above threshold" in messages[0]

def test_empty_alert_payload():
    assert format_alertmanager_payload({"alerts": []}) == []

def test_alert_payload_is_bounded():
    payload = {"alerts": [{"labels": {"alertname": "A" * 200}, "annotations": {"summary": "x" * 1000}}]}
    result = format_alertmanager_payload(payload)
    assert len(result) == 1
    assert len(result[0]) < 700
