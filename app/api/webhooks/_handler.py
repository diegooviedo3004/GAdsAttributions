"""
Shared conversion request handler.

Both webhook routes follow the same flow:
  1. Assign a request ID and set logging context
  2. Call the provided async sender function
  3. Return the upstream response (or a structured error)

Routes are responsible only for defining their schema and wiring the sender.
"""
import uuid
import time
import logging
from typing import Any, Callable, Awaitable
from fastapi.responses import JSONResponse

from app.core.logging import set_request_context
from app.core.exceptions import IntegrationError, AuthError, AppError

type Sender = Callable[[Any], Awaitable[dict]]


async def handle_conversion(
    *,
    workflow_name: str,
    payload: Any,
    send: Sender,
) -> JSONResponse:
    request_id = str(uuid.uuid4())
    set_request_context(request_id=request_id, workflow=workflow_name)

    log = logging.getLogger(f"webhooks.{workflow_name}")
    log.info("request received", extra={"request_id": request_id})

    start = time.perf_counter()
    try:
        result = await send(payload)
        duration_ms = round((time.perf_counter() - start) * 1000)
        log.info(
            "request completed",
            extra={"request_id": request_id, "duration_ms": duration_ms, "status": "success"},
        )
        return JSONResponse(status_code=200, content=result)

    except AuthError as exc:
        duration_ms = round((time.perf_counter() - start) * 1000)
        log.error(
            "authentication failed",
            extra={"request_id": request_id, "service": exc.service, "duration_ms": duration_ms},
        )
        return JSONResponse(status_code=401, content={"error": str(exc), "service": exc.service})

    except IntegrationError as exc:
        duration_ms = round((time.perf_counter() - start) * 1000)
        log.error(
            "upstream error",
            extra={
                "request_id": request_id,
                "service": exc.service,
                "status_code": exc.status_code,
                "duration_ms": duration_ms,
            },
        )
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "service": exc.service, "upstream_status": exc.status_code},
        )

    except AppError as exc:
        duration_ms = round((time.perf_counter() - start) * 1000)
        log.error(
            "application error",
            extra={"request_id": request_id, "duration_ms": duration_ms},
            exc_info=True,
        )
        return JSONResponse(status_code=500, content={"error": str(exc)})

    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000)
        log.error(
            "unexpected error",
            extra={"request_id": request_id, "duration_ms": duration_ms},
            exc_info=True,
        )
        return JSONResponse(status_code=500, content={"error": "internal server error"})
