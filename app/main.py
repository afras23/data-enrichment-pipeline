"""
FastAPI application factory and ASGI entrypoint.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.correlation import CorrelationIdMiddleware
from app.api.routes import enrichment, health
from app.config import settings
from app.db.session import engine
from app.services.alerting import MockCompositeNotifier

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Startup/shutdown hooks."""

    app.state.notifier = MockCompositeNotifier()
    logger.info("Application startup", extra={"env": settings.app_env})
    yield
    await engine.dispose()
    logger.info("Application shutdown", extra={"env": settings.app_env})


def create_app() -> FastAPI:
    """Build FastAPI app with middleware and routers."""

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = settings.api_prefix.rstrip("/")
    app.include_router(health.router, prefix=api)
    app.include_router(enrichment.router, prefix=api)

    return app


app = create_app()
