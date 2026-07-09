"""FastAPI application factory."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from .api.middleware import RequestIdMiddleware
from .api.v1.ai import router as ai_router
from .api.v1.alerts import router as alerts_router
from .api.v1.auth import router as auth_router
from .api.v1.health import router as health_router
from .api.v1.wallets import router as wallets_router
from .core.config import get_settings
from .core.errors import AppError
from .core.logging import configure_logging, get_logger
from .db.session import dispose_engine
from .providers.registry import get_provider


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger(__name__)
    log.info("startup environment=%s", get_settings().environment)
    _ = get_provider()  # warm up provider (validates config eagerly)
    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            await get_provider().aclose()
        await dispose_engine()
        log.info("shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Crypto Intelligence Platform API",
        version="0.1.0",
        description="Read-only crypto wallet intelligence, monitoring, and alerting.",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    if settings.trusted_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.trusted_hosts,
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers={"X-Request-ID": request.headers.get("X-Request-ID", "-")},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        log = get_logger(__name__)
        log.exception("unhandled error rid=%s", request.headers.get("X-Request-ID", "-"))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "internal error"}},
            headers={"X-Request-ID": request.headers.get("X-Request-ID", "-")},
        )

    api_v1_prefix = "/api/v1"
    app.include_router(health_router, prefix=api_v1_prefix)
    app.include_router(auth_router, prefix=api_v1_prefix)
    app.include_router(wallets_router, prefix=api_v1_prefix)
    app.include_router(alerts_router, prefix=api_v1_prefix)
    app.include_router(ai_router, prefix=api_v1_prefix)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"name": "crypto-intelligence-platform", "status": "ok"}

    return app


app = create_app()
