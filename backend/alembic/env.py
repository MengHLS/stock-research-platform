from alembic import context
from sqlalchemy import Connection

from research_platform.core.config import Settings
from research_platform.core.database import Base, make_application_engine
from research_platform.modules.catalog import models as catalog_models  # noqa: F401
from research_platform.modules.execution import models as execution_models  # noqa: F401

config = context.config
target_metadata = Base.metadata


def configure(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=Settings().application_url(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        configure(supplied)
    else:
        engine = make_application_engine(Settings())
        with engine.connect() as connection:
            configure(connection)
        engine.dispose()
