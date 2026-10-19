"""Composition root: the only place that wires infrastructure to modules."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from research_platform import __version__
from research_platform.core.config import Settings
from research_platform.core.database import (
    make_application_engine,
    make_source_engine,
    session_dependency,
)
from research_platform.core.error_handlers import install_error_handlers
from research_platform.core.errors import DEFAULT_ERROR_RESPONSES
from research_platform.core.logging import ROLE_API, configure_logging, log_event
from research_platform.core.middleware import RequestContextMiddleware
from research_platform.core.upstream import UpstreamClient
from research_platform.modules.catalog.router import router as catalog_router
from research_platform.modules.execution.router import router as execution_router
from research_platform.modules.identity.router import router as identity_router
from research_platform.modules.market.legacy_review_source import LegacyMarketReviewSource
from research_platform.modules.market.review import MarketReviewService
from research_platform.modules.market.router import router as market_router
from research_platform.modules.market.service import MarketService

SessionDep = Annotated[Session, Depends(session_dependency)]


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    version: str
    authentication: Literal["not_configured"] = "not_configured"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.require_development_release()
    configure_logging(role=ROLE_API, level=settings.log_level)
    engine = make_application_engine(settings)
    source_engine = make_source_engine(settings) if settings.source_mysql else None
    upstream = UpstreamClient(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log_event("api.started", version=__version__, environment=settings.environment)
        try:
            yield
        finally:
            upstream.close()
            if source_engine is not None:
                source_engine.dispose()
            engine.dispose()
            log_event("api.stopped", version=__version__)

    app = FastAPI(
        title="磐石 Quant Lab",
        version=__version__,
        lifespan=lifespan,
        # One shared error body is declared once so generated clients can type
        # failures; the handlers below produce exactly this shape.
        responses=DEFAULT_ERROR_RESPONSES,
    )
    app.state.settings = settings
    app.state.sessions = sessionmaker(engine, expire_on_commit=False)
    # Public market data is not user-scoped and is never persisted; the service
    # owns its own TTL cache and is closed with the API lifecycle.
    app.state.market = MarketService(settings, upstream)
    app.state.market_review = MarketReviewService(
        LegacyMarketReviewSource(source_engine) if source_engine is not None else None,
        settings.review,
    )
    install_error_handlers(app)
    # Added last so it is outermost: ids exist before any handler or route runs.
    app.add_middleware(RequestContextMiddleware)

    @app.get("/health/live", response_model=Health, operation_id="get_liveness")
    def liveness() -> Health:
        return Health(status="ok", version=__version__)

    @app.get(
        "/health/ready",
        response_model=Health,
        responses={503: {"model": Health}},
        operation_id="get_readiness",
    )
    def readiness(request: Request, session: SessionDep):
        try:
            session.execute(text("SELECT id FROM execution_job LIMIT 1"))
        except SQLAlchemyError:
            # Readiness failure is a real dependency failure, not a business
            # error: keep the documented Health body and record a safe event.
            log_event(
                "readiness.unavailable",
                level=logging.WARNING,
                code="DATABASE_UNAVAILABLE",
                category="unavailable",
            )
            request.scope["state"]["error_code"] = "DATABASE_UNAVAILABLE"
            return JSONResponse(
                status_code=503,
                content=Health(status="unavailable", version=__version__).model_dump(),
            )
        return Health(status="ok", version=__version__)

    app.include_router(catalog_router)
    app.include_router(execution_router)
    app.include_router(identity_router)
    app.include_router(market_router)
    return app
