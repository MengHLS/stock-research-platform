"""Read-only access to one verified, frozen first-board recursive delivery.

The delivery directory is the only data source. It is parsed once, validated
against its own declared counts/hashes and its three cross-checking files, and
then published to the application database by the explicit CLI. A bad delivery
fails loudly: no partial rows, no empty success, no recomputation on this side.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import zlib
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from research_platform.core.errors import DomainError

from . import labels

SUMMARY_FILE = "summary.json"
VERIFICATION_FILE = "verification.json"
TARGET_FILE = "target-chain-summary.csv"
CANDIDATE_FILE = "candidate-links.csv.gz"
DETECTED_FILE = "detected-firstboards.csv.gz"
DELIVERED_FILES = (
    SUMMARY_FILE,
    VERIFICATION_FILE,
    TARGET_FILE,
    CANDIDATE_FILE,
    DETECTED_FILE,
)
BOARD_SCOPE_MAINBOARD = "MAINBOARD_ONLY"
STOCK_CODE_PATTERN = re.compile(r"\d{6}\.(?:SH|SZ|BJ)")
SNAPSHOT_ID_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9-]{7,63}")

TARGET_FIELDS = frozenset(
    {
        "targetEventId",
        "targetOrder",
        "targetDate",
        "stockCode",
        "originalCode",
        "stockName",
        "sector",
        "boardCount",
        "targetClose",
        "codeCorrection",
        "allFirstBoardCountSince2019",
        "priorFirstBoardCount",
        "priorEligibleNonStCount",
        "priorStOrRiskCount",
        "nearestEligiblePrior",
        "selectionReason",
        "selectedAnchorDate",
        "selectedStage",
        "nearestStage",
        "selectedRelationStatus",
        "selectedAnchorDistance",
        "selectedReferencePeakDate",
        "selectedReferencePeak",
        "selectedPullbackLowDate",
        "selectedPullbackLow",
        "selectedPullbackPct",
        "selectedFirstCloseBreakDate",
        "selectedTargetCloseVsReferencePct",
        "candidateStageCounts",
        "legacyEarliestActiveAnchorDate",
        "legacyEarliestActiveStage",
        "legacySelectionReason",
    }
)
CANDIDATE_FIELDS = frozenset(
    {
        "targetDate",
        "stockCode",
        "candidateEventId",
        "candidateRankOldest",
        "candidateRankNearest",
        "candidateDate",
        "candidateLimitRate",
        "isSelectedAnchor",
        "isLegacyEarliestActiveAnchor",
        "selectionReason",
        "legacySelectionReason",
        "relationStatus",
        "relationAnchorSessionDistance",
        "relationReferencePeakDate",
        "relationReferencePeak",
        "relationPullbackLowDate",
        "relationPullbackLow",
        "relationPullbackPct",
        "relationFirstCloseBreakDate",
        "relationTargetCloseVsReferencePct",
        "relationPriceReasons",
        "relationPriceDiagnostic",
        "relationStage",
    }
)
DETECTED_FIELDS = frozenset(
    {
        "eventDate",
        "calendarPosition",
        "limitRate",
        "riskWarning",
        "previousSessionObserved",
        "stockCode",
        "eventId",
        "eventRank",
        "anchorEligible",
        "targetDate",
    }
)


class FrozenDeliveryError(RuntimeError):
    """The delivery is present but inconsistent with its own declarations."""


class FrozenDeliveryUnavailable(FrozenDeliveryError):
    """A required delivery file cannot be read."""


@dataclass(frozen=True, slots=True)
class RecursiveDelivery:
    """One fully validated delivery, already shaped like the database rows."""

    snapshot_id: str
    trade_date: date
    history_start: date
    board_scope: str
    status: str
    verification_status: str
    source_sha256: str
    artifact_sha256: str
    target_count: int
    first_board_count: int
    candidate_link_count: int
    stage_counts: dict[str, int]
    selection_reason_counts: dict[str, int]
    code_corrections: dict[str, str]
    target_rows: tuple[dict[str, Any], ...]
    candidate_rows: tuple[dict[str, Any], ...]

    def targets_by_stock(self) -> dict[str, dict[str, Any]]:
        return {row["stock_code"]: row for row in self.target_rows}

    def candidates_by_stock(self) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.candidate_rows:
            grouped[row["stock_code"]].append(row)
        return dict(grouped)

    def snapshot_row(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "trade_date": self.trade_date,
            "board_scope": self.board_scope,
            "status": self.status,
            "source_sha256": self.source_sha256,
            "artifact_sha256": self.artifact_sha256,
            "verification_status": self.verification_status,
            "target_count": self.target_count,
            "first_board_count": self.first_board_count,
            "candidate_link_count": self.candidate_link_count,
        }


def delivery_or_error(root: Path | None) -> RecursiveDelivery:
    """Map every delivery failure onto a reviewed business code."""
    if root is None:
        raise DomainError("FIRST_BOARD_RECURSIVE_SOURCE_NOT_CONFIGURED")
    try:
        return load_frozen_delivery(root)
    except (
        FileNotFoundError,
        NotADirectoryError,
        PermissionError,
        FrozenDeliveryUnavailable,
    ):
        raise DomainError("FIRST_BOARD_RECURSIVE_DATASET_UNAVAILABLE") from None
    except (
        OSError,
        ValueError,
        InvalidOperation,
        EOFError,
        csv.Error,
        zlib.error,
        FrozenDeliveryError,
    ):
        raise DomainError("FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA") from None


def load_frozen_delivery(root: Path) -> RecursiveDelivery:
    root = Path(root)
    summary = _read_json_object(root / SUMMARY_FILE)
    verification = _read_json_object(root / VERIFICATION_FILE)
    snapshot_id = _meta_text(summary, "taskId")
    if SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id) is None:
        raise FrozenDeliveryError("task identity is not a snapshot id")
    trade_date = _meta_date(summary, "targetDate")
    history_start = _meta_date(summary, "historyStart")
    if history_start > trade_date:
        raise FrozenDeliveryError("history start is later than the delivery date")
    board_scope = _meta_text(summary, "boardScope")
    if board_scope != BOARD_SCOPE_MAINBOARD:
        raise FrozenDeliveryError("delivery board scope is not the supported main-board scope")
    status = _meta_text(summary, "status")
    if status != "PASS":
        raise FrozenDeliveryError("delivery summary status is not PASS")
    for flag in ("outcomeAnalysis", "usingFutureReturn"):
        if _meta_bool(summary, flag) is not False:
            raise FrozenDeliveryError("delivery claims an outcome or future-return analysis")
    if _meta_int(summary, "databaseWrites") != 0:
        raise FrozenDeliveryError("delivery reports database writes")
    if _meta_bool(summary, "doNotPromoteToStrategy") is not True:
        raise FrozenDeliveryError("delivery is not marked as do-not-promote")
    source_sha256 = _meta_text(summary, "sourceManifestSha256")
    _require_sha256(source_sha256, "source manifest")
    sources = summary.get("source")
    if not isinstance(sources, dict) or not sources:
        raise FrozenDeliveryError("summary source hashes are missing")
    for name, value in sources.items():
        _require_sha256(str(value), f"source hash {name}")

    verification_status = _meta_text(verification, "status")
    if verification_status != "PASS":
        raise FrozenDeliveryError("delivery verification is not PASS")
    if _meta_date(verification, "targetDate") != trade_date:
        raise FrozenDeliveryError("verification targets another date")
    for key in ("independentAllFirstBoardMismatches", "selectionMismatches"):
        if _meta_int(verification, key) != 0:
            raise FrozenDeliveryError("delivery verification reports a mismatch")
    if _meta_bool(verification, "futureReturnUsed") is not False:
        raise FrozenDeliveryError("delivery verification claims future returns")
    if _meta_int(verification, "databaseWrites") != 0:
        raise FrozenDeliveryError("delivery verification reports database writes")

    target_count = _meta_int(summary, "targets")
    first_board_count = _meta_int(summary, "detectedFirstBoardsSince2019")
    candidate_link_count = _meta_int(summary, "candidateLinks")
    if min(target_count, first_board_count, candidate_link_count) <= 0:
        raise FrozenDeliveryError("delivery declares a non-positive count")
    if _meta_int(verification, "mainboardTargets") != target_count:
        raise FrozenDeliveryError("verification target count differs from summary")
    if _meta_int(verification, "detectedFirstBoardsSince2019") != first_board_count:
        raise FrozenDeliveryError("verification first-board count differs from summary")
    if _meta_int(verification, "candidateLinks") != candidate_link_count:
        raise FrozenDeliveryError("verification candidate count differs from summary")
    if _meta_int(verification, "independentTargetFirstBoards") != target_count:
        raise FrozenDeliveryError("verification independent target count differs from summary")
    stage_counts = _stage_counts(summary.get("selectedStageCounts"))
    selection_reason_counts = _selection_reason_counts(summary.get("selectionReasonCounts"))
    if _stage_counts(verification.get("selectedStageCounts")) != stage_counts:
        raise FrozenDeliveryError("verification stage counts differ from summary")
    if _selection_reason_counts(verification.get("selectionReasonCounts")) != (
        selection_reason_counts
    ):
        raise FrozenDeliveryError("verification selection reasons differ from summary")
    declared_corrections = _code_corrections(verification.get("codeCorrections"))

    artifact_sha256 = _artifact_digest(root)
    target_raw = _read_rows(root / TARGET_FILE, TARGET_FIELDS)
    candidate_raw = _read_rows(root / CANDIDATE_FILE, CANDIDATE_FIELDS)
    detected_raw = _read_rows(root / DETECTED_FILE, DETECTED_FIELDS)
    if len(target_raw) != target_count:
        raise FrozenDeliveryError("target rows differ from the declared count")
    if len(candidate_raw) != candidate_link_count:
        raise FrozenDeliveryError("candidate rows differ from the declared count")
    if len(detected_raw) != first_board_count:
        raise FrozenDeliveryError("detected rows differ from the declared count")

    targets, corrections, declarations = _parse_targets(target_raw, trade_date)
    if corrections != declared_corrections:
        raise FrozenDeliveryError("target code corrections differ from verification")
    candidates = _parse_candidates(candidate_raw, targets, history_start)
    _check_detected(detected_raw, targets, candidates)
    _link_stocks(targets, candidates, declarations)

    computed_stage_counts = dict(Counter(row["result_stage"] for row in targets.values()))
    computed_reason_counts = dict(Counter(row["selection_reason"] for row in targets.values()))
    if computed_stage_counts != stage_counts:
        raise FrozenDeliveryError("target stages differ from the declared stage counts")
    if computed_reason_counts != selection_reason_counts:
        raise FrozenDeliveryError("selection reasons differ from the declared counts")

    target_rows = tuple(sorted(targets.values(), key=lambda row: row["target_order"]))
    ordered_candidates = tuple(
        sorted(candidates, key=lambda row: (row["stock_code"], row["candidate_date"]))
    )
    return RecursiveDelivery(
        snapshot_id=snapshot_id,
        trade_date=trade_date,
        history_start=history_start,
        board_scope=board_scope,
        status=status,
        verification_status=verification_status,
        source_sha256=source_sha256,
        artifact_sha256=artifact_sha256,
        target_count=target_count,
        first_board_count=first_board_count,
        candidate_link_count=candidate_link_count,
        stage_counts=stage_counts,
        selection_reason_counts=selection_reason_counts,
        code_corrections=corrections,
        target_rows=target_rows,
        candidate_rows=ordered_candidates,
    )


def _parse_targets(
    rows: list[dict[str, str]], trade_date: date
) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    targets: dict[str, dict[str, Any]] = {}
    corrections: dict[str, str] = {}
    declarations: dict[str, dict[str, Any]] = {}
    for row in rows:
        stock_code = _field(row, "stockCode")
        _require_stock_code(stock_code)
        if _field(row, "targetEventId") != f"{stock_code}@{_field(row, 'targetDate')}":
            raise FrozenDeliveryError("target identity disagrees with stock and date")
        row_date = _date_field(row, "targetDate")
        if row_date != trade_date:
            raise FrozenDeliveryError("target date differs from the delivery date")
        if stock_code in targets:
            raise FrozenDeliveryError("duplicate target stock")
        correction = _optional_field(row, "codeCorrection")
        original_code = _field(row, "originalCode")
        _require_stock_code(original_code)
        if correction is None:
            if original_code != stock_code:
                raise FrozenDeliveryError("target code changed without a declared correction")
            code_from = code_to = None
        else:
            match = re.fullmatch(r"(\d{6}\.(?:SH|SZ|BJ))->(\d{6}\.(?:SH|SZ|BJ))", correction)
            if match is None or match.group(2) != stock_code:
                raise FrozenDeliveryError("target code correction is invalid")
            code_from, code_to = match.group(1), match.group(2)
            if code_from != original_code:
                raise FrozenDeliveryError("target code correction disagrees with original code")
            corrections[code_from] = code_to
        stage = _field(row, "selectedStage")
        if stage not in labels.RESULT_STAGES:
            raise FrozenDeliveryError("target result stage is not part of the taxonomy")
        reason = _field(row, "selectionReason")
        if reason not in labels.SELECTION_REASONS:
            raise FrozenDeliveryError("target selection reason is not part of the taxonomy")
        anchor_date = _optional_date(row, "selectedAnchorDate")
        nearest_date = _optional_date(row, "nearestEligiblePrior")
        nearest_stage = _optional_field(row, "nearestStage")
        if (nearest_date is None) != (nearest_stage is None):
            raise FrozenDeliveryError("nearest prior date and stage disagree")
        if nearest_stage is not None and nearest_stage not in labels.CANDIDATE_STAGES:
            raise FrozenDeliveryError("nearest stage is not part of the taxonomy")
        legacy_stage = _optional_field(row, "legacyEarliestActiveStage")
        if legacy_stage is not None and legacy_stage not in labels.CANDIDATE_STAGES:
            raise FrozenDeliveryError("legacy stage is not part of the taxonomy")
        if anchor_date is None and reason != labels.NO_PRIOR_ANCHOR:
            raise FrozenDeliveryError("a target without an anchor must declare no prior anchor")
        if anchor_date is not None and anchor_date > trade_date:
            raise FrozenDeliveryError("recursive anchor is later than the delivery date")
        board_count_text = _optional_field(row, "boardCount")
        targets[stock_code] = {
            "stock_code": stock_code,
            "target_order": _int_field(row, "targetOrder"),
            "stock_name": _field(row, "stockName"),
            "theme": _optional_field(row, "sector"),
            "target_date": row_date,
            "target_close": _optional_decimal(row, "targetClose"),
            "limit_rate": None,
            "board_count": (
                int(board_count_text)
                if board_count_text is not None and board_count_text.isdigit()
                else None
            ),
            "board_count_text": board_count_text,
            "first_board_since_2019": _optional_int(row, "allFirstBoardCountSince2019"),
            "prior_first_board_count": _optional_int(row, "priorFirstBoardCount"),
            "prior_eligible_non_st_count": _optional_int(row, "priorEligibleNonStCount"),
            "nearest_prior_date": nearest_date,
            "nearest_stage": nearest_stage,
            "nearest_distance_sessions": None,
            "anchor_date": anchor_date,
            "anchor_stage": stage if anchor_date is not None else None,
            "anchor_reference_peak_date": _optional_date(row, "selectedReferencePeakDate"),
            "anchor_reference_peak": _optional_decimal(row, "selectedReferencePeak"),
            "anchor_pullback_low_date": _optional_date(row, "selectedPullbackLowDate"),
            "anchor_pullback_low": _optional_decimal(row, "selectedPullbackLow"),
            "anchor_pullback_pct": _optional_decimal(row, "selectedPullbackPct"),
            "anchor_first_close_break_date": _optional_date(row, "selectedFirstCloseBreakDate"),
            "anchor_target_close_vs_reference_pct": _optional_decimal(
                row, "selectedTargetCloseVsReferencePct"
            ),
            "anchor_distance_sessions": _optional_int(row, "selectedAnchorDistance"),
            "selection_reason": reason,
            "result_stage": stage,
            # The two layers diverge only when the recursive anchor sits earlier than
            # the nearest prior first board. ``_link_anchor``/``_link_nearest`` force
            # their stages from the stored candidates, so anchor==nearest implies the
            # same stage; comparing dates is therefore equivalent to comparing stages,
            # and a target without a nearest prior (no prior anchor) stays False.
            "layers_diverge": (
                anchor_date is not None and nearest_date is not None and anchor_date != nearest_date
            ),
            "relation_status": _optional_field(row, "selectedRelationStatus"),
            "diagnostic_codes": None,
            "diagnostic_detail": None,
            "legacy_anchor_date": _optional_date(row, "legacyEarliestActiveAnchorDate"),
            "legacy_anchor_stage": legacy_stage,
            "legacy_selection_reason": _optional_field(row, "legacySelectionReason"),
            "code_correction_from": code_from,
            "code_correction_to": code_to,
        }
        declarations[stock_code] = {
            "candidate_stage_counts": _json_counts(row, "candidateStageCounts"),
            "prior_st_or_risk_count": _optional_int(row, "priorStOrRiskCount"),
        }
    orders = sorted(row["target_order"] for row in targets.values())
    if orders != list(range(1, len(orders) + 1)):
        raise FrozenDeliveryError("target order is not contiguous")
    return targets, corrections, declarations


def _parse_candidates(
    rows: list[dict[str, str]], targets: dict[str, dict[str, Any]], history_start: date
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, date]] = set()
    for row in rows:
        stock_code = _field(row, "stockCode")
        _require_stock_code(stock_code)
        target = targets.get(stock_code)
        if target is None:
            raise FrozenDeliveryError("candidate row belongs to an unknown target")
        candidate_date = _date_field(row, "candidateDate")
        if candidate_date < history_start:
            raise FrozenDeliveryError("candidate first board predates the delivery history start")
        if _field(row, "candidateEventId") != f"{stock_code}@{candidate_date.isoformat()}":
            raise FrozenDeliveryError("candidate identity disagrees with stock and date")
        if _date_field(row, "targetDate") != target["target_date"]:
            raise FrozenDeliveryError("candidate row targets another date")
        if candidate_date > target["target_date"]:
            raise FrozenDeliveryError("candidate first board is later than the target")
        if (stock_code, candidate_date) in seen:
            raise FrozenDeliveryError("duplicate candidate first board")
        seen.add((stock_code, candidate_date))
        stage = _field(row, "relationStage")
        if stage not in labels.CANDIDATE_STAGES:
            raise FrozenDeliveryError("candidate stage is not part of the taxonomy")
        reason = _optional_field(row, "selectionReason")
        if reason is not None and reason not in labels.SELECTION_REASONS:
            raise FrozenDeliveryError("candidate selection reason is not part of the taxonomy")
        candidates.append(
            {
                "stock_code": stock_code,
                "candidate_date": candidate_date,
                "rank_oldest": _int_field(row, "candidateRankOldest"),
                "rank_nearest": _int_field(row, "candidateRankNearest"),
                "stage": stage,
                "limit_rate": _optional_decimal(row, "candidateLimitRate"),
                "anchor_session_distance": _optional_int(row, "relationAnchorSessionDistance"),
                "reference_peak_date": _optional_date(row, "relationReferencePeakDate"),
                "reference_peak": _optional_decimal(row, "relationReferencePeak"),
                "pullback_low_date": _optional_date(row, "relationPullbackLowDate"),
                "pullback_low": _optional_decimal(row, "relationPullbackLow"),
                "pullback_pct": _optional_decimal(row, "relationPullbackPct"),
                "first_close_break_date": _optional_date(row, "relationFirstCloseBreakDate"),
                "target_close_vs_reference_pct": _optional_decimal(
                    row, "relationTargetCloseVsReferencePct"
                ),
                "is_selected_anchor": _bool_field(row, "isSelectedAnchor"),
                "is_legacy_anchor": _bool_field(row, "isLegacyEarliestActiveAnchor"),
                "selection_reason": reason,
                "legacy_selection_reason": _optional_field(row, "legacySelectionReason"),
                "relation_status": _optional_field(row, "relationStatus"),
                "relation_price_reasons": _optional_field(row, "relationPriceReasons"),
                "relation_price_diagnostic": _optional_field(row, "relationPriceDiagnostic"),
            }
        )
    return candidates


def _check_detected(
    rows: list[dict[str, str]],
    targets: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> None:
    """Cross-check the event universe: every eligible prior first board must be a candidate."""
    detected_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for row in rows:
        stock_code = _field(row, "stockCode")
        _require_stock_code(stock_code)
        target = targets.get(stock_code)
        if target is None:
            raise FrozenDeliveryError("detected row belongs to an unknown target")
        event_date = _date_field(row, "eventDate")
        event_id = _field(row, "eventId")
        if event_id != f"{stock_code}@{event_date.isoformat()}":
            raise FrozenDeliveryError("detected identity disagrees with stock and date")
        if event_id in seen:
            raise FrozenDeliveryError("duplicate detected first board")
        seen.add(event_id)
        if _date_field(row, "targetDate") != target["target_date"]:
            raise FrozenDeliveryError("detected row targets another date")
        detected_by_stock[stock_code].append(
            {
                "event_date": event_date,
                "anchor_eligible": _bool_field(row, "anchorEligible"),
                "limit_rate": _optional_decimal(row, "limitRate"),
            }
        )
    candidate_dates: dict[str, set[date]] = defaultdict(set)
    for row in candidates:
        candidate_dates[row["stock_code"]].add(row["candidate_date"])
    for stock_code, target in targets.items():
        stock_rows = detected_by_stock.get(stock_code, [])
        declared = target["first_board_since_2019"]
        if declared is not None and len(stock_rows) != declared:
            raise FrozenDeliveryError("detected row count differs from the target declaration")
        target_events = [row for row in stock_rows if row["event_date"] == target["target_date"]]
        if len(target_events) != 1:
            raise FrozenDeliveryError("target day is missing from the detected first boards")
        target["limit_rate"] = target_events[0]["limit_rate"]
        prior_rows = [row for row in stock_rows if row["event_date"] < target["target_date"]]
        if (
            target["prior_first_board_count"] is not None
            and len(prior_rows) != (target["prior_first_board_count"])
        ):
            raise FrozenDeliveryError("prior first-board count differs from the declaration")
        eligible = {row["event_date"] for row in prior_rows if row["anchor_eligible"]}
        if eligible != candidate_dates.get(stock_code, set()):
            raise FrozenDeliveryError("eligible prior first boards differ from the candidates")


def _link_stocks(
    targets: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
    declarations: dict[str, dict[str, Any]],
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[row["stock_code"]].append(row)
    for stock_code, target in targets.items():
        rows = grouped.get(stock_code, [])
        declared = target["prior_eligible_non_st_count"]
        if declared is not None and len(rows) != declared:
            raise FrozenDeliveryError("candidate count differs from the eligible prior count")
        if rows:
            contiguous = list(range(1, len(rows) + 1))
            if sorted(row["rank_oldest"] for row in rows) != contiguous:
                raise FrozenDeliveryError("candidate oldest ranks are not contiguous")
            if sorted(row["rank_nearest"] for row in rows) != contiguous:
                raise FrozenDeliveryError("candidate nearest ranks are not contiguous")
        declared_stages = declarations[stock_code]["candidate_stage_counts"]
        if dict(Counter(row["stage"] for row in rows)) != declared_stages:
            raise FrozenDeliveryError("candidate stage counts differ from the declaration")
        _link_nearest(target, rows)
        _link_legacy(target, rows)
        _link_anchor(target, rows)


def _link_anchor(target: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    selected = [row for row in rows if row["is_selected_anchor"]]
    if target["anchor_date"] is None:
        if selected:
            raise FrozenDeliveryError("a target without an anchor cannot select one")
        return
    if len(selected) != 1:
        raise FrozenDeliveryError("exactly one candidate must be the selected anchor")
    anchor = selected[0]
    if anchor["candidate_date"] != target["anchor_date"]:
        raise FrozenDeliveryError("selected anchor date differs from the target declaration")
    if anchor["stage"] != target["result_stage"]:
        raise FrozenDeliveryError("selected anchor stage differs from the target result")
    if anchor["selection_reason"] != target["selection_reason"]:
        raise FrozenDeliveryError("selected anchor reason differs from the target declaration")
    for target_key, candidate_key in (
        ("anchor_reference_peak_date", "reference_peak_date"),
        ("anchor_reference_peak", "reference_peak"),
        ("anchor_pullback_low_date", "pullback_low_date"),
        ("anchor_pullback_low", "pullback_low"),
        ("anchor_pullback_pct", "pullback_pct"),
        ("anchor_first_close_break_date", "first_close_break_date"),
        ("anchor_target_close_vs_reference_pct", "target_close_vs_reference_pct"),
        ("anchor_distance_sessions", "anchor_session_distance"),
    ):
        if target[target_key] != anchor[candidate_key]:
            raise FrozenDeliveryError("selected anchor prices differ from the target declaration")
    target["diagnostic_codes"] = anchor["relation_price_reasons"]
    target["diagnostic_detail"] = anchor["relation_price_diagnostic"]


def _link_nearest(target: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    if target["nearest_prior_date"] is None:
        return
    nearest = [row for row in rows if row["candidate_date"] == target["nearest_prior_date"]]
    if len(nearest) != 1 or nearest[0]["stage"] != target["nearest_stage"]:
        raise FrozenDeliveryError("nearest prior first board disagrees with the declaration")
    target["nearest_distance_sessions"] = nearest[0]["anchor_session_distance"]


def _link_legacy(target: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    legacy = [row for row in rows if row["is_legacy_anchor"]]
    if target["legacy_anchor_date"] is None:
        if legacy:
            raise FrozenDeliveryError("legacy anchor flagged without a declared legacy anchor")
        return
    if len(legacy) != 1 or legacy[0]["candidate_date"] != target["legacy_anchor_date"]:
        raise FrozenDeliveryError("legacy anchor disagrees with the declaration")
    if legacy[0]["stage"] != target["legacy_anchor_stage"]:
        raise FrozenDeliveryError("legacy anchor stage disagrees with the declaration")
    if legacy[0]["legacy_selection_reason"] != target["legacy_selection_reason"]:
        raise FrozenDeliveryError("legacy anchor reason disagrees with the declaration")


def _artifact_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for name in DELIVERED_FILES:
        path = root / name
        if not path.is_file():
            raise FrozenDeliveryUnavailable(f"file is missing: {name}")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FrozenDeliveryUnavailable(f"file is missing: {path.name}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise FrozenDeliveryError(f"JSON object required: {path.name}")
    return value


def _read_rows(path: Path, required: frozenset[str]) -> list[dict[str, str]]:
    if not path.is_file():
        raise FrozenDeliveryUnavailable(f"file is missing: {path.name}")
    try:
        if path.suffix == ".gz":
            handle = gzip.open(path, "rt", encoding="utf-8-sig", newline="")
        else:
            handle = path.open("r", encoding="utf-8-sig", newline="")
    except (OSError, gzip.BadGzipFile) as error:
        raise FrozenDeliveryUnavailable(f"file cannot be opened: {path.name}") from error
    with handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise FrozenDeliveryError(f"header is incomplete: {path.name}")
        return list(reader)


def _meta_text(obj: Mapping[str, Any], key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FrozenDeliveryError(f"metadata field is missing: {key}")
    return value.strip()


def _meta_int(obj: Mapping[str, Any], key: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise FrozenDeliveryError(f"metadata field is not an integer: {key}")
    return value


def _meta_bool(obj: Mapping[str, Any], key: str) -> bool:
    value = obj.get(key)
    if not isinstance(value, bool):
        raise FrozenDeliveryError(f"metadata field is not a boolean: {key}")
    return value


def _meta_date(obj: Mapping[str, Any], key: str) -> date:
    return date.fromisoformat(_meta_text(obj, key))


def _field(row: Mapping[str, str], key: str) -> str:
    value = row.get(key)
    if value is None or not value.strip():
        raise FrozenDeliveryError(f"field is empty: {key}")
    return value.strip()


def _optional_field(row: Mapping[str, str], key: str) -> str | None:
    value = row.get(key)
    if value is None or not value.strip():
        return None
    return value.strip()


def _int_field(row: Mapping[str, str], key: str) -> int:
    return int(_field(row, key))


def _optional_int(row: Mapping[str, str], key: str) -> int | None:
    value = _optional_field(row, key)
    return None if value is None else int(value)


def _date_field(row: Mapping[str, str], key: str) -> date:
    return date.fromisoformat(_field(row, key))


def _optional_date(row: Mapping[str, str], key: str) -> date | None:
    value = _optional_field(row, key)
    return None if value is None else date.fromisoformat(value)


def _optional_decimal(row: Mapping[str, str], key: str) -> Decimal | None:
    value = _optional_field(row, key)
    if value is None:
        return None
    number = Decimal(value)
    if not number.is_finite():
        raise FrozenDeliveryError(f"field is not a finite number: {key}")
    return number


def _bool_field(row: Mapping[str, str], key: str) -> bool:
    value = _field(row, key).lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise FrozenDeliveryError(f"field is not a boolean: {key}")


def _json_counts(row: Mapping[str, str], key: str) -> dict[str, int]:
    value = _optional_field(row, key)
    if value is None:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise FrozenDeliveryError(f"field is not a count object: {key}")
    counts: dict[str, int] = {}
    for code, count in parsed.items():
        if (
            code not in labels.CANDIDATE_STAGES
            or isinstance(count, bool)
            or not isinstance(count, int)
        ):
            raise FrozenDeliveryError(f"field contains an invalid stage count: {key}")
        if count < 0:
            raise FrozenDeliveryError(f"field contains a negative stage count: {key}")
        counts[code] = count
    return counts


def _stage_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise FrozenDeliveryError("declared stage counts are missing")
    counts: dict[str, int] = {}
    for code, count in value.items():
        if (
            code not in labels.RESULT_STAGES
            or isinstance(count, bool)
            or not isinstance(count, int)
        ):
            raise FrozenDeliveryError("declared stage counts are invalid")
        counts[code] = count
    return counts


def _selection_reason_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise FrozenDeliveryError("declared selection reason counts are missing")
    counts: dict[str, int] = {}
    for code, count in value.items():
        if (
            code not in labels.SELECTION_REASONS
            or isinstance(count, bool)
            or not isinstance(count, int)
        ):
            raise FrozenDeliveryError("declared selection reason counts are invalid")
        counts[code] = count
    return counts


def _code_corrections(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise FrozenDeliveryError("declared code corrections are invalid")
    corrections: dict[str, str] = {}
    for source, target in value.items():
        _require_stock_code(source)
        _require_stock_code(target)
        if source == target:
            raise FrozenDeliveryError("declared code correction does not change the code")
        corrections[source] = target
    return corrections


def _require_stock_code(value: str) -> None:
    if STOCK_CODE_PATTERN.fullmatch(value) is None:
        raise FrozenDeliveryError("stock code is not a main-board symbol")


def _require_sha256(value: str, label: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in value):
        raise FrozenDeliveryError(f"{label} is not a SHA-256 digest")
