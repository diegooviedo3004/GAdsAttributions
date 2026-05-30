import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

_CLICK_PAYLOAD = {
    "gclid": "abc123gclid",
    "conversion_datetime": "2024-05-01 10:00:00+00:00",
}

_CALL_PAYLOAD = {
    "caller_id": "+15551234567",
    "call_start_datetime": "2024-05-01 00:00:00-08:00",
    "conversion_datetime": "2024-05-03 00:00:00-08:00",
}


def test_callrail_attribution_success():
    with patch(
        "app.api.webhooks.callrail_attribution.GoogleAdsClient",
    ) as MockClient:
        MockClient.return_value.upload_click_conversion = AsyncMock(
            return_value={"results": [{"gclid": "abc123gclid"}]}
        )
        resp = client.post("/webhooks/callrail-attribution", json=_CLICK_PAYLOAD)

    assert resp.status_code == 200
    assert "results" in resp.json()


def test_callrail_attribution_missing_gclid():
    resp = client.post("/webhooks/callrail-attribution", json={"conversion_datetime": "2024-05-01"})
    assert resp.status_code == 422


def test_phone_conversion_success():
    with patch(
        "app.api.webhooks.phone_conversion.GoogleAdsClient",
    ) as MockClient:
        MockClient.return_value.upload_call_conversion = AsyncMock(
            return_value={"results": [{"callerId": "+15551234567"}]}
        )
        resp = client.post("/webhooks/phone-conversion", json=_CALL_PAYLOAD)

    assert resp.status_code == 200
    assert "results" in resp.json()


def test_phone_conversion_missing_caller_id():
    resp = client.post("/webhooks/phone-conversion", json={
        "call_start_datetime": "2024-05-01 00:00:00-08:00",
        "conversion_datetime": "2024-05-03 00:00:00-08:00",
    })
    assert resp.status_code == 422


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
