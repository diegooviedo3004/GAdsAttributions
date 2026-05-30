class AppError(Exception):
    """Base for all application errors."""


class WorkflowStopError(AppError):
    """Raised to halt a workflow without it being a failure (filter not met)."""
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class IntegrationError(AppError):
    """An external API returned an unexpected error."""
    def __init__(self, service: str, message: str, status_code: int | None = None) -> None:
        self.service = service
        self.status_code = status_code
        super().__init__(f"[{service}] {message}")


class RetryableError(IntegrationError):
    """Transient error — caller should retry."""


class AuthError(IntegrationError):
    """Authentication / authorisation failure."""


class ValidationError(AppError):
    """Incoming payload failed validation."""
