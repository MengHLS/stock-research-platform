from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | URL, connect_args: dict | None = None) -> Engine:
    driver = url.drivername if isinstance(url, URL) else url.split(":", 1)[0]
    options = {"check_same_thread": False} if driver.startswith("sqlite") else {}
    options.update(connect_args or {})
    return create_engine(url, pool_pre_ping=True, connect_args=options, hide_parameters=True)


def make_application_engine(settings: Settings) -> Engine:
    options = settings.database_mysql.connect_args() if settings.database_mysql else None
    return make_engine(settings.application_url(), options)


def make_source_engine(settings: Settings) -> Engine:
    if settings.source_mysql is None:
        raise ValueError("SOURCE_NOT_CONFIGURED")
    # Credentials must be SELECT-only at the server; no ORM metadata/migrations are bound here.
    return make_engine(settings.source_mysql.url(), settings.source_mysql.connect_args())


def session_dependency(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.sessions
    with factory() as session:
        yield session
