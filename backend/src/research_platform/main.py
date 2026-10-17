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
from research_platform.core.database import make_engine, session_dependency
from research_platform.core.errors import DomainError
from research_platform.modules.catalog.router import router as catalog_router
from research_platform.modules.execution.router import router as execution_router


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    version: str
    authentication: Literal["not_configured"] = "not_configured"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.require_development_release()
    engine = make_engine(settings.database_url.get_secret_value())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(title="Stock Research Platform", version=__version__, lifespan=lifespan)
    app.state.sessions = sessionmaker(engine, expire_on_commit=False)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, error: DomainError) -> JSONResponse:
        status = 404 if error.code.endswith("NOT_FOUND") else 409
        return JSONResponse(
            status_code=status, content={"detail": {"code": error.code, "message": error.message}}
        )

    @app.get("/health/live", response_model=Health, operation_id="get_liveness")
    def liveness() -> Health:
        return Health(status="ok", version=__version__)

    @app.get(
        "/health/ready",
        response_model=Health,
        responses={503: {"model": Health}},
        operation_id="get_readiness",
    )
    def readiness(session: Annotated[Session, Depends(session_dependency)]):
        try:
            session.execute(text("SELECT id FROM execution_job LIMIT 1"))
        except SQLAlchemyError:
            return JSONResponse(
                status_code=503,
                content=Health(status="unavailable", version=__version__).model_dump(),
            )
        return Health(status="ok", version=__version__)

    app.include_router(catalog_router)
    app.include_router(execution_router)
    return app
