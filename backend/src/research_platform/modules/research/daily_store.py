"""Atomic, content-addressed daily snapshots in the application database."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from research_platform.core.errors import DomainError

from .models import FirstBoardBackgroundEvent, FirstBoardDailyBatch, FirstBoardDailyCurrent


class SqlFirstBoardStore:
    def __init__(self, sessions):
        self.sessions = sessions

    def publish(self, batch: dict, events: list[dict]) -> None:
        try:
            with self.sessions.begin() as session:
                dialect = session.get_bind().dialect.name
                session.execute(_insert_once(dialect, FirstBoardDailyBatch, [batch]))
                for offset in range(0, len(events), 200):
                    session.execute(
                        _insert_once(
                            dialect, FirstBoardBackgroundEvent, events[offset : offset + 200]
                        )
                    )
                count = session.scalar(
                    select(func.count())
                    .select_from(FirstBoardBackgroundEvent)
                    .where(FirstBoardBackgroundEvent.batch_id == batch["batch_id"])
                )
                if count != batch["source_event_count"]:
                    raise DomainError("FIRST_BOARD_STORAGE_BAD_DATA")
                values = {
                    key: batch[key]
                    for key in ("trading_day", "taxonomy_version", "feature_version", "batch_id")
                }
                session.execute(_select_current(dialect, values))
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_STORAGE_UNAVAILABLE") from None

    def read(
        self,
        day: date | None,
        taxonomy_version: str,
        feature_version: str,
        *,
        batch_id: str | None = None,
    ):
        try:
            with self.sessions() as session:
                statement = select(FirstBoardDailyBatch).where(
                    FirstBoardDailyBatch.taxonomy_version == taxonomy_version,
                    FirstBoardDailyBatch.feature_version == feature_version,
                )
                if day is not None:
                    statement = statement.where(FirstBoardDailyBatch.trading_day == day)
                if batch_id is not None:
                    statement = statement.where(FirstBoardDailyBatch.batch_id == batch_id)
                else:
                    statement = statement.join(
                        FirstBoardDailyCurrent,
                        FirstBoardDailyCurrent.batch_id == FirstBoardDailyBatch.batch_id,
                    )
                batch = session.scalar(
                    statement.order_by(
                        FirstBoardDailyBatch.trading_day.desc(),
                        FirstBoardDailyBatch.computed_at.desc(),
                        FirstBoardDailyBatch.batch_id.desc(),
                    ).limit(1)
                )
                if batch is None:
                    return None, []
                events = list(
                    session.scalars(
                        select(FirstBoardBackgroundEvent)
                        .where(FirstBoardBackgroundEvent.batch_id == batch.batch_id)
                        .order_by(
                            FirstBoardBackgroundEvent.stock_code, FirstBoardBackgroundEvent.event_id
                        )
                    )
                )
                if len(events) != batch.source_event_count:
                    raise DomainError("FIRST_BOARD_STORAGE_BAD_DATA")
                session.expunge_all()
                return batch, events
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_STORAGE_UNAVAILABLE") from None

    def for_stock(self, stock_code: str):
        """Current snapshots only: superseded corrections stay auditable but hidden."""
        try:
            with self.sessions() as session:
                rows = list(
                    session.scalars(
                        select(FirstBoardBackgroundEvent)
                        .join(
                            FirstBoardDailyCurrent,
                            FirstBoardDailyCurrent.batch_id == FirstBoardBackgroundEvent.batch_id,
                        )
                        .where(FirstBoardBackgroundEvent.stock_code == stock_code)
                        .order_by(
                            FirstBoardBackgroundEvent.trading_day,
                            FirstBoardBackgroundEvent.event_id,
                        )
                    )
                )
                session.expunge_all()
                return rows
        except SQLAlchemyError:
            raise DomainError("FIRST_BOARD_STORAGE_UNAVAILABLE") from None


def _insert_once(dialect, model, values):
    if dialect == "sqlite":
        return sqlite_insert(model).values(values).on_conflict_do_nothing()
    if dialect == "mysql":
        statement = mysql_insert(model).values(values)
        # A no-op update handles duplicate keys without ignoring other SQL errors.
        return statement.on_duplicate_key_update(batch_id=statement.inserted.batch_id)
    raise DomainError("FIRST_BOARD_STORAGE_UNAVAILABLE")


def _select_current(dialect, values):
    model = FirstBoardDailyCurrent
    if dialect == "sqlite":
        statement = sqlite_insert(model).values(values)
        return statement.on_conflict_do_update(
            index_elements=[model.trading_day, model.taxonomy_version, model.feature_version],
            set_={"batch_id": statement.excluded.batch_id},
        )
    if dialect == "mysql":
        statement = mysql_insert(model).values(values)
        return statement.on_duplicate_key_update(batch_id=statement.inserted.batch_id)
    raise DomainError("FIRST_BOARD_STORAGE_UNAVAILABLE")
