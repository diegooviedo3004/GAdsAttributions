import logging
import json
import time
import uuid
from contextvars import ContextVar
from typing import Any

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
workflow_var: ContextVar[str] = ContextVar("workflow", default="")

_MASKED = "***MASKED***"
_SECRET_KEYS = {
    "token", "secret", "password", "key", "auth", "refresh_token",
    "access_token", "client_secret", "authorization",
}


def _mask_value(key: str, value: Any) -> Any:
    if isinstance(key, str) and any(k in key.lower() for k in _SECRET_KEYS):
        return _MASKED
    return value


def _mask_dict(d: dict) -> dict:
    return {k: _mask_value(k, v) for k, v in d.items()}


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "workflow": workflow_var.get(""),
            "request_id": request_id_var.get(""),
            "correlation_id": correlation_id_var.get(""),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = {
            k: v for k, v in record.__dict__.items()
            if k not in logging.LogRecord.__dict__ and not k.startswith("_")
            and k not in ("msg", "args", "exc_info", "exc_text", "stack_info",
                          "lineno", "funcName", "filename", "module", "created",
                          "msecs", "relativeCreated", "thread", "threadName",
                          "processName", "process", "name", "levelname",
                          "levelno", "pathname", "message")
        }
        if extra:
            payload["extra"] = _mask_dict(extra)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def set_request_context(request_id: str = "", correlation_id: str = "", workflow: str = "") -> None:
    request_id_var.set(request_id or str(uuid.uuid4()))
    correlation_id_var.set(correlation_id or str(uuid.uuid4()))
    workflow_var.set(workflow)


class WorkflowTimer:
    def __init__(self, logger: logging.Logger, workflow: str) -> None:
        self._log = logger
        self._workflow = workflow
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        self._log.info("workflow started", extra={"workflow": self._workflow})
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = round((time.perf_counter() - self._start) * 1000)
        if exc_type:
            self._log.error(
                "workflow failed",
                extra={"workflow": self._workflow, "duration_ms": duration_ms},
                exc_info=True,
            )
        else:
            self._log.info(
                "workflow completed",
                extra={"workflow": self._workflow, "duration_ms": duration_ms, "status": "success"},
            )
        return False
