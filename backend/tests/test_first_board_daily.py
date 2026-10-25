import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from research_platform.core.database import make_engine
from research_platform.core.errors import DomainError
from research_platform.modules.research import daily_service as daily_module
from research_platform.modules.research.daily_service import FirstBoardDailyService
from research_platform.modules.research.daily_source import SqlFirstBoardSource, visible_factor
from research_platform.modules.research.daily_store import SqlFirstBoardStore
from research_platform.modules.research.first_board_classifier import ShortPath, Trend
from research_platform.modules.research.first_board_features import (
    HistoricalBar,
    compute_background_features,
)
from research_platform.modules.research.models import (
    FirstBoardBackgroundEvent,
    FirstBoardDailyBatch,
    FirstBoardDailyCurrent,
)

DAY = date(2026, 10, 23)
NOW = datetime(2026, 10, 25, tzinfo=UTC)
CALENDAR = [DAY - timedelta(days=n) for n in range(61, 0, -1)]


def history():
    return {
        day: HistoricalBar(
            day, Decimal(i + 10), Decimal(i + 11), Decimal(i + 9), Decimal(i + 10), Decimal(1)
        )
        for i, day in enumerate(CALENDAR)
    }


def test_features_match_original_formula_and_ignore_future_bars():
    bars = history()
    actual = compute_background_features(CALENDAR, bars)
    assert actual.trend == Trend.UP
    assert actual.short_path == ShortPath.UP_CONTINUATION
    assert actual.position_60d_pct == Decimal(6000) / Decimal(61)
    assert actual.return_5d_pct == 100 * (Decimal(70) / 65 - 1)
    assert actual.return_60d_pct == 600
    assert actual.ma_20 == Decimal("60.5")
    assert actual.ma_60 == Decimal("40.5")
    assert actual.quality_status == "COMPLETE"
    bars[DAY] = HistoricalBar(DAY, None, Decimal(10000), Decimal(1), Decimal(5000), Decimal(7))
    assert actual == compute_background_features(CALENDAR, bars)
    # A split with a causal cumulative factor must produce the same features.
    adjusted = {
        day: replace(
            bar,
            high=bar.high / 2,
            low=bar.low / 2,
            close=bar.close / 2,
            adjustment_factor=Decimal(2),
        )
        for day, bar in history().items()
    }
    assert actual == compute_background_features(CALENDAR, adjusted)


def test_feature_validity_is_per_window_and_missing_data_is_not_zero():
    bars = history()
    bars.pop(CALENDAR[0])
    result = compute_background_features(CALENDAR, bars)
    assert result.trend == Trend.UP
    assert result.return_5d_pct is not None
    assert result.return_60d_pct is None
    assert result.quality_status == "PARTIAL"
    bars[CALENDAR[-1]] = replace(bars[CALENDAR[-1]], adjustment_factor=None)
    missing = compute_background_features(CALENDAR, bars)
    assert missing.quality_status == "INSUFFICIENT"
    assert missing.return_5d_pct is None
    assert missing.trend == Trend.UNKNOWN
    assert compute_background_features(CALENDAR[-21:], history()).short_path != ShortPath.UNKNOWN
    assert compute_background_features([], {}).quality_status == "INSUFFICIENT"
    with pytest.raises(ValueError):
        compute_background_features(list(reversed(CALENDAR)), bars)


@pytest.mark.parametrize(("position", "band"), [(35, "low"), (75, "high")])
def test_features_keep_position_endpoints(position, band):
    bars = {
        day: HistoricalBar(day, None, Decimal(100), Decimal(0 + 1), Decimal("50"), Decimal(1))
        for day in CALENDAR
    }
    # A [1,101] adjusted range makes the final close 36/76 exactly 35%/75%.
    bars = {day: replace(bar, high=Decimal(101)) for day, bar in bars.items()}
    bars[CALENDAR[-1]] = replace(bars[CALENDAR[-1]], close=Decimal(position + 1))
    assert compute_background_features(CALENDAR, bars).position_band == band


def test_flat_range_keeps_neutral_trend_and_unknown_position():
    bars = {
        day: HistoricalBar(day, None, Decimal(5), Decimal(5), Decimal(5), Decimal(1))
        for day in CALENDAR
    }
    result = compute_background_features(CALENDAR, bars)
    assert result.position_60d_pct is None
    assert result.trend == Trend.SIDEWAYS
    assert result.short_path == ShortPath.NEUTRAL
    assert "FLAT_60D_RANGE" in result.feature_reason


def test_causal_factors_do_not_fill_backwards_or_cross_unaccounted_actions():
    first, action, later = CALENDAR[0], CALENDAR[20], CALENDAR[40]
    factors = {first: Decimal(1), later: Decimal(2)}
    dates = sorted(factors)
    assert visible_factor(first - timedelta(days=1), dates, factors, []) is None
    assert visible_factor(action, dates, factors, [action]) is None
    assert visible_factor(later, dates, factors, [action, later]) == 2
    assert visible_factor(action - timedelta(days=1), dates, factors, [action]) == 1
    factors[later] = Decimal("0.5")
    assert visible_factor(later, dates, factors, []) is None
    assert visible_factor(action - timedelta(days=1), dates, factors, []) == 1


@pytest.fixture
def source_engine(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'source.db').as_posix()}")
    with engine.begin() as c:
        for ddl in [
            "CREATE TABLE index_daily (indexCode TEXT, tradeDate DATE)",
            "CREATE TABLE dataset_definition (id INT, datasetCode TEXT, status TEXT)",
            """CREATE TABLE dataset_version (
               id INT, datasetId INT, status TEXT, startDate DATE, endDate DATE,
               version TEXT, universeDefinitionJson TEXT, filterDefinitionJson TEXT)""",
            """CREATE TABLE ds_first_limit_pullback_event (
               datasetVersionId INT, eventId TEXT, symbol TEXT,
               tradeDate DATE, isFirstLimit INT)""",
            """CREATE TABLE stock_daily_prices (
               stockCode TEXT, tradeDate DATE, openPrice TEXT,
               highPrice TEXT, lowPrice TEXT, closePrice TEXT)""",
            """CREATE TABLE adjustment_factors (
               securityCode TEXT, effectiveDate DATE, backFactor TEXT)""",
            "CREATE TABLE corporate_actions (securityCode TEXT, effectiveDate DATE)",
        ]:
            c.execute(text(ddl))
        c.execute(
            text("INSERT INTO index_daily VALUES ('000001.SH', :day)"),
            [{"day": day.isoformat()} for day in [*CALENDAR, DAY]],
        )
        c.execute(
            text("INSERT INTO dataset_definition VALUES (1, 'first_limit_pullback', 'ACTIVE')")
        )
        c.execute(
            text("""INSERT INTO dataset_version VALUES
            (42, 1, 'READY', :start, :end, 'v42', :universe, :filters),
            (43, 1, 'BUILDING', :start, :end, 'v43', :universe, :filters)"""),
            {
                "start": CALENDAR[0].isoformat(),
                "end": DAY.isoformat(),
                "universe": json.dumps({"boards": ["main"]}),
                "filters": json.dumps({"events": [{"kind": "firstBoard"}]}),
            },
        )
        c.execute(
            text("""INSERT INTO ds_first_limit_pullback_event VALUES
            (42, :event, '600001.SH', :day, 1)"""),
            {"event": f"600001.SH@{DAY}", "day": DAY.isoformat()},
        )
        c.execute(
            text("""INSERT INTO stock_daily_prices VALUES
            ('600001.SH', :day, :close, :high, :low, :close)"""),
            [
                {
                    "day": day.isoformat(),
                    "close": str(bar.close),
                    "high": str(bar.high),
                    "low": str(bar.low),
                }
                for day, bar in history().items()
            ],
        )
        c.execute(
            text("INSERT INTO adjustment_factors VALUES ('600001.SH', :day, '1')"),
            {"day": CALENDAR[0].isoformat()},
        )
    yield engine
    engine.dispose()


@pytest.fixture
def daily_service(source_engine, database_url):
    engine = make_engine(database_url)
    service = FirstBoardDailyService(
        SqlFirstBoardSource(source_engine),
        SqlFirstBoardStore(sessionmaker(engine, expire_on_commit=False)),
    )
    yield service
    engine.dispose()


def test_real_adapter_refresh_idempotency_revisions_and_pagination(daily_service, source_engine):
    assert daily_service.daily().status == "NOT_REFRESHED"
    result = daily_service.refresh(now=NOW)
    assert result.trading_day == DAY
    assert result.dataset_version_id == "42"
    assert result.status == "COMPLETE"
    assert result.source_event_count == result.total == 1
    assert result.items[0].class_code == "FBC-12"
    assert result.items[0].feature_cutoff == CALENDAR[-1]
    again = daily_service.refresh(now=NOW)
    assert again.batch_id == result.batch_id
    assert again.computed_at == result.computed_at
    assert daily_service.daily(DAY, offset=1).items == []
    with source_engine.begin() as c:
        c.execute(text("UPDATE stock_daily_prices SET highPrice = '100'"))
    revised = daily_service.refresh(now=NOW)
    assert revised.batch_id != result.batch_id
    assert daily_service.daily(DAY).batch_id == revised.batch_id
    with source_engine.begin() as c:
        c.execute(
            text("""UPDATE stock_daily_prices SET highPrice = :high WHERE tradeDate = :day"""),
            [{"high": str(bar.high), "day": day.isoformat()} for day, bar in history().items()],
        )
    reverted = daily_service.refresh(now=NOW)
    assert reverted.batch_id == result.batch_id
    assert daily_service.daily(DAY).batch_id == result.batch_id
    assert daily_service.daily(DAY, batch_id=revised.batch_id).batch_id == revised.batch_id
    with daily_service.store.sessions() as session:
        assert session.scalar(select(func.count()).select_from(FirstBoardDailyBatch)) == 2
        assert session.scalar(select(func.count()).select_from(FirstBoardBackgroundEvent)) == 2
    assert daily_service.daily(date(2000, 1, 1)).status == "NOT_REFRESHED"


def test_read_only_adapter_rejects_bad_event_and_missing_ready(daily_service, source_engine):
    with source_engine.begin() as c:
        c.execute(text("UPDATE ds_first_limit_pullback_event SET eventId = 'wrong'"))
    with pytest.raises(DomainError) as invalid:
        daily_service.refresh(now=NOW)
    assert invalid.value.code == "FIRST_BOARD_SOURCE_BAD_DATA"
    assert daily_service.daily().status == "NOT_REFRESHED"
    with source_engine.begin() as c:
        c.execute(text("UPDATE dataset_version SET status = 'BUILDING'"))
    with pytest.raises(DomainError) as missing:
        daily_service.refresh(now=NOW)
    assert missing.value.code == "FIRST_BOARD_DATE_UNAVAILABLE"


def test_closed_session_guard_and_missing_source(daily_service):
    for day in (DAY, DAY + timedelta(days=1)):
        with pytest.raises(DomainError) as not_closed:
            daily_service.refresh(day, now=datetime(2026, 10, 23, 6, tzinfo=UTC))
        assert not_closed.value.code == "FIRST_BOARD_DATE_NOT_CLOSED"
    result = daily_service.refresh(now=datetime(2026, 10, 23, 8, tzinfo=UTC))
    assert result.trading_day == DAY
    daily_service.source = None
    with pytest.raises(DomainError) as no_source:
        daily_service.refresh()
    assert no_source.value.code == "SOURCE_NOT_CONFIGURED"


def test_empty_snapshot_and_incomplete_features_are_distinct(daily_service, source_engine):
    with source_engine.begin() as c:
        c.execute(text("DELETE FROM adjustment_factors"))
    result = daily_service.refresh(now=NOW)
    assert result.status == "PARTIAL"
    assert result.class_counts == {"FBC-16": 1}
    assert result.items[0].quality_status == "INSUFFICIENT"
    assert result.items[0].position_60d_pct is None
    with source_engine.begin() as c:
        c.execute(text("DELETE FROM ds_first_limit_pullback_event"))
    empty = daily_service.refresh(now=NOW)
    assert empty.status == "EMPTY"
    assert empty.total == empty.source_event_count == 0


def test_daily_query_is_authenticated_shared_market_data_and_never_refreshes(
    client_factory, daily_service
):
    result = daily_service.refresh(now=NOW)
    first, second = client_factory(1), client_factory(2)
    for client in (first, second):
        client.app.state.first_board_daily = FirstBoardDailyService(None, daily_service.store)
        response = client.get("/api/v1/research/first-board-classifier/daily?date=2026-10-23")
        assert response.status_code == 200
        payload = response.json()
        assert payload["batch_id"] == result.batch_id
        assert payload["computed_at"].endswith("Z")
        assert isinstance(payload["items"][0]["position_60d_pct"], str)
        assert (
            client.get("/api/v1/research/first-board-classifier/daily?limit=501").status_code == 422
        )
    assert client_factory().get("/api/v1/research/first-board-classifier/daily").status_code == 503


def test_unsupported_axes_are_stored_without_fabricating_a_class(daily_service, monkeypatch):
    features = replace(
        compute_background_features(CALENDAR, history()),
        position_60d_pct=Decimal(90),
        trend=Trend.DOWN,
        short_path=ShortPath.DOWN_CONTINUATION,
    )
    monkeypatch.setattr(daily_module, "compute_background_features", lambda *_: features)
    result = daily_service.refresh(now=NOW)
    assert result.status == "PARTIAL"
    assert result.unsupported_count == 1
    assert result.items[0].class_code is None
    assert result.items[0].feature_reason == "UNSUPPORTED_AXIS_COMBINATION"


def test_concurrent_identical_refresh_publishes_one_batch(daily_service):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: daily_service.refresh(now=NOW), range(2)))
    assert results[0].batch_id == results[1].batch_id
    with daily_service.store.sessions() as session:
        assert session.scalar(select(func.count()).select_from(FirstBoardDailyBatch)) == 1
        assert session.scalar(select(func.count()).select_from(FirstBoardBackgroundEvent)) == 1


def test_count_mismatch_rolls_back_entire_publication(daily_service):
    result = daily_service.refresh(now=NOW)
    batch, _ = daily_service.store.read(
        DAY, result.taxonomy_version, result.feature_version, batch_id=result.batch_id
    )
    values = {column.name: getattr(batch, column.name) for column in batch.__table__.columns}
    values["batch_id"] = "b" * 64
    with pytest.raises(DomainError) as mismatch:
        daily_service.store.publish(values, [])
    assert mismatch.value.code == "FIRST_BOARD_STORAGE_BAD_DATA"
    with daily_service.store.sessions() as session:
        assert session.get(FirstBoardDailyBatch, "b" * 64) is None
    assert daily_service.daily().total == 1


def test_future_source_data_never_changes_historical_snapshot(daily_service, source_engine):
    result = daily_service.refresh(now=NOW)
    with source_engine.begin() as c:
        c.execute(
            text("INSERT INTO adjustment_factors VALUES ('600001.SH', :day, '0.01')"),
            {"day": DAY.isoformat()},
        )
        c.execute(
            text("INSERT INTO corporate_actions VALUES ('600001.SH', :day)"),
            {"day": DAY.isoformat()},
        )
        c.execute(
            text("""INSERT INTO stock_daily_prices VALUES
            ('600001.SH', :day, '99', '100', '98', '99')"""),
            {"day": DAY.isoformat()},
        )
    assert daily_service.refresh(now=NOW).batch_id == result.batch_id


def test_current_pointer_migration_preserves_existing_snapshots():
    engine = make_engine("sqlite:///:memory:")
    config = Config(str(Path(__file__).resolve().parents[2] / "backend/alembic.ini"))
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0007_first_board_daily")
        values = {
            "trading_day": DAY,
            "dataset_version_id": "42",
            "source_version": "v42",
            "universe_definition": "{}",
            "taxonomy_version": "first-board-background-v1",
            "feature_version": "first-board-prefix-v1",
            "source_event_count": 0,
            "computed_at": NOW.replace(tzinfo=None),
        }
        connection.execute(
            FirstBoardDailyBatch.__table__.insert(),
            [
                {**values, "batch_id": "a" * 64},
                {**values, "batch_id": "b" * 64},
            ],
        )
        connection.commit()
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        selected = connection.execute(select(FirstBoardDailyCurrent.batch_id)).scalar_one()
        assert selected == "b" * 64
        assert connection.scalar(select(func.count()).select_from(FirstBoardDailyBatch)) == 2
    engine.dispose()
