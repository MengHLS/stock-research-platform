import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from research_platform.core.config import Settings
from research_platform.core.database import make_engine
from research_platform.main import create_app
from research_platform.modules.identity.dependencies import Actor, require_actor

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def without_ambient_rp_variables(monkeypatch):
    """Tests set their own RP_* values; _env_file=None alone cannot isolate them."""
    for name in [key for key in os.environ if key.startswith("RP_")]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def database_url(tmp_path):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    engine = make_engine(url)
    config = Config(str(ROOT / "backend/alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.upgrade(config, "head")
    engine.dispose()
    return url


@pytest.fixture
def session(database_url):
    engine = make_engine(database_url)
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture
def client_factory(database_url):
    clients = []

    def make(user_id=None):
        app = create_app(Settings(environment="test", database_url=database_url, _env_file=None))
        if user_id is not None:
            app.dependency_overrides[require_actor] = lambda: Actor(user_id=user_id)
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)
