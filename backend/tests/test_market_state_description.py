from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from research_platform.core.config import MarketStateConfig, Settings
from research_platform.core.errors import DomainError
from research_platform.main import create_app
from research_platform.modules.identity.dependencies import Actor, require_actor
from research_platform.modules.market.state_description import (
    MarketStateDescriptionService,
    describe_row,
    scan_table,
)
from research_platform.modules.market.state_source import FrozenMarketStateSource


def market_row(
    day: str,
    *,
    close: float = 100,
    breadth20: float = 60,
    breadth60: float = 55,
    ma20: float = 99,
    ma60: float = 98,
    eligible20: int = 100,
    eligible60: int = 100,
) -> dict:
    return {
        "tradeDate": day,
        "universeId": "CN_A_SH_SZ_VERIFIED_V1",
        "featureVersion": "market-state-v1.0.0",
        "csi300Close": close,
        "csi300Return1dPct": 0.1,
        "csi300Ma20": ma20,
        "csi300Ma60": ma60,
        "csi300Volatility20Pct": 20.0,
        "csi300Return20dPct": 3.0 if close > ma20 else -6.0,
        "csi300Drawdown60Pct": -8.0,
        "barCount": 100,
        "returnObservedCount": 100,
        "advancers": 40,
        "decliners": 58,
        "unchanged": 2,
        "medianReturnPct": -0.3,
        "aboveMa20RatioPct": breadth20,
        "ma20EligibleCount": eligible20,
        "aboveMa60RatioPct": breadth60,
        "ma60EligibleCount": eligible60,
        "amountRatio20": 0.8,
        "amountRolling120Midrank": 0.2,
        "amountCoverageCount": 100,
        "limitRuleKnownBarCount": 100,
        "limitUpCloseCount": 30,
        "limitDownCloseCount": 5,
        "brokenBoardRatePct": 30.0,
        "yesterdayLimitUpFeedbackAvgReturnPct": 0.5,
        "yesterdayLimitUpFeedbackWinRatePct": 55.0,
        "coverageStatus": "VERIFIED_UNIVERSE",
    }


def market_rows(count: int = 65) -> list[dict]:
    first = date(2026, 7, 17)
    rows = []
    for index in range(count):
        day = (first + timedelta(days=index)).isoformat()
        rows.append(
            market_row(
                day,
                close=100 if index == count - 6 else (95 if index == count - 1 else 97),
                breadth20=60 if index == count - 6 else (40 if index == count - 1 else 45),
                breadth60=55 if index == count - 6 else (45 if index == count - 1 else 48),
                ma20=97 if index == count - 1 else 99,
                ma60=98,
            )
        )
    return rows


def write_delivery(root: Path, rows: list[dict], *, tamper: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "universeId": "CN_A_SH_SZ_VERIFIED_V1",
        "featureVersion": "market-state-v1.0.0",
        "rowCount": len(rows),
        "rows": rows,
    }
    table_path = root / "market-state-daily.json"
    table_path.write_text(json.dumps(payload), encoding="utf-8")
    digest = hashlib.sha256(table_path.read_bytes()).hexdigest()
    (root / "verification.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "outputFiles": {"market-state-daily.json": digest},
            }
        ),
        encoding="utf-8",
    )
    (root / "run-meta.json").write_text(
        json.dumps(
            {
                "buildVersion": "market-state-build-v1",
                "certificationLevel": "EXPLORATORY",
            }
        ),
        encoding="utf-8",
    )
    if tamper:
        table_path.write_text(table_path.read_text(encoding="utf-8") + " ", encoding="utf-8")


def test_source_rejects_a_changed_delivery(tmp_path):
    write_delivery(tmp_path, market_rows(), tamper=True)
    service = MarketStateDescriptionService(
        FrozenMarketStateSource(tmp_path),
        MarketStateConfig(root=tmp_path),
    )
    with pytest.raises(DomainError) as failure:
        service.describe(date(2026, 9, 19))
    assert failure.value.code == "MARKET_STATE_SOURCE_BAD_DATA"


def test_source_reports_a_missing_delivery_as_unavailable(tmp_path):
    service = MarketStateDescriptionService(
        FrozenMarketStateSource(tmp_path / "missing"),
        MarketStateConfig(root=tmp_path / "missing"),
    )
    with pytest.raises(DomainError) as failure:
        service.describe(date(2026, 9, 19))
    assert failure.value.code == "MARKET_STATE_SOURCE_UNAVAILABLE"


def test_description_marks_short_and_slow_layers_without_a_score(tmp_path):
    rows = market_rows()
    write_delivery(tmp_path, rows)
    table = FrozenMarketStateSource(tmp_path).load()

    result = describe_row(table, rows[-1]["tradeDate"])

    assert [layer.classification for layer in result.layers] == [
        "weakening",
        "weak",
        "weak",
    ]
    assert result.layers[0].base_date == date.fromisoformat(rows[-6]["tradeDate"])
    assert result.layers[0].metrics[0].value == pytest.approx(-5)
    assert result.layers[0].metrics[1].value == pytest.approx(-20)
    assert {item.code for item in result.conflicts} == {
        "index_up_breadth_down",
        "limit_feedback_positive_breadth_weak",
    }
    assert "5日变化恶化，20日趋势偏弱，60日结构偏弱" in result.summary
    assert result.certification_level == "EXPLORATORY"


def test_quality_gate_prevents_a_classification(tmp_path):
    rows = market_rows()
    rows[-1]["ma20EligibleCount"] = 94
    rows[-1]["ma60EligibleCount"] = 94
    write_delivery(tmp_path, rows)
    table = FrozenMarketStateSource(tmp_path).load()

    result = describe_row(table, rows[-1]["tradeDate"])

    assert [layer.status for layer in result.layers] == [
        "unavailable",
        "unavailable",
        "unavailable",
    ]
    assert "不可评估" in result.summary
    assert {item.code for item in result.issues} >= {
        "breadth_gate_failed_5d",
        "breadth_gate_failed_20d",
        "breadth_gate_failed_60d",
    }


def test_scan_reports_distribution_runs_and_transitions(tmp_path):
    rows = market_rows()
    write_delivery(tmp_path, rows)
    table = FrozenMarketStateSource(tmp_path).load()

    result = scan_table(table, date(2026, 7, 1), date(2026, 10, 31))

    assert result["row_count"] == 65
    assert result["description_version"] == "market-description-v1"
    assert result["layers"]["short_5d"]["runs"] >= 1
    assert result["layers"]["short_5d"]["counts"]["weakening"] >= 1
    assert result["layers"]["structure_60d"]["unavailable_by_year"] == {}
    assert result["conflicts"]["index_up_breadth_down"] >= 1
    assert result["issues"]["exploratory_certification"] == 65


def test_limit_counts_preserve_zero_and_bound_the_requested_dates(tmp_path):
    rows = market_rows()
    rows[-1]["limitUpCloseCount"] = 0
    rows[-1]["limitDownCloseCount"] = 0
    rows[-1]["brokenBoardCount"] = 30
    write_delivery(tmp_path, rows)
    service = MarketStateDescriptionService(
        FrozenMarketStateSource(tmp_path),
        MarketStateConfig(root=tmp_path),
    )

    result = service.limit_counts(
        date.fromisoformat(rows[-2]["tradeDate"]),
        date.fromisoformat(rows[-1]["tradeDate"]),
    )

    assert len(result) == 2
    latest = result[date.fromisoformat(rows[-1]["tradeDate"])]
    assert latest.limit_up_close_count == 0
    assert latest.limit_down_close_count == 0
    assert latest.broken_board_count == 30
    assert latest.limit_down_close_count is not None


def test_limit_counts_reject_fractional_negative_and_boolean_values(tmp_path):
    rows = market_rows()
    rows[-1]["limitUpCloseCount"] = -1
    rows[-1]["limitDownCloseCount"] = "2.5"
    rows[-1]["brokenBoardCount"] = True
    write_delivery(tmp_path, rows)
    service = MarketStateDescriptionService(
        FrozenMarketStateSource(tmp_path),
        MarketStateConfig(root=tmp_path),
    )

    latest = service.limit_counts(
        date.fromisoformat(rows[-1]["tradeDate"]),
        date.fromisoformat(rows[-1]["tradeDate"]),
    )[date.fromisoformat(rows[-1]["tradeDate"])]

    assert latest.limit_up_close_count is None
    assert latest.limit_down_close_count is None
    assert latest.broken_board_count is None


def _client(tmp_path, *, configured: bool = True, user_id: int = 1):
    write_delivery(tmp_path, market_rows())
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'app.db').as_posix()}",
        _env_file=None,
        market_state={"root": tmp_path} if configured else None,
    )
    app = create_app(settings)
    app.dependency_overrides[require_actor] = lambda: Actor(user_id=user_id)
    return TestClient(app)


def test_state_description_api_is_shared_and_exposes_versioned_evidence(tmp_path):
    with _client(tmp_path, user_id=1) as first:
        response = first.get(
            "/api/v1/market/state/description",
            params={"date": "2026-09-19"},
        )
    with _client(tmp_path, user_id=2) as second:
        other = second.get(
            "/api/v1/market/state/description",
            params={"date": "2026-09-19"},
        )
    assert response.status_code == 200
    assert other.status_code == 200
    assert response.json() == other.json()
    body = response.json()
    assert body["description_version"] == "market-description-v1"
    assert body["feature_version"] == "market-state-v1.0.0"
    assert body["build_version"] == "market-state-build-v1"
    assert body["usage"] == "descriptive_not_predictive"
    assert body["source_sha256"] == response.json()["source_sha256"]
    assert body["layers"][0]["metrics"][0]["value"] == "-5.00"
    assert body["facts"]["median_return_pct"] == "-0.3"


def test_state_description_api_requires_configured_identity(tmp_path):
    write_delivery(tmp_path, market_rows())
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'unauthenticated.db').as_posix()}",
        _env_file=None,
        market_state={"root": tmp_path},
    )
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/v1/market/state/description",
            params={"date": "2026-09-19"},
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AUTH_NOT_CONFIGURED"


def test_state_description_api_rejects_unknown_query_date_and_unconfigured_source(tmp_path):
    with _client(tmp_path) as client:
        typo = client.get(
            "/api/v1/market/state/description",
            params={"date": "2026-09-19", "window": 5},
        )
        missing = client.get(
            "/api/v1/market/state/description",
            params={"date": "2001-01-01"},
        )
    with _client(tmp_path, configured=False) as client:
        unconfigured = client.get("/api/v1/market/state/description")
    assert typo.status_code == 400
    assert typo.json()["detail"]["code"] == "REQUEST_INVALID"
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "MARKET_STATE_DATE_UNAVAILABLE"
    assert unconfigured.status_code == 503
    assert unconfigured.json()["detail"]["code"] == "SOURCE_NOT_CONFIGURED"
