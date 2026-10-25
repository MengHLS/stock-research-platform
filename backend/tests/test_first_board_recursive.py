import csv
import gzip
from datetime import date
from decimal import Decimal

import pytest
from first_board_recursive_fixture import (
    SNAPSHOT_ID,
    TRADE_DATE,
    rewrite_json,
    rewrite_rows,
    write_recursive_delivery,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from research_platform.core.database import make_engine
from research_platform.core.errors import DomainError
from research_platform.modules.first_board_recursive import dataset_source, service
from research_platform.modules.first_board_recursive.models import (
    FirstBoardRecursiveCandidate,
    FirstBoardRecursiveSnapshot,
    FirstBoardRecursiveTarget,
)
from research_platform.modules.first_board_recursive.store import SqlFirstBoardRecursiveStore


@pytest.fixture
def delivery_root(tmp_path):
    return write_recursive_delivery(tmp_path / "delivery")


@pytest.fixture
def store(database_url):
    engine = make_engine(database_url)
    yield SqlFirstBoardRecursiveStore(sessionmaker(engine, expire_on_commit=False))
    engine.dispose()


def load(root):
    return dataset_source.load_frozen_delivery(root)


def test_frozen_delivery_matches_declared_counts_and_rows(delivery_root):
    delivery = load(delivery_root)

    assert delivery.snapshot_id == SNAPSHOT_ID
    assert delivery.trade_date == TRADE_DATE
    assert delivery.board_scope == "MAINBOARD_ONLY"
    assert delivery.status == delivery.verification_status == "PASS"
    assert delivery.target_count == len(delivery.target_rows) == 6
    assert delivery.first_board_count == 18
    assert delivery.candidate_link_count == len(delivery.candidate_rows) == 11
    assert delivery.stage_counts == {
        "ALREADY_REBROKEN_BEFORE_TARGET": 1,
        "CHAIN_INFORMATION_INSUFFICIENT": 2,
        "EPISODE_REATTACK_BELOW_REFERENCE": 1,
        "EPISODE_TARGET_DAY_DIRECT_BREAK": 1,
        "NO_ACTIVE_PRIOR_EPISODE": 1,
    }
    assert delivery.selection_reason_counts == {
        "STRUCTURE_BREAK_STOP": 1,
        "NEAREST_ACTIVE_EPISODE": 2,
        "INFORMATION_GAP_STOP": 2,
        "NO_PRIOR_ANCHOR": 1,
    }
    assert delivery.code_corrections == {"000001.SZ": "600001.SH"}
    assert len(delivery.artifact_sha256) == 64

    recursive = delivery.targets_by_stock()["600001.SH"]
    assert recursive["board_count"] is None
    assert recursive["board_count_text"] == "8天4板"
    assert recursive["limit_rate"] == Decimal("0.1")
    assert recursive["anchor_reference_peak"] == Decimal("15.39")
    assert recursive["nearest_distance_sessions"] == 6
    assert recursive["layers_diverge"] is True
    assert recursive["code_correction_from"] == "000001.SZ"
    assert recursive["code_correction_to"] == "600001.SH"
    assert recursive["anchor_stage"] == "ALREADY_REBROKEN_BEFORE_TARGET"
    assert len(delivery.candidates_by_stock()["600001.SH"]) == 5

    nearest_only = delivery.targets_by_stock()["600002.SH"]
    assert nearest_only["anchor_date"] == nearest_only["nearest_prior_date"]
    assert nearest_only["layers_diverge"] is False

    no_anchor = delivery.targets_by_stock()["600003.SH"]
    assert no_anchor["anchor_date"] is None
    assert no_anchor["anchor_stage"] is None
    assert no_anchor["board_count"] == 1
    assert delivery.candidates_by_stock().get("600003.SH") is None

    information_gap = delivery.targets_by_stock()["600004.SH"]
    assert information_gap["result_stage"] == "CHAIN_INFORMATION_INSUFFICIENT"
    assert information_gap["selection_reason"] == "INFORMATION_GAP_STOP"
    assert information_gap["layers_diverge"] is False
    assert information_gap["anchor_reference_peak_date"] is None
    assert information_gap["anchor_reference_peak"] is None
    assert information_gap["anchor_pullback_low_date"] is None
    assert information_gap["anchor_pullback_low"] is None
    assert information_gap["anchor_pullback_pct"] is None
    assert information_gap["anchor_first_close_break_date"] is None
    assert information_gap["anchor_target_close_vs_reference_pct"] is None
    assert len(delivery.candidates_by_stock()["600004.SH"]) == 1

    direct_break = delivery.targets_by_stock()["600005.SH"]
    assert direct_break["result_stage"] == "EPISODE_TARGET_DAY_DIRECT_BREAK"
    assert direct_break["anchor_first_close_break_date"] == direct_break["target_date"]
    assert direct_break["anchor_reference_peak"] == Decimal("42.42")
    assert direct_break["anchor_pullback_low"] == Decimal("39.6")

    gap_at_anchor = delivery.targets_by_stock()["600006.SH"]
    assert gap_at_anchor["selection_reason"] == "INFORMATION_GAP_STOP"
    assert gap_at_anchor["anchor_date"] < gap_at_anchor["nearest_prior_date"]
    assert gap_at_anchor["layers_diverge"] is True
    assert gap_at_anchor["anchor_stage"] == "CHAIN_INFORMATION_INSUFFICIENT"
    assert gap_at_anchor["nearest_stage"] == "CHAIN_INFORMATION_INSUFFICIENT"
    assert gap_at_anchor["anchor_reference_peak"] is None
    assert gap_at_anchor["anchor_first_close_break_date"] is None
    assert gap_at_anchor["anchor_distance_sessions"] == 1260
    assert gap_at_anchor["nearest_distance_sessions"] == 8
    assert len(delivery.candidates_by_stock()["600006.SH"]) == 2


def test_delivery_rejects_declared_count_stage_and_verification_mismatches(tmp_path, delivery_root):
    rewrite_json(delivery_root, "summary.json", lambda data: data.update(targets=4))
    with pytest.raises(DomainError) as count:
        dataset_source.delivery_or_error(delivery_root)
    assert count.value.code == "FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA"

    verification_root = write_recursive_delivery(tmp_path / "verification")
    rewrite_json(verification_root, "verification.json", lambda data: data.update(status="FAIL"))
    with pytest.raises(DomainError) as verification:
        dataset_source.delivery_or_error(verification_root)
    assert verification.value.code == "FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA"

    stage_root = write_recursive_delivery(tmp_path / "stage")
    rewrite_rows(
        stage_root,
        "target-chain-summary.csv",
        lambda rows: rows[0].update(selectedStage="EPISODE_TARGET_DAY_DIRECT_BREAK"),
    )
    with pytest.raises(DomainError) as stage:
        dataset_source.delivery_or_error(stage_root)
    assert stage.value.code == "FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA"

    reason_root = write_recursive_delivery(tmp_path / "reason")
    rewrite_json(
        reason_root,
        "summary.json",
        lambda data: data["selectionReasonCounts"].update(NO_PRIOR_ANCHOR=2),
    )
    with pytest.raises(DomainError) as reason:
        dataset_source.delivery_or_error(reason_root)
    assert reason.value.code == "FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA"


def test_delivery_rejects_missing_file_and_inconsistent_rows(tmp_path, delivery_root):
    (delivery_root / "candidate-links.csv.gz").unlink()
    with pytest.raises(DomainError) as missing:
        dataset_source.delivery_or_error(delivery_root)
    assert missing.value.code == "FIRST_BOARD_RECURSIVE_DATASET_UNAVAILABLE"

    corrupt_root = write_recursive_delivery(tmp_path / "corrupt")
    (corrupt_root / "detected-firstboards.csv.gz").write_bytes(b"not-gzip")
    with pytest.raises(DomainError) as corrupt:
        dataset_source.delivery_or_error(corrupt_root)
    assert corrupt.value.code == "FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA"

    identity_root = write_recursive_delivery(tmp_path / "identity")
    rewrite_rows(
        identity_root,
        "candidate-links.csv.gz",
        lambda rows: rows[0].update(candidateEventId="600001.SH@2019-01-19"),
    )
    with pytest.raises(DomainError) as identity:
        dataset_source.delivery_or_error(identity_root)
    assert identity.value.code == "FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA"

    eligible_root = write_recursive_delivery(tmp_path / "eligible")
    rewrite_rows(
        eligible_root,
        "detected-firstboards.csv.gz",
        lambda rows: rows[0].update(anchorEligible="False"),
    )
    with pytest.raises(DomainError) as eligible:
        dataset_source.delivery_or_error(eligible_root)
    assert eligible.value.code == "FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA"

    history_root = write_recursive_delivery(tmp_path / "history")
    rewrite_rows(
        history_root,
        "candidate-links.csv.gz",
        lambda rows: rows[0].update(candidateDate="2018-12-28"),
    )
    with pytest.raises(DomainError) as history:
        dataset_source.delivery_or_error(history_root)
    assert history.value.code == "FIRST_BOARD_RECURSIVE_DATASET_BAD_DATA"


def test_delivery_without_configuration_reports_not_configured():
    with pytest.raises(DomainError) as unconfigured:
        dataset_source.delivery_or_error(None)
    assert unconfigured.value.code == "FIRST_BOARD_RECURSIVE_SOURCE_NOT_CONFIGURED"


def test_import_is_idempotent_and_verify_compares_both_layers(database_url, store, delivery_root):
    delivery = load(delivery_root)

    inserted = service.import_delivery(store, delivery)
    assert inserted["status"] == "INSERTED"
    stored = store.snapshot(TRADE_DATE)
    computed_at = stored.computed_at

    unchanged = service.import_delivery(store, delivery)
    assert unchanged["status"] == "UNCHANGED"
    assert store.snapshot(TRADE_DATE).computed_at == computed_at

    status = service.stored_status(store)
    assert [item["snapshot_id"] for item in status["snapshots"]] == [SNAPSHOT_ID]
    assert status["snapshots"][0]["counts"] == {
        "targets": 6,
        "first_boards_since_2019": 18,
        "candidate_links": 11,
    }
    assert "message" not in status

    verified = service.verify_delivery(store, delivery)
    assert verified["status"] == "PASS"
    assert verified["mismatch_count"] == 0


def test_import_conflict_requires_replace_and_then_verifies_again(database_url, tmp_path, store):
    first = load(write_recursive_delivery(tmp_path / "first"))
    changed = load(write_recursive_delivery(tmp_path / "changed", anchor_peak="15.40"))
    assert first.artifact_sha256 != changed.artifact_sha256
    assert first.snapshot_id == changed.snapshot_id

    service.import_delivery(store, first)
    with pytest.raises(DomainError) as conflict:
        service.import_delivery(store, changed)
    assert conflict.value.code == "FIRST_BOARD_RECURSIVE_SNAPSHOT_CONFLICT"
    assert store.snapshot(TRADE_DATE).artifact_sha256 == first.artifact_sha256

    replaced = service.import_delivery(store, changed, replace=True)
    assert replaced["status"] == "REPLACED"
    assert store.snapshot(TRADE_DATE).artifact_sha256 == changed.artifact_sha256
    stored_target = store.target(SNAPSHOT_ID, "600001.SH")
    assert stored_target is not None
    assert stored_target.anchor_reference_peak == Decimal("15.40")
    engine = make_engine(database_url)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        assert session.scalar(select(func.count()).select_from(FirstBoardRecursiveSnapshot)) == 1
        assert session.scalar(select(func.count()).select_from(FirstBoardRecursiveTarget)) == 6
        assert session.scalar(select(func.count()).select_from(FirstBoardRecursiveCandidate)) == 11
    engine.dispose()

    assert service.verify_delivery(store, changed)["status"] == "PASS"
    with pytest.raises(DomainError) as stale:
        service.verify_delivery(store, first)
    assert stale.value.code == "FIRST_BOARD_RECURSIVE_VERIFY_MISMATCH"


def test_verify_detects_a_tampered_stored_row(database_url, store, delivery_root):
    delivery = load(delivery_root)
    service.import_delivery(store, delivery)
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE research_first_board_recursive_target SET target_close = '99.0' "
                "WHERE stock_code = '600001.SH'"
            )
        )
    engine.dispose()

    with pytest.raises(DomainError) as tampered:
        service.verify_delivery(store, delivery)
    assert tampered.value.code == "FIRST_BOARD_RECURSIVE_VERIFY_MISMATCH"


def test_publication_rolls_back_when_stored_counts_disagree(store, delivery_root):
    delivery = load(delivery_root)
    snapshot = delivery.snapshot_row()
    snapshot["target_count"] = 99
    with pytest.raises(DomainError) as mismatch:
        store.publish(
            snapshot,
            [dict(row) for row in delivery.target_rows],
            [dict(row) for row in delivery.candidate_rows],
        )
    assert mismatch.value.code == "FIRST_BOARD_RECURSIVE_STORAGE_BAD_DATA"
    assert store.snapshot(TRADE_DATE) is None


def test_timeline_window_and_folded_history_are_separated(store, delivery_root):
    delivery = load(delivery_root)
    service.import_delivery(store, delivery)
    reader = service.FirstBoardRecursiveService(store)

    detail = reader.target_detail("600001.SH")
    anchor = detail.summary.anchor_date
    assert anchor == date(2026, 7, 29)
    assert [node.date for node in detail.timeline] == [
        date(2026, 7, 29),
        date(2026, 9, 1),
        date(2026, 9, 1),
        date(2026, 10, 15),
        date(2026, 10, 23),
    ]
    assert [node.kind for node in detail.timeline] == [
        "FIRST_BOARD",
        "FIRST_BOARD",
        "FIRST_CLOSE_BREAK",
        "FIRST_BOARD",
        "TARGET",
    ]
    assert [node.role for node in detail.timeline] == [
        "ANCHOR",
        "SKIPPED",
        "FIRST_CLOSE_BREAK",
        "NEAREST_PRIOR",
        "TARGET",
    ]
    assert all(node.date >= anchor for node in detail.timeline)
    assert date(2019, 1, 18) not in [node.date for node in detail.timeline]
    assert all(item.date < anchor for item in detail.earlier_first_boards)
    assert [item.date for item in detail.earlier_first_boards] == [
        date(2019, 1, 18),
        date(2024, 2, 1),
    ]
    assert all(
        item.is_before_anchor and not item.is_skipped for item in detail.earlier_first_boards
    )
    assert detail.recursive_anchor.reference_peak == Decimal("15.39")
    assert detail.recursive_anchor.pullback_low == Decimal("13.52")
    assert detail.recursive_anchor.first_close_break_date == date(2026, 9, 1)
    assert detail.nearest_prior.date == date(2026, 10, 15)
    assert detail.nearest_prior.distance_sessions == 6
    assert "回溯" in detail.nearest_prior.explanation
    assert detail.audit.code_correction_from == "000001.SZ"
    assert detail.audit.legacy_anchor_date == date(2019, 1, 18)
    assert len(detail.candidates) == 5
    assert sum(item.is_selected_anchor for item in detail.candidates) == 1

    no_anchor = reader.target_detail("600003.SH")
    assert [node.kind for node in no_anchor.timeline] == ["TARGET"]
    assert no_anchor.recursive_anchor is None
    assert no_anchor.nearest_prior is None
    assert no_anchor.earlier_first_boards == []
    assert no_anchor.candidates == []


def test_reader_reports_missing_snapshot_and_unknown_target(store, delivery_root):
    reader = service.FirstBoardRecursiveService(store)
    with pytest.raises(DomainError) as missing:
        reader.snapshot(TRADE_DATE)
    assert missing.value.code == "FIRST_BOARD_RECURSIVE_SNAPSHOT_NOT_FOUND"

    service.import_delivery(store, load(delivery_root))
    with pytest.raises(DomainError) as unknown:
        reader.target_detail("999999.SZ")
    assert unknown.value.code == "FIRST_BOARD_RECURSIVE_TARGET_NOT_FOUND"
    with pytest.raises(DomainError) as other_date:
        reader.snapshot(date(2026, 10, 22))
    assert other_date.value.code == "FIRST_BOARD_RECURSIVE_SNAPSHOT_NOT_FOUND"


def test_csv_helpers_stay_gzip_and_plain(delivery_root):
    with gzip.open(delivery_root / "candidate-links.csv.gz", "rt", encoding="utf-8") as handle:
        candidates = list(csv.DictReader(handle))
    assert len(candidates) == 11
    with (delivery_root / "target-chain-summary.csv").open(encoding="utf-8") as handle:
        targets = list(csv.DictReader(handle))
    assert targets[0]["stockCode"] == "600001.SH"


def test_information_gap_and_direct_break_explanations_stay_accurate(store, delivery_root):
    service.import_delivery(store, load(delivery_root))
    reader = service.FirstBoardRecursiveService(store)

    gap = reader.target_detail("600004.SH")
    explanation = gap.nearest_prior.explanation
    assert "价格信息不足" in explanation
    assert "形成有效结构" not in explanation
    assert "信息缺口停在最近候选" in explanation
    assert gap.nearest_prior.is_recursive_anchor is True
    assert gap.nearest_prior.stage == "CHAIN_INFORMATION_INSUFFICIENT"
    assert gap.recursive_anchor.reference_peak is None
    assert gap.recursive_anchor.reference_peak_date is None
    assert gap.recursive_anchor.pullback_low is None
    assert gap.recursive_anchor.pullback_low_date is None
    assert gap.recursive_anchor.pullback_pct is None
    assert gap.recursive_anchor.first_close_break_date is None
    assert gap.recursive_anchor.target_close_vs_reference_pct is None
    assert [node.kind for node in gap.timeline] == ["FIRST_BOARD", "TARGET"]
    assert [node.date for node in gap.timeline] == [date(2020, 3, 5), TRADE_DATE]
    assert gap.timeline[0].reference_peak is None
    assert gap.timeline[0].pullback_low is None
    assert gap.timeline[0].first_close_break_date is None
    assert "价格信息不足" in gap.timeline[0].note
    assert "事件链信息不足" in gap.timeline[1].note
    assert gap.candidates[0].reference_peak is None
    assert gap.candidates[0].pullback_low is None
    assert gap.candidates[0].first_close_break_date is None

    direct = reader.target_detail("600005.SH")
    assert "涨停幅度 10%" in direct.target.explanation
    assert "比率" not in direct.target.explanation
    assert "回调 6.65%" in direct.recursive_anchor.explanation
    assert "目标收盘相对 P 2.69%" in direct.recursive_anchor.explanation
    assert [node.kind for node in direct.timeline] == [
        "FIRST_BOARD",
        "FIRST_CLOSE_BREAK",
        "TARGET",
    ]
    assert direct.timeline[1].date == direct.timeline[2].date == TRADE_DATE
    assert direct.recursive_anchor.first_close_break_date == TRADE_DATE
    assert direct.recursive_anchor.pullback_pct == Decimal("6.647807637907")

    recursive = reader.target_detail("600001.SH")
    assert "回调 12.15%" in recursive.recursive_anchor.explanation
    assert "目标收盘相对 P -0.19%" in recursive.recursive_anchor.explanation
    assert recursive.recursive_anchor.pullback_pct == Decimal("12.150747238467")
    assert recursive.recursive_anchor.target_close_vs_reference_pct == Decimal("-0.194931773879")


def test_information_gap_on_an_earlier_anchor_does_not_stop_at_the_nearest_board(
    store, delivery_root
):
    """The recursion may stop at a gap found earlier than the nearest prior board."""
    service.import_delivery(store, load(delivery_root))
    reader = service.FirstBoardRecursiveService(store)

    detail = reader.target_detail("600006.SH")
    assert detail.summary.result_stage == "CHAIN_INFORMATION_INSUFFICIENT"
    assert detail.summary.selection_reason == "INFORMATION_GAP_STOP"
    assert detail.summary.anchor_date == date(2021, 8, 2)
    assert detail.summary.nearest_prior_date == date(2026, 9, 30)
    assert detail.summary.layers_diverge is True
    assert detail.nearest_prior.is_recursive_anchor is False

    explanation = detail.nearest_prior.explanation
    assert "未作为本轮递归锚点" in explanation
    assert "继续向更早的首板回溯" in explanation
    assert "停在最近候选" not in explanation

    nearest_node = next(node for node in detail.timeline if node.role == "NEAREST_PRIOR")
    assert "未作为本轮递归锚点" in nearest_node.note
    assert "停在最近候选" not in nearest_node.note
    assert any(node.role == "ANCHOR" for node in detail.timeline)

    # The anchor card still renders the information gap with unknown prices.
    assert "事件链信息不足" in detail.recursive_anchor.explanation
    assert "参考高点未知" in detail.recursive_anchor.explanation
    assert "回调低点未知" in detail.recursive_anchor.explanation
    assert detail.recursive_anchor.reference_peak is None
    assert detail.recursive_anchor.pullback_low is None
    assert detail.recursive_anchor.first_close_break_date is None
