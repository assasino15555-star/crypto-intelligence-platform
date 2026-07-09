"""Application error model.

Distinct error types enable clean HTTP mapping and avoid leaking internal
details to API consumers.
"""

from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        if code:
            self.code = code


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class AuthError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


class ProviderError(AppError):
    status_code = 502
    code = "provider_unavailable"


class ProviderRetryableError(ProviderError):
    code = "provider_retryable"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderPermanentError(ProviderError):
    status_code = 400
    code = "provider_permanent"


class AiProviderError(AppError):
    status_code = 502
    code = "ai_unavailable"
