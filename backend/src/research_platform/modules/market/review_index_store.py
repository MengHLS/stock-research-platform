"""Application-database persistence for review-only public index bars."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from sqlalchemy import case, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import ReviewIndexDailyBar
from .review import IndexBar


class ReviewIndexStoreError(RuntimeError):
    """The application database cannot read or write persisted index bars."""


class ReviewIndexBarStore(Protocol):
    def index_rows(
        self,
        start: date,
        end: date,
        symbols: list[str],
    ) -> dict[str, list[IndexBar]]: ...

    def latest_fetched_at(self, symbol: str) -> datetime | None: ...

    def upsert(
        self,
        symbol: str,
        bars: list[IndexBar],
        *,
        provider: str,
        fetched_at: datetime,
    ) -> None: ...


class SqlReviewIndexStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def index_rows(
        self,
        start: date,
        end: date,
        symbols: list[str],
    ) -> dict[str, list[IndexBar]]:
        result: dict[str, list[IndexBar]] = {symbol: [] for symbol in symbols}
        try:
            with self._sessions() as session:
                rows = session.scalars(
                    select(ReviewIndexDailyBar)
                    .where(
                        ReviewIndexDailyBar.symbol.in_(symbols),
                        ReviewIndexDailyBar.trading_day >= start,
                        ReviewIndexDailyBar.trading_day <= end,
                    )
                    .order_by(
                        ReviewIndexDailyBar.symbol,
                        ReviewIndexDailyBar.trading_day,
                    )
                )
                for row in rows:
                    result.setdefault(row.symbol, []).append(
                        IndexBar(
                            trading_day=row.trading_day,
                            symbol=row.symbol,
                            open=row.open,
                            high=row.high,
                            low=row.low,
                            close=row.close,
                            amount_source=None,
                            volume_source=None,
                        )
                    )
        except SQLAlchemyError as error:
            raise ReviewIndexStoreError from error
        return result

    def latest_fetched_at(self, symbol: str) -> datetime | None:
        try:
            with self._sessions() as session:
                return session.scalar(
                    select(func.max(ReviewIndexDailyBar.fetched_at)).where(
                        ReviewIndexDailyBar.symbol == symbol
                    )
                )
        except SQLAlchemyError as error:
            raise ReviewIndexStoreError from error

    def upsert(
        self,
        symbol: str,
        bars: list[IndexBar],
        *,
        provider: str,
        fetched_at: datetime,
    ) -> None:
        if not bars:
            return
        values = [
            {
                "symbol": symbol,
                "trading_day": bar.trading_day,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "provider": provider,
                "fetched_at": fetched_at,
            }
            for bar in bars
            if all(value is not None for value in (bar.open, bar.high, bar.low, bar.close))
        ]
        if not values:
            return
        try:
            with self._sessions.begin() as session:
                dialect = session.get_bind().dialect.name
                statement = _upsert_statement(dialect, values)
                session.execute(statement)
        except SQLAlchemyError as error:
            raise ReviewIndexStoreError from error


def _upsert_statement(dialect: str, values: list[dict]):
    if dialect == "sqlite":
        statement = sqlite_insert(ReviewIndexDailyBar).values(values)
        return statement.on_conflict_do_update(
            index_elements=[
                ReviewIndexDailyBar.symbol,
                ReviewIndexDailyBar.trading_day,
            ],
            set_={
                "open": statement.excluded.open,
                "high": statement.excluded.high,
                "low": statement.excluded.low,
                "close": statement.excluded.close,
                "provider": statement.excluded.provider,
                "fetched_at": statement.excluded.fetched_at,
            },
            where=ReviewIndexDailyBar.fetched_at <= statement.excluded.fetched_at,
        )
    if dialect == "mysql":
        statement = mysql_insert(ReviewIndexDailyBar).values(values)
        newer = ReviewIndexDailyBar.fetched_at <= statement.inserted.fetched_at
        return statement.on_duplicate_key_update(
            open=case(
                (newer, statement.inserted.open),
                else_=ReviewIndexDailyBar.open,
            ),
            high=case(
                (newer, statement.inserted.high),
                else_=ReviewIndexDailyBar.high,
            ),
            low=case(
                (newer, statement.inserted.low),
                else_=ReviewIndexDailyBar.low,
            ),
            close=case(
                (newer, statement.inserted.close),
                else_=ReviewIndexDailyBar.close,
            ),
            provider=case(
                (newer, statement.inserted.provider),
                else_=ReviewIndexDailyBar.provider,
            ),
            fetched_at=case(
                (newer, statement.inserted.fetched_at),
                else_=ReviewIndexDailyBar.fetched_at,
            ),
        )
    raise ReviewIndexStoreError(f"unsupported application database dialect: {dialect}")
