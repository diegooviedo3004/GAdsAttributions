import httpx
import asyncio
import logging
from typing import Any
from app.core.exceptions import RetryableError, IntegrationError

_RETRY_STATUS = {429, 500, 502, 503, 504}
_DEFAULT_TIMEOUT = httpx.Timeout(30.0)
_DEFAULT_RETRIES = 3
_BACKOFF_BASE = 2.0


class BaseClient:
    service_name: str = "unknown"

    def __init__(self) -> None:
        self._log = logging.getLogger(f"integrations.{self.service_name}")
        self._client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        retries: int = _DEFAULT_RETRIES,
        **kwargs: Any,
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 2):
            try:
                self._log.debug(
                    "http request",
                    extra={"method": method, "url": url, "attempt": attempt},
                )
                resp = await self._client.request(method, url, **kwargs)
                self._log.debug(
                    "http response",
                    extra={"status": resp.status_code, "url": url},
                )
                if resp.status_code in _RETRY_STATUS and attempt <= retries:
                    wait = _BACKOFF_BASE ** attempt
                    self._log.warning(
                        "retrying after transient error",
                        extra={"status": resp.status_code, "wait_s": wait, "attempt": attempt},
                    )
                    await asyncio.sleep(wait)
                    continue
                return resp
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt <= retries:
                    wait = _BACKOFF_BASE ** attempt
                    self._log.warning(
                        "network error, retrying",
                        extra={"error": str(exc), "wait_s": wait, "attempt": attempt},
                    )
                    await asyncio.sleep(wait)
                    continue
                raise RetryableError(self.service_name, str(exc)) from exc
        raise RetryableError(self.service_name, f"exhausted retries: {last_exc}")

    async def aclose(self) -> None:
        await self._client.aclose()
