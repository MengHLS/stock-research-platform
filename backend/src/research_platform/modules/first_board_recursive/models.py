"""Imported, immutable first-board recursive structure snapshots."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import Mapped, mapped_column

from research_platform.core.database import Base

timestamp_type = DateTime().with_variant(MySQLDateTime(fsp=6), "mysql")
SNAPSHOT_ID = "research_first_board_recursive_snapshot"


class FirstBoardRecursiveSnapshot(Base):
    """One verified frozen delivery. Counts are the delivery's declared counts."""

    __tablename__ = SNAPSHOT_ID
    __table_args__ = (Index("ix_first_board_recursive_snapshot_day", "trade_date", "board_scope"),)

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    board_scope: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Declared identity of the consumed source snapshot (summary.sourceManifestSha256).
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Fingerprint of the delivered files themselves, so a changed delivery is visible.
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    first_board_count: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_link_count: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(timestamp_type, nullable=False)


class FirstBoardRecursiveTarget(Base):
    """Recursive result per target stock; both layers plus the legacy-rule audit."""

    __tablename__ = "research_first_board_recursive_target"
    __table_args__ = (
        Index("ix_first_board_recursive_target_stage", "snapshot_id", "result_stage"),
    )

    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SNAPSHOT_ID}.snapshot_id"), primary_key=True
    )
    stock_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    target_order: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_name: Mapped[str] = mapped_column(String(32), nullable=False)
    theme: Mapped[str | None] = mapped_column(String(32))
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_close: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    limit_rate: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    # The delivery's ``boardCount`` is a text label such as "1" or "8天4板"; the
    # integer column is only filled when that text is purely numeric.
    board_count: Mapped[int | None] = mapped_column(Integer)
    board_count_text: Mapped[str | None] = mapped_column(String(24))
    first_board_since_2019: Mapped[int | None] = mapped_column(Integer)
    prior_first_board_count: Mapped[int | None] = mapped_column(Integer)
    prior_eligible_non_st_count: Mapped[int | None] = mapped_column(Integer)

    nearest_prior_date: Mapped[date | None] = mapped_column(Date)
    nearest_stage: Mapped[str | None] = mapped_column(String(48))
    nearest_distance_sessions: Mapped[int | None] = mapped_column(Integer)

    anchor_date: Mapped[date | None] = mapped_column(Date)
    anchor_stage: Mapped[str | None] = mapped_column(String(48))
    anchor_reference_peak_date: Mapped[date | None] = mapped_column(Date)
    anchor_reference_peak: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    anchor_pullback_low_date: Mapped[date | None] = mapped_column(Date)
    anchor_pullback_low: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    anchor_pullback_pct: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    anchor_first_close_break_date: Mapped[date | None] = mapped_column(Date)
    anchor_target_close_vs_reference_pct: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    anchor_distance_sessions: Mapped[int | None] = mapped_column(Integer)

    selection_reason: Mapped[str] = mapped_column(String(48), nullable=False)
    result_stage: Mapped[str] = mapped_column(String(48), nullable=False)
    # Derived: the recursive layer stopped earlier than the nearest prior first board.
    layers_diverge: Mapped[bool] = mapped_column(Boolean, nullable=False)
    relation_status: Mapped[str | None] = mapped_column(String(48))
    diagnostic_codes: Mapped[str | None] = mapped_column(String(512))
    diagnostic_detail: Mapped[str | None] = mapped_column(String(1024))

    legacy_anchor_date: Mapped[date | None] = mapped_column(Date)
    legacy_anchor_stage: Mapped[str | None] = mapped_column(String(48))
    legacy_selection_reason: Mapped[str | None] = mapped_column(String(48))
    code_correction_from: Mapped[str | None] = mapped_column(String(16))
    code_correction_to: Mapped[str | None] = mapped_column(String(16))


class FirstBoardRecursiveCandidate(Base):
    """Every eligible prior first board of one target; the recursive window and history."""

    __tablename__ = "research_first_board_recursive_candidate"
    __table_args__ = (
        Index("ix_first_board_recursive_candidate_stock", "stock_code", "candidate_date"),
    )

    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SNAPSHOT_ID}.snapshot_id"), primary_key=True
    )
    stock_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    candidate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    rank_oldest: Mapped[int] = mapped_column(Integer, nullable=False)
    rank_nearest: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(48), nullable=False)
    limit_rate: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    anchor_session_distance: Mapped[int | None] = mapped_column(Integer)
    reference_peak_date: Mapped[date | None] = mapped_column(Date)
    reference_peak: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    pullback_low_date: Mapped[date | None] = mapped_column(Date)
    pullback_low: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    pullback_pct: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    first_close_break_date: Mapped[date | None] = mapped_column(Date)
    target_close_vs_reference_pct: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    is_selected_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_legacy_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False)
    selection_reason: Mapped[str | None] = mapped_column(String(48))
    legacy_selection_reason: Mapped[str | None] = mapped_column(String(48))
    relation_status: Mapped[str | None] = mapped_column(String(48))
    relation_price_reasons: Mapped[str | None] = mapped_column(String(512))
    relation_price_diagnostic: Mapped[str | None] = mapped_column(String(1024))
