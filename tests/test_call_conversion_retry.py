import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.services.call_conversion_retry import (
    _extract_error_codes,
    _is_success,
    _parse_to_date,
    _fmt,
    run_with_retry,
)
from datetime import datetime

client = TestClient(app)

# ── Unit: helpers ──────────────────────────────────────────────────────────────

def test_parse_to_date_with_time():
    assert _parse_to_date("2026-05-29 21:50:56") == datetime(2026, 5, 29)

def test_parse_to_date_iso():
    assert _parse_to_date("2026-05-29T21:50:56") == datetime(2026, 5, 29)

def test_parse_to_date_with_tz():
    assert _parse_to_date("2026-05-29 21:50:56+00:00") == datetime(2026, 5, 29)

def test_fmt():
    assert _fmt(datetime(2026, 5, 29)) == "2026-05-29 00:00:00-08:00"

def test_is_success_with_populated_result():
    assert _is_success({"results": [{"callerId": "5551234567"}]}) is True

def test_is_success_with_empty_result_object():
    # Google Ads returns [{}] when submitted but not matched — not a success
    assert _is_success({"results": [{}]}) is False

def test_is_success_with_no_results():
    assert _is_success({}) is False
    assert _is_success({"results": []}) is False

def test_extract_error_codes_call_not_found():
    response = {
        "partialFailureError": {
            "details": [{"errors": [{"errorCode": {"conversionUploadError": "CALL_NOT_FOUND"}}]}]
        }
    }
    assert _extract_error_codes(response) == {"CALL_NOT_FOUND"}

def test_extract_error_codes_multiple():
    response = {
        "partialFailureError": {
            "details": [{
                "errors": [
                    {"errorCode": {"conversionUploadError": "CALL_NOT_FOUND"}},
                    {"errorCode": {"dateError": "LATER_THAN_MAXIMUM_DATE"}},
                ]
            }]
        }
    }
    assert _extract_error_codes(response) == {"CALL_NOT_FOUND", "LATER_THAN_MAXIMUM_DATE"}

def test_extract_error_codes_empty():
    assert _extract_error_codes({}) == set()
    assert _extract_error_codes({"results": [{"callerId": "123"}]}) == set()

# ── Unit: retry strategy ───────────────────────────────────────────────────────

_CALL_NOT_FOUND = {
    "partialFailureError": {
        "details": [{"errors": [{"errorCode": {"conversionUploadError": "CALL_NOT_FOUND"}}]}]
    },
    "results": [{}],
}

_SUCCESS = {"results": [{"callerId": "5149091569", "conversionAction": "customers/x/conversionActions/y"}]}

_TERMINAL = {
    "partialFailureError": {
        "details": [{"errors": [{"errorCode": {"conversionUploadError": "UNPARSEABLE_CALLERS_PHONE_NUMBER"}}]}]
    },
    "results": [{}],
}


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt():
    mock_client = AsyncMock()
    mock_client.upload_call_conversion = AsyncMock(side_effect=[_CALL_NOT_FOUND, _SUCCESS])

    result = await run_with_retry(
        client=mock_client,
        customer_id="123",
        conversion_action="customers/123/conversionActions/456",
        caller_id="5149091569",
        call_start_datetime="2026-05-29 21:50:56",
        search_window_days=1,
    )

    assert result.success is True
    assert result.attempts == 2
    assert result.successful_combination is not None


@pytest.mark.asyncio
async def test_retry_stops_on_terminal_error():
    mock_client = AsyncMock()
    mock_client.upload_call_conversion = AsyncMock(return_value=_TERMINAL)

    result = await run_with_retry(
        client=mock_client,
        customer_id="123",
        conversion_action="customers/123/conversionActions/456",
        caller_id="bad-phone",
        call_start_datetime="2026-05-29 21:50:56",
        search_window_days=30,
    )

    assert result.success is False
    assert result.attempts == 1  # stopped immediately
    assert result.terminal_error == "UNPARSEABLE_CALLERS_PHONE_NUMBER"


@pytest.mark.asyncio
async def test_retry_exhausts_all_combinations():
    mock_client = AsyncMock()
    mock_client.upload_call_conversion = AsyncMock(return_value=_CALL_NOT_FOUND)

    result = await run_with_retry(
        client=mock_client,
        customer_id="123",
        conversion_action="customers/123/conversionActions/456",
        caller_id="5149091569",
        call_start_datetime="2026-05-29 21:50:56",
        search_window_days=2,
    )

    assert result.success is False
    assert result.attempts == 3 * 16  # (2+1) start dates × 16 conv offsets


# ── Integration: webhook schema ────────────────────────────────────────────────

def test_phone_conversion_requires_conversion_datetime_without_retry():
    resp = client.post("/webhooks/phone-conversion", json={
        "caller_id": "+15551234567",
        "call_start_datetime": "2026-05-29 21:50:56",
        # no conversion_datetime, no search_window_days
    })
    assert resp.status_code == 422


def test_phone_conversion_accepts_no_conversion_datetime_with_retry():
    with patch("app.api.webhooks.phone_conversion.GoogleAdsClient") as MockClient:
        MockClient.return_value.upload_call_conversion = AsyncMock(return_value=_SUCCESS)
        resp = client.post("/webhooks/phone-conversion", json={
            "caller_id": "+15551234567",
            "call_start_datetime": "2026-05-29 21:50:56",
            "search_window_days": 1,
        })
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_phone_conversion_search_window_above_90_rejected():
    resp = client.post("/webhooks/phone-conversion", json={
        "caller_id": "+15551234567",
        "call_start_datetime": "2026-05-29 21:50:56",
        "search_window_days": 91,
    })
    assert resp.status_code == 422
