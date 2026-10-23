"""Application-database persistence for derived daily limit-up/down counts."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .models import MarketReviewDailyCounts, utc_now
from .review_counts import COVERAGE_DERIVED, LimitCounts


class ReviewCountsStoreError(RuntimeError):
    """The application database cannot read or write derived limit counts."""


class ReviewCountsStore(Protocol):
    def counts(self, start: date, end: date) -> dict[date, LimitCounts]: ...

    def latest_trading_day(self) -> date | None: ...

    def upsert(self, counts: Sequence[LimitCounts]) -> int: ...


class SqlReviewCountsStore:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def counts(self, start: date, end: date) -> dict[date, LimitCounts]:
        try:
            with self._sessions() as session:
                rows = session.scalars(
                    select(MarketReviewDailyCounts)
                    .where(
                        MarketReviewDailyCounts.trading_day >= start,
                        MarketReviewDailyCounts.trading_day <= end,
                    )
                    .order_by(MarketReviewDailyCounts.trading_day)
                )
                return {
                    row.trading_day: LimitCounts(
                        trading_day=row.trading_day,
                        limit_up_close_count=row.limit_up_close_count,
                        limit_down_close_count=row.limit_down_close_count,
                        raw_limit_up_close_count=row.raw_limit_up_close_count,
                        raw_limit_down_close_count=row.raw_limit_down_close_count,
                        rule_known_bar_count=row.rule_known_bar_count,
                        st_observed_bar_count=row.st_observed_bar_count,
                        ipo_window_bar_count=row.ipo_window_bar_count,
                        coverage_status=row.coverage_status,
                    )
                    for row in rows
                }
        except SQLAlchemyError as error:
            raise ReviewCountsStoreError from error

    def latest_trading_day(self) -> date | None:
        try:
            with self._sessions() as session:
                return session.scalar(select(func.max(MarketReviewDailyCounts.trading_day)))
        except SQLAlchemyError as error:
            raise ReviewCountsStoreError from error

    def upsert(self, counts: Sequence[LimitCounts]) -> int:
        if not counts:
            return 0
        computed_at = utc_now()
        values = [
            {
                "trading_day": item.trading_day,
                "limit_up_close_count": item.limit_up_close_count,
                "limit_down_close_count": item.limit_down_close_count,
                "raw_limit_up_close_count": item.raw_limit_up_close_count,
                "raw_limit_down_close_count": item.raw_limit_down_close_count,
                "rule_known_bar_count": item.rule_known_bar_count,
                "st_observed_bar_count": item.st_observed_bar_count,
                "ipo_window_bar_count": item.ipo_window_bar_count,
                "coverage_status": item.coverage_status,
                "computed_at": computed_at,
            }
            for item in counts
        ]
        try:
            with self._sessions.begin() as session:
                dialect = session.get_bind().dialect.name
                session.execute(_upsert_statement(dialect, values))
        except SQLAlchemyError as error:
            raise ReviewCountsStoreError from error
        return len(values)


def _preserved(table, inserted):
    """A stored row wins when the incoming result saw fewer usable bars or lost coverage.

    The comparison is rendered into the upsert itself so a concurrent refresh
    cannot interleave between a read and a write and replace a better result.
    """

    return or_(
        table.rule_known_bar_count > inserted.rule_known_bar_count,
        and_(
            table.coverage_status == COVERAGE_DERIVED,
            inserted.coverage_status != COVERAGE_DERIVED,
        ),
    )


def _upsert_statement(dialect: str, values: list[dict]):
    table = MarketReviewDailyCounts
    if dialect == "sqlite":
        statement = sqlite_insert(table).values(values)
        return statement.on_conflict_do_update(
            index_elements=[table.trading_day],
            set_={
                "limit_up_close_count": statement.excluded.limit_up_close_count,
                "limit_down_close_count": statement.excluded.limit_down_close_count,
                "raw_limit_up_close_count": statement.excluded.raw_limit_up_close_count,
                "raw_limit_down_close_count": statement.excluded.raw_limit_down_close_count,
                "rule_known_bar_count": statement.excluded.rule_known_bar_count,
                "st_observed_bar_count": statement.excluded.st_observed_bar_count,
                "ipo_window_bar_count": statement.excluded.ipo_window_bar_count,
                "coverage_status": statement.excluded.coverage_status,
                "computed_at": statement.excluded.computed_at,
            },
            where=~_preserved(table, statement.excluded),
        )
    if dialect == "mysql":
        statement = mysql_insert(table).values(values)
        allowed = ~_preserved(table, statement.inserted)
        return statement.on_duplicate_key_update(
            limit_up_close_count=case(
                (allowed, statement.inserted.limit_up_close_count),
                else_=table.limit_up_close_count,
            ),
            limit_down_close_count=case(
                (allowed, statement.inserted.limit_down_close_count),
                else_=table.limit_down_close_count,
            ),
            raw_limit_up_close_count=case(
                (allowed, statement.inserted.raw_limit_up_close_count),
                else_=table.raw_limit_up_close_count,
            ),
            raw_limit_down_close_count=case(
                (allowed, statement.inserted.raw_limit_down_close_count),
                else_=table.raw_limit_down_close_count,
            ),
            rule_known_bar_count=case(
                (allowed, statement.inserted.rule_known_bar_count),
                else_=table.rule_known_bar_count,
            ),
            st_observed_bar_count=case(
                (allowed, statement.inserted.st_observed_bar_count),
                else_=table.st_observed_bar_count,
            ),
            ipo_window_bar_count=case(
                (allowed, statement.inserted.ipo_window_bar_count),
                else_=table.ipo_window_bar_count,
            ),
            coverage_status=case(
                (allowed, statement.inserted.coverage_status),
                else_=table.coverage_status,
            ),
            computed_at=case(
                (allowed, statement.inserted.computed_at),
                else_=table.computed_at,
            ),
        )
    raise ReviewCountsStoreError(f"unsupported application database dialect: {dialect}")
