"""
Google Ads API client.

Handles OAuth2 token refresh and two conversion upload endpoints:
  - uploadClickConversions  (callrail-attribution webhook)
  - uploadCallConversions   (phone-conversion webhook)
"""
from typing import Any
from app.integrations.base_client import BaseClient
from app.core.config import get_settings
from app.core.exceptions import IntegrationError, AuthError

_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_ADS_BASE = "https://googleads.googleapis.com/v20"


class GoogleAdsClient(BaseClient):
    service_name = "google_ads"

    def __init__(self) -> None:
        super().__init__()
        self._cfg = get_settings()
        self._access_token: str | None = None

    async def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        cfg = self._cfg
        resp = await self._request(
            "POST",
            _OAUTH_TOKEN_URL,
            json={
                "client_id": cfg.google_client_id,
                "client_secret": cfg.google_client_secret,
                "refresh_token": cfg.google_refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if resp.status_code != 200:
            raise AuthError("google_ads", f"token refresh failed: {resp.text}", resp.status_code)
        self._access_token = resp.json()["access_token"]
        return self._access_token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "developer-token": self._cfg.google_developer_token,
        }

    async def upload_click_conversion(
        self,
        *,
        customer_id: str,
        conversion_action: str,
        gclid: str,
        conversion_datetime: str,
    ) -> dict[str, Any]:
        token = await self._get_access_token()
        resp = await self._request(
            "POST",
            f"{_ADS_BASE}/customers/{customer_id}:uploadClickConversions",
            headers=self._auth_headers(token),
            json={
                "conversions": [{
                    "gclid": gclid,
                    "conversionAction": conversion_action,
                    "conversionDateTime": conversion_datetime,
                    "consent": {"adPersonalization": "GRANTED", "adUserData": "GRANTED"},
                }],
                "partialFailure": True,
            },
        )
        if resp.status_code not in (200, 206):
            raise IntegrationError("google_ads", f"uploadClickConversions failed: {resp.text}", resp.status_code)
        return resp.json()

    async def upload_call_conversion(
        self,
        *,
        customer_id: str,
        conversion_action: str,
        caller_id: str,
        call_start_datetime: str,
        conversion_datetime: str,
    ) -> dict[str, Any]:
        token = await self._get_access_token()
        resp = await self._request(
            "POST",
            f"{_ADS_BASE}/customers/{customer_id}:uploadCallConversions",
            headers=self._auth_headers(token),
            json={
                "conversions": [{
                    "callerId": caller_id,
                    "callStartDateTime": call_start_datetime,
                    "conversionDateTime": conversion_datetime,
                    "conversionAction": conversion_action,
                    "consent": {"adPersonalization": "GRANTED", "adUserData": "GRANTED"},
                }],
                "partialFailure": True,
                "validateOnly": False,
            },
        )
        if resp.status_code not in (200, 206):
            raise IntegrationError("google_ads", f"uploadCallConversions failed: {resp.text}", resp.status_code)
        return resp.json()
