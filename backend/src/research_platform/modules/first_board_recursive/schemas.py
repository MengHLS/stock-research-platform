"""API contracts for the imported first-board recursive structure snapshot."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TimelineKind = Literal["FIRST_BOARD", "FIRST_CLOSE_BREAK", "TARGET"]
TimelineRole = Literal["ANCHOR", "SKIPPED", "NEAREST_PRIOR", "FIRST_CLOSE_BREAK", "TARGET"]


class SnapshotCountsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: int = Field(ge=0)
    first_boards_since_2019: int = Field(ge=0)
    candidate_links: int = Field(ge=0)


class SnapshotSourceRead(BaseModel):
    """Identity of the consumed frozen delivery; verification is never claimed as a rerun."""

    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["FROZEN_RESEARCH"] = "FROZEN_RESEARCH"
    source_sha256: str
    artifact_sha256: str
    verification_status: str
    verification_status_label: str
    uses_forward_data: Literal[False] = False


class SnapshotMetaRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str
    trade_date: date
    board_scope: str
    board_scope_label: str
    status: str
    status_label: str
    computed_at: datetime
    counts: SnapshotCountsRead
    stage_counts: dict[str, int]
    stage_labels: dict[str, str]
    selection_reason_counts: dict[str, int]
    selection_reason_labels: dict[str, str]
    source: SnapshotSourceRead


class TargetSummaryRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock_code: str
    stock_name: str
    theme: str | None
    target_order: int
    target_date: date
    target_close: Decimal | None
    limit_rate: Decimal | None
    board_count: int | None
    board_count_text: str | None
    result_stage: str
    result_stage_label: str
    selection_reason: str
    selection_reason_label: str
    nearest_prior_date: date | None
    nearest_prior_stage: str | None
    nearest_prior_stage_label: str | None
    anchor_date: date | None
    anchor_distance_sessions: int | None
    layers_diverge: bool
    relation_status: str | None
    relation_status_label: str | None


class SnapshotRead(SnapshotMetaRead):
    """Snapshot plus the target rows; candidates and timelines stay on the detail route."""

    targets: list[TargetSummaryRead]


class TargetRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    date: date
    close: Decimal | None
    limit_rate: Decimal | None
    theme: str | None
    board_count: int | None
    board_count_text: str | None
    first_board_since_2019: int | None
    prior_first_board_count: int | None
    prior_eligible_non_st_count: int | None
    stage_description: str
    explanation: str


class NearestPriorRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    distance_sessions: int | None
    stage: str | None
    stage_label: str | None
    label: str
    explanation: str
    is_recursive_anchor: bool


class RecursiveAnchorRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    distance_sessions: int | None
    stage: str
    stage_label: str
    reference_peak_date: date | None
    reference_peak: Decimal | None
    pullback_low_date: date | None
    pullback_low: Decimal | None
    pullback_pct: Decimal | None
    first_close_break_date: date | None
    target_close_vs_reference_pct: Decimal | None
    selection_reason: str
    selection_reason_label: str
    label: str
    explanation: str


class TimelineNodeRead(BaseModel):
    """One node of the recursive window only (date >= anchor, target last)."""

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    date: date
    kind: TimelineKind
    role: TimelineRole
    label: str
    stage: str | None
    stage_label: str | None
    is_selected_anchor: bool
    is_skipped: bool
    is_nearest_prior: bool
    is_before_anchor: bool
    limit_rate: Decimal | None
    reference_peak: Decimal | None
    pullback_low: Decimal | None
    first_close_break_date: date | None
    target_close_vs_reference_pct: Decimal | None
    note: str | None


class EarlierFirstBoardRead(BaseModel):
    """Folded history before the recursive anchor; never part of the main timeline."""

    model_config = ConfigDict(extra="forbid")

    date: date
    rank_oldest: int
    rank_nearest: int
    stage: str
    stage_label: str
    is_before_anchor: Literal[True] = True
    is_skipped: Literal[False] = False


class CandidateRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_date: date
    rank_oldest: int
    rank_nearest: int
    stage: str
    stage_label: str
    limit_rate: Decimal | None
    anchor_session_distance: int | None
    reference_peak_date: date | None
    reference_peak: Decimal | None
    pullback_low_date: date | None
    pullback_low: Decimal | None
    pullback_pct: Decimal | None
    first_close_break_date: date | None
    target_close_vs_reference_pct: Decimal | None
    is_selected_anchor: bool
    is_legacy_anchor: bool
    selection_reason: str | None
    selection_reason_label: str | None
    relation_status: str | None
    relation_status_label: str | None
    price_reasons: list[str]
    price_diagnostic: str | None


class AuditRead(BaseModel):
    """Old-rule audit and raw keys; deliberately kept out of the primary reading order."""

    model_config = ConfigDict(extra="forbid")

    code_correction_from: str | None
    code_correction_to: str | None
    legacy_anchor_date: date | None
    legacy_anchor_stage: str | None
    legacy_anchor_stage_label: str | None
    legacy_selection_reason: str | None
    legacy_selection_reason_label: str | None
    relation_status: str | None
    relation_status_label: str | None
    diagnostic_codes: list[str]
    diagnostic_detail: str | None


class TargetDetailRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: SnapshotMetaRead
    summary: TargetSummaryRead
    target: TargetRead
    nearest_prior: NearestPriorRead | None
    recursive_anchor: RecursiveAnchorRead | None
    timeline: list[TimelineNodeRead]
    earlier_first_boards: list[EarlierFirstBoardRead]
    candidates: list[CandidateRead]
    audit: AuditRead
    uses_forward_data: Literal[False] = False
