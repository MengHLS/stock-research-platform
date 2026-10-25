"""Application service for the imported first-board recursive snapshots.

The service only reads the application database. Import and verification of the
frozen delivery are explicit CLI operations, so an API request never reparses the
external delivery and never writes.
"""

from __future__ import annotations

import logging
from datetime import UTC, date
from decimal import Decimal
from typing import Any

from research_platform.core.errors import DomainError
from research_platform.core.logging import log_event

from . import labels
from .dataset_source import RecursiveDelivery
from .models import (
    FirstBoardRecursiveCandidate,
    FirstBoardRecursiveSnapshot,
    FirstBoardRecursiveTarget,
)
from .schemas import (
    AuditRead,
    CandidateRead,
    EarlierFirstBoardRead,
    NearestPriorRead,
    RecursiveAnchorRead,
    SnapshotCountsRead,
    SnapshotMetaRead,
    SnapshotRead,
    SnapshotSourceRead,
    TargetDetailRead,
    TargetRead,
    TargetSummaryRead,
    TimelineNodeRead,
)
from .store import SqlFirstBoardRecursiveStore

_KIND_ORDER = {"FIRST_BOARD": 0, "FIRST_CLOSE_BREAK": 1, "TARGET": 2}
_DECIMAL_TOLERANCE = Decimal("0.000000001")
_VERIFY_MISMATCH_LIMIT = 20


class FirstBoardRecursiveService:
    def __init__(self, store: SqlFirstBoardRecursiveStore) -> None:
        self.store = store

    def snapshot(self, trade_date: date | None = None) -> SnapshotRead:
        row = self._require_snapshot(trade_date)
        targets = self.store.targets(row.snapshot_id)
        meta = self._meta(row)
        return SnapshotRead(**meta.model_dump(), targets=[_summary(item) for item in targets])

    def target_detail(self, stock_code: str, trade_date: date | None = None) -> TargetDetailRead:
        symbol = stock_code.strip().upper()
        row = self._require_snapshot(trade_date)
        target = self.store.target(row.snapshot_id, symbol)
        if target is None:
            raise DomainError("FIRST_BOARD_RECURSIVE_TARGET_NOT_FOUND")
        candidates = self.store.candidates(row.snapshot_id, symbol)
        if not candidates and target.anchor_date is not None:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_BAD_DATA")
        meta = self._meta(row)
        anchor = _anchor(target)
        return TargetDetailRead(
            snapshot=meta,
            summary=_summary(target),
            target=_target_card(target),
            nearest_prior=_nearest_prior(target),
            recursive_anchor=anchor,
            timeline=_timeline(target, candidates, anchor),
            earlier_first_boards=_earlier_first_boards(target, candidates),
            candidates=[_candidate(item) for item in candidates],
            audit=_audit(target),
        )

    def _require_snapshot(self, trade_date: date | None) -> FirstBoardRecursiveSnapshot:
        row = self.store.snapshot(trade_date)
        if row is None:
            raise DomainError("FIRST_BOARD_RECURSIVE_SNAPSHOT_NOT_FOUND")
        return row

    def _meta(self, row: FirstBoardRecursiveSnapshot) -> SnapshotMetaRead:
        derived = self.store.derived_counts(row.snapshot_id)
        if (
            derived["targets"] != row.target_count
            or derived["candidates"] != row.candidate_link_count
        ):
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_BAD_DATA")
        return SnapshotMetaRead(
            snapshot_id=row.snapshot_id,
            trade_date=row.trade_date,
            board_scope=row.board_scope,
            board_scope_label=labels.board_scope_label(row.board_scope),
            status=row.status,
            status_label=labels.snapshot_status_label(row.status),
            computed_at=row.computed_at.replace(tzinfo=UTC),
            counts=SnapshotCountsRead(
                targets=derived["targets"],
                first_boards_since_2019=row.first_board_count,
                candidate_links=derived["candidates"],
            ),
            stage_counts=derived["stage_counts"],
            stage_labels={code: labels.stage_label(code) for code in labels.RESULT_STAGES},
            selection_reason_counts=derived["selection_reason_counts"],
            selection_reason_labels={
                code: labels.selection_reason_label(code) for code in labels.SELECTION_REASONS
            },
            source=SnapshotSourceRead(
                source_sha256=row.source_sha256,
                artifact_sha256=row.artifact_sha256,
                verification_status=row.verification_status,
                verification_status_label=labels.verification_status_label(row.verification_status),
            ),
        )


def _summary(row: FirstBoardRecursiveTarget) -> TargetSummaryRead:
    return TargetSummaryRead(
        stock_code=row.stock_code,
        stock_name=row.stock_name,
        theme=row.theme,
        target_order=row.target_order,
        target_date=row.target_date,
        target_close=_public_decimal(row.target_close),
        limit_rate=_public_decimal(row.limit_rate),
        board_count=row.board_count,
        board_count_text=row.board_count_text,
        result_stage=row.result_stage,
        result_stage_label=labels.stage_label(row.result_stage),
        selection_reason=row.selection_reason,
        selection_reason_label=labels.selection_reason_label(row.selection_reason),
        nearest_prior_date=row.nearest_prior_date,
        nearest_prior_stage=row.nearest_stage,
        nearest_prior_stage_label=labels.stage_label(row.nearest_stage),
        anchor_date=row.anchor_date,
        anchor_distance_sessions=row.anchor_distance_sessions,
        layers_diverge=row.layers_diverge,
        relation_status=row.relation_status,
        relation_status_label=labels.relation_status_label(row.relation_status),
    )


def _target_card(row: FirstBoardRecursiveTarget) -> TargetRead:
    board_text = row.board_count_text or "未知"
    if row.board_count is not None:
        board_text = f"{row.board_count}"
    parts = [f"目标首板 {row.target_date.isoformat()}"]
    if row.target_close is not None:
        parts.append(f"收盘 {labels.decimal_text(_public_decimal(row.target_close))}")
    if row.limit_rate is not None:
        parts.append(f"涨停幅度 {labels.ratio_percent_text(_public_decimal(row.limit_rate))}")
    if row.theme:
        parts.append(f"题材 {row.theme}")
    parts.append(f"板数 {board_text}")
    counts = []
    if row.first_board_since_2019 is not None:
        counts.append(f"2019 年以来首板 {row.first_board_since_2019} 次")
    if row.prior_first_board_count is not None:
        counts.append(f"此前 {row.prior_first_board_count} 次")
    if row.prior_eligible_non_st_count is not None:
        counts.append(f"合格非 ST 前次首板 {row.prior_eligible_non_st_count} 次")
    explanation = "；".join(parts) + "。"
    if counts:
        explanation += "，".join(counts) + "。"
    return TargetRead(
        label="目标首板",
        date=row.target_date,
        close=_public_decimal(row.target_close),
        limit_rate=_public_decimal(row.limit_rate),
        theme=row.theme,
        board_count=row.board_count,
        board_count_text=row.board_count_text,
        first_board_since_2019=row.first_board_since_2019,
        prior_first_board_count=row.prior_first_board_count,
        prior_eligible_non_st_count=row.prior_eligible_non_st_count,
        stage_description=labels.stage_description(row.result_stage),
        explanation=explanation,
    )


def _nearest_prior(row: FirstBoardRecursiveTarget) -> NearestPriorRead | None:
    if row.nearest_prior_date is None:
        return None
    is_anchor = row.anchor_date == row.nearest_prior_date
    return NearestPriorRead(
        date=row.nearest_prior_date,
        distance_sessions=row.nearest_distance_sessions,
        stage=row.nearest_stage,
        stage_label=labels.stage_label(row.nearest_stage),
        label="最近前次首板",
        explanation=labels.nearest_prior_explanation(
            prior_date=row.nearest_prior_date,
            distance_sessions=row.nearest_distance_sessions,
            stage=row.nearest_stage,
            selection_reason=row.selection_reason,
            is_recursive_anchor=is_anchor,
        ),
        is_recursive_anchor=is_anchor,
    )


def _anchor(row: FirstBoardRecursiveTarget) -> RecursiveAnchorRead | None:
    if row.anchor_date is None:
        return None
    return RecursiveAnchorRead(
        date=row.anchor_date,
        distance_sessions=row.anchor_distance_sessions,
        stage=row.result_stage,
        stage_label=labels.stage_label(row.result_stage),
        reference_peak_date=row.anchor_reference_peak_date,
        reference_peak=_public_decimal(row.anchor_reference_peak),
        pullback_low_date=row.anchor_pullback_low_date,
        pullback_low=_public_decimal(row.anchor_pullback_low),
        pullback_pct=_public_decimal(row.anchor_pullback_pct),
        first_close_break_date=row.anchor_first_close_break_date,
        target_close_vs_reference_pct=_public_decimal(row.anchor_target_close_vs_reference_pct),
        selection_reason=row.selection_reason,
        selection_reason_label=labels.selection_reason_label(row.selection_reason),
        label="递归锚点",
        explanation=labels.recursive_anchor_explanation(
            anchor_date=row.anchor_date,
            distance_sessions=row.anchor_distance_sessions,
            stage=row.result_stage,
            reference_peak_date=row.anchor_reference_peak_date,
            reference_peak=_public_decimal(row.anchor_reference_peak),
            pullback_low_date=row.anchor_pullback_low_date,
            pullback_low=_public_decimal(row.anchor_pullback_low),
            pullback_pct=_public_decimal(row.anchor_pullback_pct),
            first_close_break_date=row.anchor_first_close_break_date,
            target_close_vs_reference_pct=_public_decimal(row.anchor_target_close_vs_reference_pct),
            selection_reason=row.selection_reason,
        ),
    )


def _timeline(
    row: FirstBoardRecursiveTarget,
    candidates: list[FirstBoardRecursiveCandidate],
    anchor: RecursiveAnchorRead | None,
) -> list[TimelineNodeRead]:
    nodes: list[TimelineNodeRead] = []
    if row.anchor_date is not None:
        anchor_candidates = [item for item in candidates if item.candidate_date == row.anchor_date]
        if len(anchor_candidates) != 1:
            raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_BAD_DATA")
        for item in candidates:
            if item.candidate_date < row.anchor_date:
                continue
            role = _window_role(row, item)
            nodes.append(
                TimelineNodeRead(
                    order=1,
                    date=item.candidate_date,
                    kind="FIRST_BOARD",
                    role=role,
                    label=labels.timeline_role_label(role),
                    stage=item.stage,
                    stage_label=labels.stage_label(item.stage),
                    is_selected_anchor=item.is_selected_anchor,
                    is_skipped=role == "SKIPPED",
                    is_nearest_prior=item.candidate_date == row.nearest_prior_date,
                    is_before_anchor=False,
                    limit_rate=_public_decimal(item.limit_rate),
                    reference_peak=_public_decimal(item.reference_peak),
                    pullback_low=_public_decimal(item.pullback_low),
                    first_close_break_date=item.first_close_break_date,
                    target_close_vs_reference_pct=_public_decimal(
                        item.target_close_vs_reference_pct
                    ),
                    note=_window_note(role, row, item),
                )
            )
        if row.anchor_first_close_break_date is not None:
            nodes.append(
                TimelineNodeRead(
                    order=1,
                    date=row.anchor_first_close_break_date,
                    kind="FIRST_CLOSE_BREAK",
                    role="FIRST_CLOSE_BREAK",
                    label=labels.timeline_role_label("FIRST_CLOSE_BREAK"),
                    stage=None,
                    stage_label=None,
                    is_selected_anchor=False,
                    is_skipped=False,
                    is_nearest_prior=False,
                    is_before_anchor=False,
                    limit_rate=None,
                    reference_peak=None,
                    pullback_low=None,
                    first_close_break_date=row.anchor_first_close_break_date,
                    target_close_vs_reference_pct=None,
                    note=(
                        "锚点后首次以收盘价越过参考高点"
                        + (
                            f" P={labels.decimal_text(_public_decimal(anchor.reference_peak))}"
                            if anchor is not None and anchor.reference_peak is not None
                            else ""
                        )
                        + "。"
                    ),
                )
            )
    nodes.append(
        TimelineNodeRead(
            order=1,
            date=row.target_date,
            kind="TARGET",
            role="TARGET",
            label=labels.timeline_role_label("TARGET"),
            stage=row.result_stage,
            stage_label=labels.stage_label(row.result_stage),
            is_selected_anchor=False,
            is_skipped=False,
            is_nearest_prior=False,
            is_before_anchor=False,
            limit_rate=_public_decimal(row.limit_rate),
            reference_peak=None,
            pullback_low=None,
            first_close_break_date=row.anchor_first_close_break_date,
            target_close_vs_reference_pct=_public_decimal(row.anchor_target_close_vs_reference_pct),
            note=f"目标日首板；递归结果“{labels.stage_label(row.result_stage)}”。",
        )
    )
    nodes.sort(key=lambda item: (item.date, _KIND_ORDER[item.kind]))
    return [item.model_copy(update={"order": index}) for index, item in enumerate(nodes, start=1)]


def _window_role(row: FirstBoardRecursiveTarget, item: FirstBoardRecursiveCandidate) -> str:
    if item.is_selected_anchor:
        return "ANCHOR"
    if item.candidate_date == row.nearest_prior_date:
        return "NEAREST_PRIOR"
    return "SKIPPED"


def _window_note(
    role: str, row: FirstBoardRecursiveTarget, item: FirstBoardRecursiveCandidate
) -> str:
    if role == "ANCHOR":
        note = "该首板作为递归锚点"
        if item.candidate_date == row.nearest_prior_date:
            note += "，同时也是最近前次首板"
        if row.result_stage == labels.CHAIN_INFORMATION_INSUFFICIENT:
            note += "；但该事件链价格信息不足，结构是否成立无法认证"
        return note + "。"
    if role == "NEAREST_PRIOR":
        # ``_window_role`` only reaches this role for a non-anchor candidate, so a
        # gap here never means "the recursion stopped here": the anchor sits earlier.
        if (
            row.selection_reason == labels.INFORMATION_GAP_STOP
            or item.stage == labels.CHAIN_INFORMATION_INSUFFICIENT
        ):
            return "最近前次首板的价格信息不足，未作为本轮递归锚点；递归继续向更早的首板回溯。"
        return "最近前次首板未形成有效结构，递归继续向更早的首板回溯。"
    return "该首板未形成有效结构，被递归跳过。"


def _earlier_first_boards(
    row: FirstBoardRecursiveTarget, candidates: list[FirstBoardRecursiveCandidate]
) -> list[EarlierFirstBoardRead]:
    if row.anchor_date is None:
        return []
    return [
        EarlierFirstBoardRead(
            date=item.candidate_date,
            rank_oldest=item.rank_oldest,
            rank_nearest=item.rank_nearest,
            stage=item.stage,
            stage_label=labels.stage_label(item.stage),
        )
        for item in candidates
        if item.candidate_date < row.anchor_date
    ]


def _candidate(row: FirstBoardRecursiveCandidate) -> CandidateRead:
    return CandidateRead(
        candidate_date=row.candidate_date,
        rank_oldest=row.rank_oldest,
        rank_nearest=row.rank_nearest,
        stage=row.stage,
        stage_label=labels.stage_label(row.stage),
        limit_rate=_public_decimal(row.limit_rate),
        anchor_session_distance=row.anchor_session_distance,
        reference_peak_date=row.reference_peak_date,
        reference_peak=_public_decimal(row.reference_peak),
        pullback_low_date=row.pullback_low_date,
        pullback_low=_public_decimal(row.pullback_low),
        pullback_pct=_public_decimal(row.pullback_pct),
        first_close_break_date=row.first_close_break_date,
        target_close_vs_reference_pct=_public_decimal(row.target_close_vs_reference_pct),
        is_selected_anchor=row.is_selected_anchor,
        is_legacy_anchor=row.is_legacy_anchor,
        selection_reason=row.selection_reason,
        selection_reason_label=labels.selection_reason_label(row.selection_reason),
        relation_status=row.relation_status,
        relation_status_label=labels.relation_status_label(row.relation_status),
        price_reasons=_split_codes(row.relation_price_reasons),
        price_diagnostic=row.relation_price_diagnostic,
    )


def _audit(row: FirstBoardRecursiveTarget) -> AuditRead:
    return AuditRead(
        code_correction_from=row.code_correction_from,
        code_correction_to=row.code_correction_to,
        legacy_anchor_date=row.legacy_anchor_date,
        legacy_anchor_stage=row.legacy_anchor_stage,
        legacy_anchor_stage_label=labels.stage_label(row.legacy_anchor_stage),
        legacy_selection_reason=row.legacy_selection_reason,
        legacy_selection_reason_label=labels.selection_reason_label(row.legacy_selection_reason),
        relation_status=row.relation_status,
        relation_status_label=labels.relation_status_label(row.relation_status),
        diagnostic_codes=_split_codes(row.diagnostic_codes),
        diagnostic_detail=row.diagnostic_detail,
    )


def _split_codes(value: str | None) -> list[str]:
    if value is None:
        return []
    return [part for part in value.split(";") if part]


def _public_decimal(value: Decimal | None) -> Decimal | None:
    """Drop trailing zeros stored by the fixed-precision column; never invent a value."""
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return Decimal(text or "0")


def import_delivery(
    store: SqlFirstBoardRecursiveStore,
    delivery: RecursiveDelivery,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    state = store.publish(
        delivery.snapshot_row(),
        [dict(item) for item in delivery.target_rows],
        [dict(item) for item in delivery.candidate_rows],
        replace=replace,
    )
    stored = store.snapshot(delivery.trade_date)
    if stored is None:
        raise DomainError("FIRST_BOARD_RECURSIVE_STORAGE_BAD_DATA")
    log_event(
        "first_board_recursive.imported",
        level=logging.INFO,
        state=state,
        snapshot_id=delivery.snapshot_id,
        trade_date=delivery.trade_date.isoformat(),
        targets=delivery.target_count,
        candidates=delivery.candidate_link_count,
    )
    return {
        "status": state,
        "snapshot_id": delivery.snapshot_id,
        "trade_date": delivery.trade_date.isoformat(),
        "board_scope": delivery.board_scope,
        "verification_status": delivery.verification_status,
        "source_sha256": delivery.source_sha256,
        "artifact_sha256": delivery.artifact_sha256,
        "counts": {
            "targets": delivery.target_count,
            "first_boards_since_2019": delivery.first_board_count,
            "candidate_links": delivery.candidate_link_count,
        },
        "stage_counts": delivery.stage_counts,
        "selection_reason_counts": delivery.selection_reason_counts,
        "code_corrections": delivery.code_corrections,
        "computed_at": stored.computed_at.isoformat(),
    }


def stored_status(store: SqlFirstBoardRecursiveStore) -> dict[str, Any]:
    snapshots = []
    for row in store.snapshots():
        derived = store.derived_counts(row.snapshot_id)
        snapshots.append(
            {
                "snapshot_id": row.snapshot_id,
                "trade_date": row.trade_date.isoformat(),
                "board_scope": row.board_scope,
                "status": row.status,
                "verification_status": row.verification_status,
                "computed_at": row.computed_at.isoformat(),
                "source_sha256": row.source_sha256,
                "artifact_sha256": row.artifact_sha256,
                "counts": {
                    "targets": derived["targets"],
                    "first_boards_since_2019": row.first_board_count,
                    "candidate_links": derived["candidates"],
                },
                "stage_counts": derived["stage_counts"],
                "selection_reason_counts": derived["selection_reason_counts"],
            }
        )
    payload: dict[str, Any] = {"snapshots": snapshots}
    if not snapshots:
        payload["message"] = "尚未导入首板递归冻结快照。"
    return payload


def verify_delivery(
    store: SqlFirstBoardRecursiveStore, delivery: RecursiveDelivery
) -> dict[str, Any]:
    """Compare stored rows with the delivery field by field; any mismatch is fatal."""
    stored = store.snapshot(delivery.trade_date)
    if stored is None or stored.snapshot_id != delivery.snapshot_id:
        raise DomainError("FIRST_BOARD_RECURSIVE_SNAPSHOT_NOT_FOUND")
    mismatches: list[dict[str, Any]] = []
    mismatches.extend(_compare_snapshot(stored, delivery))
    mismatches.extend(
        _compare_rows(
            "target",
            {row.stock_code: row for row in store.targets(delivery.snapshot_id)},
            {row["stock_code"]: row for row in delivery.target_rows},
            ("snapshot_id",),
        )
    )
    mismatches.extend(
        _compare_rows(
            "candidate",
            {(row.stock_code, row.candidate_date): row for row in _all_candidates(store, delivery)},
            {(row["stock_code"], row["candidate_date"]): row for row in delivery.candidate_rows},
            ("snapshot_id",),
        )
    )
    derived = store.derived_counts(delivery.snapshot_id)
    if derived["stage_counts"] != delivery.stage_counts:
        mismatches.append(
            {
                "scope": "derived",
                "field": "stage_counts",
                "stored": derived["stage_counts"],
                "source": delivery.stage_counts,
            }
        )
    if derived["selection_reason_counts"] != delivery.selection_reason_counts:
        mismatches.append(
            {
                "scope": "derived",
                "field": "selection_reason_counts",
                "stored": derived["selection_reason_counts"],
                "source": delivery.selection_reason_counts,
            }
        )
    checks = [
        "snapshot_metadata",
        "target_rows",
        "candidate_rows",
        "derived_stage_and_reason_counts",
        "timeline_invariants",
    ]
    mismatches.extend(_compare_timeline(store, delivery))
    if mismatches:
        log_event(
            "first_board_recursive.verify_failed",
            level=logging.WARNING,
            snapshot_id=delivery.snapshot_id,
            mismatch_count=len(mismatches),
        )
        raise DomainError(
            "FIRST_BOARD_RECURSIVE_VERIFY_MISMATCH",
            f"库内数据与冻结产物有 {len(mismatches)} 处不一致。",
        )
    log_event(
        "first_board_recursive.verified",
        level=logging.INFO,
        snapshot_id=delivery.snapshot_id,
        trade_date=delivery.trade_date.isoformat(),
    )
    return {
        "status": "PASS",
        "snapshot_id": delivery.snapshot_id,
        "trade_date": delivery.trade_date.isoformat(),
        "checks": checks,
        "mismatch_count": 0,
        "counts": {
            "targets": delivery.target_count,
            "first_boards_since_2019": delivery.first_board_count,
            "candidate_links": delivery.candidate_link_count,
        },
        "stage_counts": delivery.stage_counts,
        "selection_reason_counts": delivery.selection_reason_counts,
        "source_sha256": delivery.source_sha256,
        "artifact_sha256": delivery.artifact_sha256,
    }


def _all_candidates(store: SqlFirstBoardRecursiveStore, delivery: RecursiveDelivery) -> list:
    rows = []
    for stock_code in delivery.targets_by_stock():
        rows.extend(store.candidates(delivery.snapshot_id, stock_code))
    return rows


def _compare_snapshot(stored, delivery: RecursiveDelivery) -> list[dict[str, Any]]:
    expected = {
        "snapshot_id": delivery.snapshot_id,
        "trade_date": delivery.trade_date,
        "board_scope": delivery.board_scope,
        "status": delivery.status,
        "source_sha256": delivery.source_sha256,
        "artifact_sha256": delivery.artifact_sha256,
        "verification_status": delivery.verification_status,
        "target_count": delivery.target_count,
        "first_board_count": delivery.first_board_count,
        "candidate_link_count": delivery.candidate_link_count,
    }
    mismatches = []
    for field, value in expected.items():
        if getattr(stored, field) != value:
            mismatches.append(
                {
                    "scope": "snapshot",
                    "field": field,
                    "stored": str(getattr(stored, field)),
                    "source": str(value),
                }
            )
    return mismatches


def _compare_rows(
    scope: str,
    stored_rows: dict[Any, Any],
    source_rows: dict[Any, dict[str, Any]],
    ignored: tuple[str, ...],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    for key in sorted(set(stored_rows) - set(source_rows), key=str):
        mismatches.append({"scope": scope, "key": str(key), "field": "stored_only"})
    for key in sorted(set(source_rows) - set(stored_rows), key=str):
        mismatches.append({"scope": scope, "key": str(key), "field": "source_only"})
    for key in sorted(set(stored_rows) & set(source_rows), key=str):
        stored_values = _row_values(stored_rows[key], ignored)
        for field, source_value in source_rows[key].items():
            stored_value = stored_values.get(field)
            if not _values_match(stored_value, source_value):
                mismatches.append(
                    {
                        "scope": scope,
                        "key": str(key),
                        "field": field,
                        "stored": str(stored_value),
                        "source": str(source_value),
                    }
                )
    return mismatches


def _row_values(row: Any, ignored: tuple[str, ...]) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in ignored
    }


def _values_match(stored: Any, source: Any) -> bool:
    """Fixed-precision columns round the source; compare decimals within that error."""
    if stored is None or source is None:
        return stored is None and source is None
    if isinstance(stored, Decimal) and isinstance(source, Decimal):
        return abs(stored - source) <= _DECIMAL_TOLERANCE
    return stored == source


def _compare_timeline(
    store: SqlFirstBoardRecursiveStore, delivery: RecursiveDelivery
) -> list[dict[str, Any]]:
    """Every served timeline must stay inside the recursive window and contain the target."""
    service = FirstBoardRecursiveService(store)
    mismatches: list[dict[str, Any]] = []
    for stock_code in delivery.targets_by_stock():
        detail = service.target_detail(stock_code, delivery.trade_date)
        anchor = detail.summary.anchor_date
        dates = [node.date for node in detail.timeline]
        if not dates or dates[-1] != detail.summary.target_date:
            mismatches.append({"scope": "timeline", "key": stock_code, "field": "target_last"})
        if anchor is None:
            if len(detail.timeline) != 1:
                mismatches.append(
                    {"scope": "timeline", "key": stock_code, "field": "window_without_anchor"}
                )
        else:
            if any(node_date < anchor for node_date in dates):
                mismatches.append(
                    {"scope": "timeline", "key": stock_code, "field": "before_anchor"}
                )
            if anchor not in dates:
                mismatches.append(
                    {"scope": "timeline", "key": stock_code, "field": "missing_anchor"}
                )
            if any(item.date >= anchor for item in detail.earlier_first_boards):
                mismatches.append(
                    {"scope": "timeline", "key": stock_code, "field": "earlier_not_before_anchor"}
                )
    return mismatches
