import pytest
from unittest.mock import AsyncMock
from app.api.webhooks._handler import handle_conversion
from app.core.exceptions import IntegrationError, AuthError


@pytest.mark.asyncio
async def test_handle_conversion_returns_200_on_success():
    send = AsyncMock(return_value={"results": [{"callerId": "+15551234567"}]})
    response = await handle_conversion(workflow_name="test", payload={}, send=send)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_handle_conversion_returns_502_on_integration_error():
    async def send(_):
        raise IntegrationError("google_ads", "upstream failed", 500)

    response = await handle_conversion(workflow_name="test", payload={}, send=send)
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_handle_conversion_returns_401_on_auth_error():
    async def send(_):
        raise AuthError("google_ads", "token expired", 401)

    response = await handle_conversion(workflow_name="test", payload={}, send=send)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_handle_conversion_returns_500_on_unexpected_error():
    async def send(_):
        raise RuntimeError("something broke")

    response = await handle_conversion(workflow_name="test", payload={}, send=send)
    assert response.status_code == 500
