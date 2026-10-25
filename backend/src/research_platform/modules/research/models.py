"""Versioned, shared market observations; no private user data."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import Mapped, mapped_column

from research_platform.core.database import Base

timestamp_type = DateTime().with_variant(MySQLDateTime(fsp=6), "mysql")


class FirstBoardDailyBatch(Base):
    __tablename__ = "research_first_board_daily_batch"
    __table_args__ = (Index("ix_first_board_batch_day", "trading_day", "computed_at"),)

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    dataset_version_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    universe_definition: Mapped[str] = mapped_column(Text, nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(48), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(48), nullable=False)
    source_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(timestamp_type, nullable=False)


class FirstBoardBackgroundEvent(Base):
    __tablename__ = "research_first_board_background_event"
    __table_args__ = (Index("ix_first_board_event_stock", "stock_code", "trading_day"),)

    batch_id: Mapped[str] = mapped_column(
        ForeignKey("research_first_board_daily_batch.batch_id"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trading_day: Mapped[date] = mapped_column(Date, nullable=False)
    stock_code: Mapped[str] = mapped_column(String(16), nullable=False)
    feature_cutoff: Mapped[date | None] = mapped_column(Date)
    class_code: Mapped[str | None] = mapped_column(String(16))
    group_code: Mapped[str | None] = mapped_column(String(16))
    position_band: Mapped[str] = mapped_column(String(16), nullable=False)
    trend: Mapped[str] = mapped_column(String(16), nullable=False)
    short_path: Mapped[str] = mapped_column(String(24), nullable=False)
    position_60d_pct: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    return_5d_pct: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    return_20d_pct: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    return_60d_pct: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    ma_20: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    ma_60: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    quality_status: Mapped[str] = mapped_column(String(16), nullable=False)
    feature_reason: Mapped[str | None] = mapped_column(String(512))


class FirstBoardDailyCurrent(Base):
    """The selected snapshot can change without mutating historical observations."""

    __tablename__ = "research_first_board_daily_current"

    trading_day: Mapped[date] = mapped_column(Date, primary_key=True)
    taxonomy_version: Mapped[str] = mapped_column(String(48), primary_key=True)
    feature_version: Mapped[str] = mapped_column(String(48), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("research_first_board_daily_batch.batch_id"), nullable=False
    )
