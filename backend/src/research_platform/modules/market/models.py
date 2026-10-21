"""Persistent read-through cache for the cross-market overview."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Numeric, String
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import Mapped, mapped_column

from research_platform.core.database import Base


def utc_now() -> datetime:
    """Application timestamps are stored as naive UTC and serialized with UTC."""
    return datetime.now(UTC).replace(tzinfo=None)


class GlobalMarketQuoteSnapshot(Base):
    __tablename__ = "market_global_quote_snapshot"

    instrument_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    open: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    high: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    low: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    change: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    quote_time: Mapped[datetime | None] = mapped_column(DateTime)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class GlobalMarketDailyBar(Base):
    __tablename__ = "market_global_daily_bar"
    __table_args__ = (Index("ix_global_bar_day", "trading_day"),)

    instrument_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ReviewIndexDailyBar(Base):
    """Persisted daily bars for review indices absent from the legacy source."""

    __tablename__ = "market_review_index_daily"
    __table_args__ = (Index("ix_review_index_daily_day", "trading_day"),)

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(MySQLDateTime(fsp=6), "mysql"),
        nullable=False,
    )
