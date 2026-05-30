from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.api.routes.health import router as health_router
from app.api.webhooks.callrail_attribution import router as callrail_router
from app.api.webhooks.phone_conversion import router as phone_conversion_router

log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    configure_logging(cfg.log_level)
    log.info("application starting", extra={"environment": cfg.environment})
    yield
    log.info("application shutting down")


app = FastAPI(
    title="VFC Automation Platform",
    description="Google Ads conversion tracking webhooks.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(health_router, tags=["Health"])
app.include_router(callrail_router, tags=["Webhooks"])
app.include_router(phone_conversion_router, tags=["Webhooks"])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled exception", extra={"path": request.url.path}, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})
