import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()
_START_TIME = time.time()


@router.get("/health", summary="Liveness check")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@router.get("/status", summary="Readiness and uptime")
async def status_endpoint() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "uptime_seconds": round(time.time() - _START_TIME),
    })


@router.get("/metrics", summary="Basic runtime metrics")
async def metrics() -> JSONResponse:
    import sys, os
    return JSONResponse({
        "status": "ok",
        "uptime_seconds": round(time.time() - _START_TIME),
        "python_version": sys.version,
        "pid": os.getpid(),
    })
