import csv
import os
from datetime import date
from pathlib import Path

import pytest
from first_board_recursive_fixture import (
    SNAPSHOT_ID,
    TRADE_DATE,
    write_recursive_delivery,
)
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from research_platform.core.database import make_engine
from research_platform.modules.first_board_recursive import dataset_source, labels, service
from research_platform.modules.first_board_recursive.models import (
    FirstBoardRecursiveCandidate,
    FirstBoardRecursiveSnapshot,
    FirstBoardRecursiveTarget,
)
from research_platform.modules.first_board_recursive.store import SqlFirstBoardRecursiveStore

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_URL = "/api/v1/research/first-board-recursive/snapshots/current"
TARGET_URL = "/api/v1/research/first-board-recursive/targets/{symbol}"


def _configured_delivery_root() -> Path | None:
    """The real delivery lives outside this repository; tests skip without it."""
    from_env = os.environ.get("RP_FIRST_BOARD_RECURSIVE__ROOT")
    if from_env:
        return Path(from_env.strip().strip("'"))
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("RP_FIRST_BOARD_RECURSIVE__ROOT="):
            return Path(line.split("=", 1)[1].strip().strip("'"))
    return None


@pytest.fixture(scope="module")
def real_delivery():
    root = _configured_delivery_root()
    if root is None or not (root / "summary.json").is_file():
        pytest.skip("frozen first-board recursive delivery is not configured")
    return dataset_source.load_frozen_delivery(root)


@pytest.fixture
def populated(database_url):
    root = write_recursive_delivery(Path(database_url.removeprefix("sqlite:///")).parent / "frozen")
    delivery = dataset_source.load_frozen_delivery(root)
    engine = make_engine(database_url)
    store = SqlFirstBoardRecursiveStore(sessionmaker(engine, expire_on_commit=False))
    service.import_delivery(store, delivery)
    engine.dispose()
    return delivery


def test_snapshot_endpoint_returns_metadata_counts_and_summaries(client_factory, populated):
    client = client_factory(user_id=1)
    response = client.get(SNAPSHOT_URL)
    assert response.status_code == 200
    payload = response.json()

    assert payload["snapshot_id"] == SNAPSHOT_ID
    assert payload["trade_date"] == TRADE_DATE.isoformat()
    assert payload["board_scope"] == "MAINBOARD_ONLY"
    assert payload["board_scope_label"] == "主板"
    assert payload["status"] == "PASS"
    assert payload["counts"] == {
        "targets": 6,
        "first_boards_since_2019": 18,
        "candidate_links": 11,
    }
    assert payload["stage_counts"] == {
        "ALREADY_REBROKEN_BEFORE_TARGET": 1,
        "CHAIN_INFORMATION_INSUFFICIENT": 2,
        "EPISODE_REATTACK_BELOW_REFERENCE": 1,
        "EPISODE_TARGET_DAY_DIRECT_BREAK": 1,
        "NO_ACTIVE_PRIOR_EPISODE": 1,
    }
    assert payload["selection_reason_counts"] == {
        "INFORMATION_GAP_STOP": 2,
        "NEAREST_ACTIVE_EPISODE": 2,
        "NO_PRIOR_ANCHOR": 1,
        "STRUCTURE_BREAK_STOP": 1,
    }
    assert payload["source"]["verification_status"] == "PASS"
    assert payload["source"]["source_kind"] == "FROZEN_RESEARCH"
    assert payload["source"]["uses_forward_data"] is False
    assert payload["stage_labels"]["EPISODE_FIRST_CLOSE_REBREAK"] == "试盘洗盘后首次收盘突破"
    assert payload["stage_labels"]["EPISODE_TARGET_DAY_DIRECT_BREAK"] == (
        "目标日直接首次收盘突破（前一日尚未回升）"
    )
    assert len(payload["targets"]) == 6
    assert "candidates" not in payload
    assert "timeline" not in payload

    summaries = {item["stock_code"]: item for item in payload["targets"]}
    assert summaries["600001.SH"]["board_count"] is None
    assert summaries["600001.SH"]["board_count_text"] == "8天4板"
    assert summaries["600001.SH"]["layers_diverge"] is True
    assert summaries["600001.SH"]["result_stage_label"] == "目标前已经越过前高"
    assert summaries["600003.SH"]["anchor_date"] is None
    assert summaries["600003.SH"]["selection_reason_label"] == "无更早首板可作锚点"

    dated = client.get(SNAPSHOT_URL, params={"trade_date": TRADE_DATE.isoformat()})
    assert dated.status_code == 200
    other_day = client.get(SNAPSHOT_URL, params={"trade_date": "2026-10-22"})
    assert other_day.status_code == 404
    assert other_day.json()["detail"]["code"] == "FIRST_BOARD_RECURSIVE_SNAPSHOT_NOT_FOUND"


def test_target_endpoint_returns_two_layers_and_recursive_window(client_factory, populated):
    client = client_factory(user_id=1)
    response = client.get(TARGET_URL.format(symbol="600001.SH"))
    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["stock_code"] == "600001.SH"
    assert payload["summary"]["nearest_prior_date"] == "2026-10-15"
    assert payload["target"]["close"] == "15.36"
    assert payload["target"]["board_count_text"] == "8天4板"
    assert payload["target"]["board_count"] is None
    assert "目标首板" in payload["target"]["explanation"]

    timeline = payload["timeline"]
    assert [node["date"] for node in timeline] == [
        "2026-07-29",
        "2026-09-01",
        "2026-09-01",
        "2026-10-15",
        "2026-10-23",
    ]
    assert [node["role"] for node in timeline] == [
        "ANCHOR",
        "SKIPPED",
        "FIRST_CLOSE_BREAK",
        "NEAREST_PRIOR",
        "TARGET",
    ]
    assert [node["order"] for node in timeline] == [1, 2, 3, 4, 5]
    assert all(node["date"] >= payload["summary"]["anchor_date"] for node in timeline)
    expected_dates = {node["date"] for node in timeline}
    assert "2019-01-18" not in expected_dates
    assert timeline[0]["label"] == "递归锚点首板"
    assert timeline[1]["is_skipped"] is True
    assert timeline[3]["is_nearest_prior"] is True

    earlier = payload["earlier_first_boards"]
    assert [item["date"] for item in earlier] == ["2019-01-18", "2024-02-01"]
    assert all(item["date"] < payload["summary"]["anchor_date"] for item in earlier)
    assert all(item["is_before_anchor"] is True and item["is_skipped"] is False for item in earlier)

    anchor = payload["recursive_anchor"]
    assert anchor["date"] == "2026-07-29"
    assert anchor["reference_peak"] == "15.39"
    assert anchor["pullback_low"] == "13.52"
    assert anchor["first_close_break_date"] == "2026-09-01"
    assert anchor["selection_reason_label"] == "向前回溯遇到结构破坏而停止"
    assert "递归锚点" in anchor["explanation"]

    nearest = payload["nearest_prior"]
    assert nearest["date"] == "2026-10-15"
    assert nearest["distance_sessions"] == 6
    assert nearest["is_recursive_anchor"] is False
    assert "递归继续向更早的首板回溯" in nearest["explanation"]

    assert len(payload["candidates"]) == 5
    selected = [item for item in payload["candidates"] if item["is_selected_anchor"]]
    assert [item["candidate_date"] for item in selected] == ["2026-07-29"]
    assert payload["audit"]["code_correction_from"] == "000001.SZ"
    assert payload["audit"]["legacy_anchor_date"] == "2019-01-18"
    assert payload["audit"]["legacy_selection_reason_label"] == "旧规则：最早有效结构（仅审计）"
    assert payload["uses_forward_data"] is False


def test_target_endpoint_handles_no_prior_anchor_and_errors(client_factory, populated):
    client = client_factory(user_id=1)
    response = client.get(TARGET_URL.format(symbol="600003.SH"))
    assert response.status_code == 200
    payload = response.json()
    assert [node["kind"] for node in payload["timeline"]] == ["TARGET"]
    assert payload["summary"]["anchor_date"] is None
    assert payload["recursive_anchor"] is None
    assert payload["nearest_prior"] is None
    assert payload["earlier_first_boards"] == []
    assert payload["candidates"] == []

    unknown = client.get(TARGET_URL.format(symbol="999999.SZ"))
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "FIRST_BOARD_RECURSIVE_TARGET_NOT_FOUND"

    other_day = client.get(
        TARGET_URL.format(symbol="600001.SH"), params={"trade_date": "2026-10-22"}
    )
    assert other_day.status_code == 404
    assert other_day.json()["detail"]["code"] == "FIRST_BOARD_RECURSIVE_SNAPSHOT_NOT_FOUND"

    anonymous = client_factory()
    assert anonymous.get(SNAPSHOT_URL).status_code == 503
    assert anonymous.get(SNAPSHOT_URL).json()["detail"]["code"] == "AUTH_NOT_CONFIGURED"


def test_information_gap_and_direct_break_details_keep_null_facts(client_factory, populated):
    client = client_factory(user_id=1)
    gap = client.get(TARGET_URL.format(symbol="600004.SH")).json()
    assert gap["nearest_prior"]["stage"] == "CHAIN_INFORMATION_INSUFFICIENT"
    assert gap["nearest_prior"]["is_recursive_anchor"] is True
    assert "形成有效结构" not in gap["nearest_prior"]["explanation"]
    assert "价格信息不足" in gap["nearest_prior"]["explanation"]
    assert [node["kind"] for node in gap["timeline"]] == ["FIRST_BOARD", "TARGET"]
    assert gap["timeline"][0]["reference_peak"] is None
    assert gap["timeline"][0]["pullback_low"] is None
    assert gap["timeline"][0]["first_close_break_date"] is None
    for field in (
        "reference_peak",
        "reference_peak_date",
        "pullback_low",
        "pullback_low_date",
        "pullback_pct",
        "first_close_break_date",
        "target_close_vs_reference_pct",
    ):
        assert gap["recursive_anchor"][field] is None
        assert gap["candidates"][0][field] is None
    assert gap["summary"]["result_stage_label"] == "事件链信息不足"
    assert gap["summary"]["selection_reason_label"] == "路径信息缺口导致停止"

    direct = client.get(TARGET_URL.format(symbol="600005.SH")).json()
    assert "涨停幅度 10%" in direct["target"]["explanation"]
    assert "比率" not in direct["target"]["explanation"]
    assert [node["kind"] for node in direct["timeline"]] == [
        "FIRST_BOARD",
        "FIRST_CLOSE_BREAK",
        "TARGET",
    ]
    assert direct["timeline"][1]["date"] == direct["timeline"][2]["date"] == "2026-10-23"
    assert "回调 6.65%" in direct["recursive_anchor"]["explanation"]
    assert "目标收盘相对 P 2.69%" in direct["recursive_anchor"]["explanation"]
    assert direct["recursive_anchor"]["pullback_pct"] == "6.647807637907"
    assert direct["recursive_anchor"]["first_close_break_date"] == "2026-10-23"

    gap_at_anchor = client.get(TARGET_URL.format(symbol="600006.SH")).json()
    assert gap_at_anchor["summary"]["anchor_date"] == "2021-08-02"
    assert gap_at_anchor["summary"]["nearest_prior_date"] == "2026-09-30"
    assert gap_at_anchor["summary"]["layers_diverge"] is True
    assert gap_at_anchor["nearest_prior"]["is_recursive_anchor"] is False
    nearest_explanation = gap_at_anchor["nearest_prior"]["explanation"]
    assert "未作为本轮递归锚点" in nearest_explanation
    assert "继续向更早的首板回溯" in nearest_explanation
    assert "停在最近候选" not in nearest_explanation
    nearest_node = next(
        node for node in gap_at_anchor["timeline"] if node["role"] == "NEAREST_PRIOR"
    )
    assert "未作为本轮递归锚点" in nearest_node["note"]
    assert "停在最近候选" not in nearest_node["note"]
    assert "参考高点未知" in gap_at_anchor["recursive_anchor"]["explanation"]
    assert gap_at_anchor["recursive_anchor"]["reference_peak"] is None
    assert gap_at_anchor["recursive_anchor"]["first_close_break_date"] is None


def test_snapshot_is_shared_across_actors_and_the_api_never_writes(
    client_factory, populated, database_url
):
    first, second = client_factory(user_id=1), client_factory(user_id=2)
    payloads = [client.get(SNAPSHOT_URL).json() for client in (first, second)]
    assert payloads[0] == payloads[1]
    details = [
        client.get(TARGET_URL.format(symbol="600001.SH")).json() for client in (first, second)
    ]
    assert details[0] == details[1]

    engine = make_engine(database_url)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        before = (
            session.scalar(select(func.count()).select_from(FirstBoardRecursiveSnapshot)),
            session.scalar(select(func.count()).select_from(FirstBoardRecursiveTarget)),
            session.scalar(select(func.count()).select_from(FirstBoardRecursiveCandidate)),
            session.scalar(select(FirstBoardRecursiveSnapshot.computed_at)),
        )
    for client in (first, second):
        client.get(SNAPSHOT_URL)
        client.get(TARGET_URL.format(symbol="600001.SH"))
        client.get(TARGET_URL.format(symbol="600002.SH"))
    with sessionmaker(engine, expire_on_commit=False)() as session:
        after = (
            session.scalar(select(func.count()).select_from(FirstBoardRecursiveSnapshot)),
            session.scalar(select(func.count()).select_from(FirstBoardRecursiveTarget)),
            session.scalar(select(func.count()).select_from(FirstBoardRecursiveCandidate)),
            session.scalar(select(FirstBoardRecursiveSnapshot.computed_at)),
        )
    engine.dispose()
    assert before == after == (1, 6, 11, before[3])


def test_real_delivery_matches_the_frozen_benchmarks(client_factory, database_url, real_delivery):
    engine = make_engine(database_url)
    store = SqlFirstBoardRecursiveStore(sessionmaker(engine, expire_on_commit=False))
    service.import_delivery(store, real_delivery)
    engine.dispose()
    client = client_factory(user_id=1)

    snapshot = client.get(SNAPSHOT_URL).json()
    assert snapshot["snapshot_id"] == real_delivery.snapshot_id
    assert snapshot["counts"] == {
        "targets": real_delivery.target_count,
        "first_boards_since_2019": real_delivery.first_board_count,
        "candidate_links": real_delivery.candidate_link_count,
    }
    assert snapshot["counts"] == {
        "targets": 53,
        "first_boards_since_2019": 1608,
        "candidate_links": 1364,
    }
    assert snapshot["stage_counts"] == {
        "ALREADY_REBROKEN_BEFORE_TARGET": 25,
        "CHAIN_INFORMATION_INSUFFICIENT": 4,
        "EPISODE_FIRST_CLOSE_REBREAK": 4,
        "EPISODE_REATTACK_BELOW_REFERENCE": 16,
        "EPISODE_TARGET_DAY_DIRECT_BREAK": 3,
        "NO_ACTIVE_PRIOR_EPISODE": 1,
    }
    assert snapshot["selection_reason_counts"] == {
        "INFORMATION_GAP_STOP": 4,
        "NEAREST_ACTIVE_EPISODE": 18,
        "NO_PRIOR_ANCHOR": 1,
        "RECURSIVE_ACTIVE_EPISODE": 5,
        "STRUCTURE_BREAK_STOP": 25,
    }
    assert snapshot["source"]["source_sha256"] == real_delivery.source_sha256
    assert "candidates" not in snapshot and "timeline" not in snapshot

    hualin = client.get(TARGET_URL.format(symbol="002945.SZ")).json()
    assert [node["date"] for node in hualin["timeline"]] == [
        "2026-07-29",
        "2026-09-01",
        "2026-09-01",
        "2026-10-15",
        "2026-10-23",
    ]
    assert [node["role"] for node in hualin["timeline"]] == [
        "ANCHOR",
        "SKIPPED",
        "FIRST_CLOSE_BREAK",
        "NEAREST_PRIOR",
        "TARGET",
    ]
    assert hualin["summary"]["nearest_prior_date"] == "2026-10-15"
    assert hualin["recursive_anchor"]["date"] == "2026-07-29"
    assert hualin["recursive_anchor"]["reference_peak"] == "15.39"
    assert hualin["recursive_anchor"]["pullback_low"] == "13.52"
    assert hualin["recursive_anchor"]["first_close_break_date"] == "2026-09-01"
    earlier_dates = [item["date"] for item in hualin["earlier_first_boards"]]
    assert len(earlier_dates) == 26
    assert earlier_dates == sorted(earlier_dates)
    assert "2019-06-19" in earlier_dates
    assert "2019-06-19" not in [node["date"] for node in hualin["timeline"]]
    assert len(hualin["candidates"]) == 29
    assert hualin["audit"]["legacy_anchor_date"] == "2019-06-19"

    tianbo = client.get(TARGET_URL.format(symbol="603448.SH")).json()
    assert [node["kind"] for node in tianbo["timeline"]] == ["TARGET"]
    assert tianbo["summary"]["anchor_date"] is None
    assert tianbo["recursive_anchor"] is None
    assert tianbo["nearest_prior"] is None
    assert tianbo["earlier_first_boards"] == []
    assert tianbo["candidates"] == []

    # M1: an information-gap stop must never claim the nearest prior board
    # "formed a valid structure"; the frozen REPORT calls the path insufficient.
    detail = client.get(TARGET_URL.format(symbol="000700.SZ")).json()
    assert detail["summary"]["result_stage"] == "CHAIN_INFORMATION_INSUFFICIENT"
    assert detail["summary"]["selection_reason"] == "INFORMATION_GAP_STOP"
    assert detail["nearest_prior"]["is_recursive_anchor"] is True
    assert "价格信息不足" in detail["nearest_prior"]["explanation"]
    assert "形成有效结构" not in detail["nearest_prior"]["explanation"]
    assert "信息缺口停在最近候选" in detail["nearest_prior"]["explanation"]
    assert detail["recursive_anchor"]["reference_peak"] is None
    assert detail["recursive_anchor"]["pullback_low"] is None
    assert detail["recursive_anchor"]["first_close_break_date"] is None
    assert all(node["first_close_break_date"] is None for node in detail["timeline"])

    for symbol in ("001359.SZ", "002812.SZ", "603838.SH"):
        other = client.get(TARGET_URL.format(symbol=symbol)).json()
        assert other["summary"]["result_stage"] == "CHAIN_INFORMATION_INSUFFICIENT"
        assert "价格信息不足" in other["nearest_prior"]["explanation"]
        assert "形成有效结构" not in other["nearest_prior"]["explanation"]

    # m2: served percentages are trimmed to two decimals, facts keep full precision.
    assert "回调 12.15%" in hualin["recursive_anchor"]["explanation"]
    assert "目标收盘相对 P -0.19%" in hualin["recursive_anchor"]["explanation"]
    assert hualin["recursive_anchor"]["pullback_pct"] == "12.150747238467"
    assert "涨停幅度 10%" in hualin["target"]["explanation"]
    assert "比率" not in hualin["target"]["explanation"]


def test_real_delivery_stage_wordings_match_the_served_labels(real_delivery):
    """m4: labels.py must not invent a second vocabulary for the frozen stages."""
    root = _configured_delivery_root()
    assert root is not None and (root / "target-chain-summary.csv").is_file()
    with (root / "target-chain-summary.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == real_delivery.target_count == 53
    checked = 0
    for row in rows:
        stage = row["selectedStage"]
        assert labels.STAGE_LABELS[stage] == row["selectedStageZh"]
        checked += 1
        nearest_stage = row["nearestStage"]
        if nearest_stage:
            assert labels.STAGE_LABELS[nearest_stage] == row["nearestStageZh"]
    assert checked == 53
    # Stage labels cover the whole result taxonomy, not just the delivered subset.
    assert set(labels.RESULT_STAGES) <= set(labels.STAGE_LABELS)


def test_real_delivery_counts_are_consistent_with_the_declared_total(real_delivery):
    # The detected universe includes the 53 targets themselves and the ineligible priors.
    assert real_delivery.first_board_count == sum(
        row["first_board_since_2019"] for row in real_delivery.target_rows
    )
    assert real_delivery.candidate_link_count == sum(
        len(rows) for rows in real_delivery.candidates_by_stock().values()
    )
    assert real_delivery.target_count == len(real_delivery.target_rows)
    assert sum(1 for row in real_delivery.target_rows if row["anchor_date"] is None) == 1
    assert real_delivery.trade_date == date(2026, 10, 23)
