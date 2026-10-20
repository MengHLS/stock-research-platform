from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from research_platform.core.config import ReviewConfig, Settings
from research_platform.core.errors import DomainError
from research_platform.main import create_app
from research_platform.modules.identity.dependencies import Actor, require_actor
from research_platform.modules.market.legacy_review_source import LegacyMarketReviewSource
from research_platform.modules.market.review import (
    LEGACY_INDEX_SYMBOLS,
    PUBLIC_INDEX_SYMBOLS,
    IndexBar,
    LimitUpRecord,
    MarketReviewService,
    MarketWideRow,
    ReviewDateCoverage,
    StockBar,
    StockQuote,
)
from research_platform.modules.market.state_description import MarketStateLimitCounts


def record(
    symbol: str,
    day: str,
    *,
    time: str | None = "10:00:00",
    name: str | None = None,
    sector: str | None = "半导体",
) -> LimitUpRecord:
    return LimitUpRecord(
        trading_day=date.fromisoformat(day),
        symbol=symbol,
        name=name or symbol,
        sector=sector,
        limit_up_time=time,
    )


FIXTURE = [
    record("000001.SZ", "2026-09-16", time="09:35:00", name="甲"),
    record("000001.SZ", "2026-09-17", time="09:40:00", name="甲"),
    record("000001.SZ", "2026-09-18", time="09:45:00", name="甲"),
    record("000002.SZ", "2026-09-15", time="14:00:00", name="乙"),
    record("000002.SZ", "2026-09-18", time="10:05:00", name="乙"),
    record("000003.SZ", "2026-09-18", time="11:20:00", name="丙"),
    record("000004.SZ", "2026-09-16", time="13:10:00", name="丁"),
    record("000004.SZ", "2026-09-17", time="13:15:00", name="丁"),
    record("000005.SZ", "2026-09-17", time="14:30:00", name="戊"),
    record("000006.SZ", "2026-09-17", time="10:00:00", name="己"),
    record("000006.SZ", "2026-09-17", time="09:30:00", name="己"),
]


class FakeReviewSource:
    def __init__(self, records: list[LimitUpRecord] | None = None) -> None:
        self.records = list(FIXTURE if records is None else records)
        self.days = sorted({row.trading_day for row in self.records})
        if not self.days or self.days[0] > date(2026, 9, 15):
            self.days = sorted({date(2026, 9, 15), *self.days})
        self.quote_calls = 0
        self.stock_bar_calls = 0

    def trading_days(self, start: date, end: date) -> list[date]:
        return [day for day in self.days if start <= day <= end]

    def calendar_bounds(self, end: date) -> tuple[date | None, date | None]:
        days = [day for day in self.days if day <= end]
        return (days[0] if days else None, days[-1] if days else None)

    def latest_trading_day(self, end: date) -> date | None:
        eligible = [day for day in self.days if day <= end]
        return eligible[-1] if eligible else None

    def latest_limit_up_date(self, end: date) -> date | None:
        eligible = [row.trading_day for row in self.records if row.trading_day <= end]
        return max(eligible) if eligible else None

    def latest_review_date(self, end: date) -> date | None:
        eligible = [
            row.trading_day
            for row in self.records
            if row.trading_day <= end and row.trading_day in self.days
        ]
        return max(eligible) if eligible else None

    def trading_day_neighbours(
        self, trading_day: date, end: date
    ) -> tuple[date | None, date | None]:
        before = [day for day in self.days if day < trading_day and day <= end]
        after = [day for day in self.days if day > trading_day and day <= end]
        return (before[-1] if before else None, after[0] if after else None)

    def daily_coverage(self, start: date, end: date) -> list[ReviewDateCoverage]:
        result = []
        for day in self.days:
            if not start <= day <= end:
                continue
            result.append(
                ReviewDateCoverage(
                    trading_day=day,
                    limit_up_rows=sum(row.trading_day == day for row in self.records),
                    market_wide_rows=1,
                    shanghai_rows=1,
                    shenzhen_rows=1,
                    csi300_rows=1,
                    csi500_rows=1,
                )
            )
        return result

    def limit_up_records(self, start: date, end: date) -> list[LimitUpRecord]:
        return [row for row in self.records if start <= row.trading_day <= end]

    def stock_quotes(self, trading_day: date, symbols: list[str]) -> list[StockQuote]:
        return self.stock_quotes_range(trading_day, trading_day, symbols)

    def stock_quotes_range(
        self,
        start: date,
        end: date,
        symbols: list[str],
    ) -> list[StockQuote]:
        self.quote_calls += 1
        return [
            StockQuote(
                trading_day=trading_day,
                symbol=symbol,
                change_pct=Decimal("10.00") if symbol == "000001.SZ" else Decimal("-2.50"),
                one_word_board=symbol == "000001.SZ",
            )
            for trading_day in self.days
            if start <= trading_day <= end
            for symbol in symbols
        ]

    def stock_bars_range(self, start: date, end: date, symbol: str) -> list[StockBar]:
        self.stock_bar_calls += 1
        return [
            StockBar(
                trading_day=day,
                symbol=symbol,
                open=Decimal("10.00") + Decimal(offset),
                high=Decimal("10.50") + Decimal(offset),
                low=Decimal("9.80") + Decimal(offset),
                close=Decimal("10.20") + Decimal(offset),
                previous_close=Decimal("10.00") + Decimal(offset),
            )
            for offset, day in enumerate(day for day in self.days if start <= day <= end)
        ]

    def market_wide_rows(self, start: date, end: date) -> list[MarketWideRow]:
        return [
            MarketWideRow(
                trading_day=day,
                turnover_100m_cny=Decimal("12000.50"),
                margin_balance_100m_cny=Decimal("18000.25"),
            )
            for day in self.days
            if start <= day <= end
        ]

    def index_rows(self, start: date, end: date, symbols: list[str]) -> list[IndexBar]:
        rows = []
        for symbol in symbols:
            for offset, day in enumerate(day for day in self.days if start <= day <= end):
                close = Decimal("3000") + Decimal(offset * 10)
                rows.append(
                    IndexBar(
                        trading_day=day,
                        symbol=symbol,
                        open=close - 5,
                        high=close + 10,
                        low=close - 10,
                        close=close,
                        amount_source=Decimal("500000"),
                        volume_source=Decimal("250000"),
                    )
                )
        return rows


class FakeIndexSupplement:
    def __init__(
        self,
        days: list[date] | None = None,
        *,
        fail_symbols: set[str] | None = None,
    ) -> None:
        self.days = list(days or [])
        self.fail_symbols = fail_symbols or set()
        self.calls: list[tuple[date, date, list[str]]] = []

    def index_rows(
        self,
        start: date,
        end: date,
        symbols: list[str],
    ) -> dict[str, list[IndexBar]]:
        self.calls.append((start, end, list(symbols)))
        rows: dict[str, list[IndexBar]] = {}
        for symbol in symbols:
            if symbol in self.fail_symbols:
                raise DomainError("MARKET_SOURCE_UNAVAILABLE")
            base = Decimal("4000") if symbol == "399006.SZ" else Decimal("1000")
            rows[symbol] = [
                IndexBar(
                    trading_day=day,
                    symbol=symbol,
                    open=base + Decimal(offset * 10) - 5,
                    high=base + Decimal(offset * 10) + 10,
                    low=base + Decimal(offset * 10) - 10,
                    close=base + Decimal(offset * 10),
                    amount_source=None,
                    volume_source=None,
                )
                for offset, day in enumerate(day for day in self.days if start <= day <= end)
            ]
        return rows


class FakeMarketStateCountSource:
    def __init__(
        self,
        rows: list[MarketStateLimitCounts] | None = None,
        *,
        error_code: str | None = None,
    ) -> None:
        self.error_code = error_code
        self.rows = (
            rows
            if rows is not None
            else [
                MarketStateLimitCounts(
                    trading_day=date(2026, 9, 15),
                    limit_up_close_count=0,
                    limit_down_close_count=2,
                    broken_board_count=1,
                    broken_board_rate_pct=Decimal("100"),
                    coverage_status="VERIFIED_UNIVERSE",
                ),
                MarketStateLimitCounts(
                    trading_day=date(2026, 9, 16),
                    limit_up_close_count=1,
                    limit_down_close_count=0,
                    broken_board_count=0,
                    broken_board_rate_pct=Decimal("0"),
                    coverage_status="VERIFIED_UNIVERSE",
                ),
                MarketStateLimitCounts(
                    trading_day=date(2026, 9, 17),
                    limit_up_close_count=4,
                    limit_down_close_count=3,
                    broken_board_count=2,
                    broken_board_rate_pct=Decimal("33.33333333333333333333333333"),
                    coverage_status="VERIFIED_UNIVERSE",
                ),
                MarketStateLimitCounts(
                    trading_day=date(2026, 9, 18),
                    limit_up_close_count=3,
                    limit_down_close_count=5,
                    broken_board_count=2,
                    broken_board_rate_pct=Decimal("40"),
                    coverage_status="VERIFIED_UNIVERSE",
                ),
            ]
        )

    def limit_counts(
        self,
        start: date,
        end: date,
    ) -> dict[date, MarketStateLimitCounts]:
        if self.error_code is not None:
            raise DomainError(self.error_code)
        return {row.trading_day: row for row in self.rows if start <= row.trading_day <= end}


def service(
    source: FakeReviewSource | None = None,
    *,
    market_state_counts: FakeMarketStateCountSource | None = None,
    index_supplement: FakeIndexSupplement | None | object = ...,
    **config,
) -> MarketReviewService:
    review_source = source or FakeReviewSource()
    supplement = (
        FakeIndexSupplement(review_source.days) if index_supplement is ... else index_supplement
    )
    return MarketReviewService(
        review_source,
        ReviewConfig(**config),
        market_state_counts=market_state_counts or FakeMarketStateCountSource(),
        index_supplement=supplement,
    )


def test_overview_matches_legacy_board_roster_fixture():
    overview = service().overview(date(2026, 9, 18), 4)

    assert overview.previous_trading_day == date(2026, 9, 17)
    assert overview.summary.assessment == "available"
    assert overview.summary.total_limit_up == 3
    assert overview.summary.first_board_count == 2
    assert overview.summary.connection_board_count == 1
    assert overview.summary.max_board == 3
    assert overview.summary.three_board_plus_count == 1
    assert overview.summary.emotion_score == 52
    assert overview.summary.broken_count == 3
    assert overview.summary.broken_connection_count == 1
    assert [row.symbol for row in overview.ladder.connection] == ["000001.SZ"]
    assert {row.symbol for row in overview.ladder.first} == {"000002.SZ", "000003.SZ"}
    assert [(row.symbol, row.boards, row.broken_kind) for row in overview.ladder.broken] == [
        ("000004.SZ", 2, "connection"),
        ("000006.SZ", 1, "first"),
        ("000005.SZ", 1, "first"),
    ]
    assert overview.ladder.broken[1].limit_up_time == "09:30:00"
    assert overview.ladder.connection[0].change_pct == Decimal("10.00")
    assert overview.ladder.connection[0].one_word_board is True


def test_history_rows_are_bounded_and_use_only_data_at_or_before_each_day():
    overview = service().overview(date(2026, 9, 18), 2)

    assert [row.date for row in overview.history] == [
        date(2026, 9, 17),
        date(2026, 9, 18),
    ]
    assert overview.history[0].total_limit_up == 4
    assert overview.history[0].broken_count == 0
    assert overview.history[0].emotion_score == 26
    assert overview.history[0].max_board_stock_total == 2
    assert overview.history[1].emotion_score == 52
    assert overview.history[1].broken_count == 3
    assert overview.history[1].broken_connection_count == 1
    assert overview.history[1].max_board_stocks[0].symbol == "000001.SZ"
    assert overview.window_requested == 2
    assert overview.window_actual == 2


def test_overview_returns_120_trading_days_and_reports_short_history():
    source = FakeReviewSource()
    source.days = [
        date(2026, 1, 1) + timedelta(days=offset)
        for offset in range(200)
        if (date(2026, 1, 1) + timedelta(days=offset)).weekday() < 5
    ]
    review = service(source)
    result = review.overview(source.days[-1], 120)
    assert result.window_requested == result.window_actual == len(result.history) == 120
    assert [row.date for row in result.history] == source.days[-120:]
    assert all(row.turnover_100m_cny == Decimal("12000.50") for row in result.history)
    short = review.overview(source.days[9], 120)
    assert short.window_requested == 120
    assert short.window_actual == len(short.history) == 10


def test_history_includes_all_known_six_plus_stocks_even_below_maximum():
    days = [date(2026, 8, 3) + timedelta(days=offset) for offset in range(10)]
    records = [record("600000.SH", day.isoformat()) for day in days]
    # One seven-board leader, fifteen six-board stocks, and a five-board stock.
    for number, start in [(1, 3), *[(number, 4) for number in range(2, 17)], (17, 5)]:
        records.extend(
            record(f"{number:06d}.SZ", day.isoformat(), name=f"完整名称{number}")
            for day in days[start:]
        )
    source = FakeReviewSource(records)
    source.days = days
    history = service(source).overview(days[-1], 2).history
    latest = history[-1]
    # The chain touching the calendar boundary stays unknown; known names still survive.
    assert latest.max_board is None
    assert [(stock.name, stock.boards) for stock in latest.high_board_stocks] == [
        ("完整名称1", 7),
        *[(f"完整名称{number}", 6) for number in range(2, 17)],
    ]
    assert [(stock.name, stock.boards) for stock in history[0].high_board_stocks] == [
        ("完整名称1", 6)
    ]
    source.records = [row for row in records if row.symbol != "600000.SH"] + [
        record("600001.SH", day.isoformat()) for day in days[:4]
    ]
    latest = service(source).overview(days[-1], 1).history[0]
    assert latest.max_board == 7
    assert len(latest.high_board_stocks) == 16
    assert latest.max_board_stock_total == len(latest.max_board_stocks) == 1


def test_limit_up_detail_returns_current_and_broken_rows_across_window():
    source = FakeReviewSource()
    result = service(source).limit_up(date(2026, 9, 18), 2)

    assert result.window_requested == 2
    assert result.window_actual == 2
    assert [day.date for day in result.days] == [date(2026, 9, 17), date(2026, 9, 18)]
    assert result.days[0].total_limit_up == 4
    assert result.days[0].broken_count == 0
    assert result.days[1].total_limit_up == 3
    assert result.days[1].broken_count == 3
    current = [
        row for row in result.rows if row.date == date(2026, 9, 18) and row.status == "limit_up"
    ]
    broken = [
        row for row in result.rows if row.date == date(2026, 9, 18) and row.status == "broken"
    ]
    assert {row.symbol for row in current} == {"000001.SZ", "000002.SZ", "000003.SZ"}
    assert [(row.symbol, row.boards, row.boards_as_of_date) for row in broken] == [
        ("000004.SZ", 2, date(2026, 9, 17)),
        ("000005.SZ", 1, date(2026, 9, 17)),
        ("000006.SZ", 1, date(2026, 9, 17)),
    ]
    assert all(row.change_pct == Decimal("-2.50") for row in broken)
    assert all(row.one_word_board is None for row in broken)
    assert all(row.limit_up_time_as_of_date == row.boards_as_of_date for row in broken)
    assert source.quote_calls == 1


def test_limit_up_detail_keeps_missing_days_unknown_instead_of_zero():
    source = FakeReviewSource([record("000001.SZ", "2026-09-17")])
    source.days = [date(2026, 9, 17), date(2026, 9, 18)]

    result = service(source).limit_up(date(2026, 9, 18), 2)

    assert result.days[1].assessment == "missing"
    assert result.days[1].total_limit_up is None
    assert result.days[1].limit_up.status == "missing"
    assert {issue.code for issue in result.issues} >= {"target_limit_up_missing"}
    assert {row.date for row in result.rows} == {date(2026, 9, 17)}


def test_stock_series_canonicalizes_symbol_and_returns_real_candles():
    source = FakeReviewSource()
    source.days = [
        date(2026, 9, 14),
        date(2026, 9, 15),
        date(2026, 9, 16),
        date(2026, 9, 17),
        date(2026, 9, 18),
    ]

    result = service(source).stock_series("sz000001", date(2026, 9, 18), 5)

    assert result.symbol == "000001.SZ"
    assert result.window_requested == 5
    assert result.window_actual == 5
    assert result.coverage.row_count == 5
    assert [bar.date for bar in result.bars] == source.days
    assert all(
        bar.open is not None
        and bar.high is not None
        and bar.low is not None
        and bar.close is not None
        for bar in result.bars
    )
    assert result.bars[0].ma5 is None
    assert result.bars[-1].ma5 is not None
    assert result.bars[-1].ma20 is None
    assert source.stock_bar_calls == 1


def test_stock_series_preserves_gaps_and_uses_hidden_history_for_moving_averages():
    class GappedSource(FakeReviewSource):
        def stock_bars_range(self, start, end, symbol):
            return [
                bar
                for bar in super().stock_bars_range(start, end, symbol)
                if bar.trading_day != self.days[-2]
            ]

    source = GappedSource()
    source.days = [
        date(2026, 8, 3) + timedelta(days=offset)
        for offset in range(47)
        if (date(2026, 8, 3) + timedelta(days=offset)).weekday() < 5
    ]
    result = service(source).stock_series("000001.SZ", source.days[-1], 2)
    assert result.window_actual == 2
    assert result.missing_days == 1
    assert result.coverage.row_count == 1
    assert result.bars[0].close is None
    assert result.bars[1].ma5 is None
    assert result.bars[1].ma20 is None
    assert result.bars[1].change_pct is not None
    assert "stock_history_missing" in {issue.code for issue in result.issues}

    complete = FakeReviewSource()
    complete.days = source.days
    target = complete.days[-2]
    series = service(complete).stock_series("000001.SZ", target, 1)
    assert [bar.date for bar in series.bars] == [target]
    assert series.bars[0].ma20 == Decimal("19.70")


@pytest.mark.parametrize(
    "defect",
    ["duplicate", "wrong_symbol", "non_finite", "inverted", "negative_previous", "extreme"],
)
def test_stock_series_rejects_bad_source_data(defect):
    class BadSource(FakeReviewSource):
        def stock_bars_range(self, start, end, symbol):
            bars = super().stock_bars_range(start, end, symbol)
            if defect == "duplicate":
                return [*bars, bars[-1]]
            if defect == "wrong_symbol":
                return [replace(bars[-1], symbol="000002.SZ")]
            if defect == "inverted":
                return [replace(bars[-1], high=Decimal("8"), low=Decimal("12"))]
            if defect == "negative_previous":
                return [replace(bars[-1], previous_close=Decimal("-10"))]
            if defect == "extreme":
                return [
                    replace(
                        bars[-1],
                        open=Decimal("1E100"),
                        high=Decimal("1E100"),
                        low=Decimal("1E100"),
                        close=Decimal("1E100"),
                    )
                ]
            return [replace(bars[-1], close=Decimal("NaN"))]

    with pytest.raises(DomainError) as failure:
        service(BadSource()).stock_series("000001.SZ", date(2026, 9, 18), 2)
    assert failure.value.code == "MARKET_REVIEW_SOURCE_BAD_DATA"


def test_stock_series_counts_partial_source_rows_as_present():
    class PartialSource(FakeReviewSource):
        def stock_bars_range(self, start, end, symbol):
            return [replace(bar, open=None) for bar in super().stock_bars_range(start, end, symbol)]

    result = service(PartialSource()).stock_series("000001.SZ", date(2026, 9, 18), 2)
    assert result.coverage.status == "available"
    assert result.coverage.row_count == 2
    assert result.missing_days == 2
    assert all(bar.open is None and bar.close is not None for bar in result.bars)


def test_missing_previous_limit_records_leave_board_metrics_unknown():
    source = FakeReviewSource([record("000001.SZ", "2026-09-18")])
    source.days = [date(2026, 9, 17), date(2026, 9, 18)]
    overview = service(source).overview(date(2026, 9, 18), 2)

    assert overview.summary.assessment == "partial"
    assert overview.summary.total_limit_up == 1
    assert overview.summary.first_board_count is None
    assert overview.summary.connection_board_count is None
    assert overview.summary.emotion_score is None
    assert overview.ladder.unknown[0].boards is None
    assert {issue.code for issue in overview.issues} >= {"previous_limit_up_missing"}
    assert "board_history_exhausted" not in {issue.code for issue in overview.issues}
    assert "history_window_truncated" not in {issue.code for issue in overview.issues}


def test_missing_record_day_in_broken_chain_is_not_reported_as_query_start():
    source = FakeReviewSource(
        [
            record("000004.SZ", "2026-09-17"),
            record("000001.SZ", "2026-09-18"),
        ]
    )
    source.days = [date(2026, 9, 15) + timedelta(days=offset) for offset in range(4)]
    overview = service(source).overview(date(2026, 9, 18), 4)

    assert overview.ladder.broken[0].boards is None
    assert "board_history_exhausted" not in {issue.code for issue in overview.issues}
    assert "history_window_truncated" not in {issue.code for issue in overview.issues}


def test_board_chain_touching_calendar_start_is_not_reported_as_first_board():
    rows = [
        record("000001.SZ", "2026-09-15"),
        record("000001.SZ", "2026-09-16"),
        record("000001.SZ", "2026-09-17"),
        record("000001.SZ", "2026-09-18"),
    ]
    overview = service(FakeReviewSource(rows)).overview(date(2026, 9, 18), 4)

    assert overview.summary.assessment == "partial"
    assert overview.summary.total_limit_up == 1
    assert overview.summary.max_board is None
    assert overview.ladder.unknown[0].boards is None
    assert {issue.code for issue in overview.issues} >= {"board_history_exhausted"}


def test_no_target_limit_records_are_missing_not_zero():
    source = FakeReviewSource([record("000001.SZ", "2026-09-17")])
    source.days = [date(2026, 9, 17), date(2026, 9, 18)]
    overview = service(source).overview(date(2026, 9, 18), 2)

    assert overview.summary.assessment == "missing"
    assert overview.summary.total_limit_up is None
    assert overview.ladder.broken == []
    assert {issue.code for issue in overview.issues} >= {"target_limit_up_missing"}


def test_unknown_broken_board_keeps_broken_count_unknown():
    rows = [
        record("000004.SZ", "2026-09-15"),
        record("000004.SZ", "2026-09-16"),
        record("000004.SZ", "2026-09-17"),
        record("000001.SZ", "2026-09-18"),
    ]
    overview = service(FakeReviewSource(rows)).overview(date(2026, 9, 18), 4)

    assert overview.summary.assessment == "partial"
    assert overview.summary.total_limit_up == 1
    assert overview.summary.broken_count is None
    assert overview.summary.broken_connection_count is None
    assert overview.ladder.broken[0].boards is None
    assert {issue.code for issue in overview.issues} >= {
        "board_history_exhausted",
        "history_window_truncated",
    }


def test_dates_report_each_presence_only_coverage():
    result = service().dates(date(2026, 9, 15), date(2026, 9, 18))

    assert [row.date for row in result.dates] == [
        date(2026, 9, 15),
        date(2026, 9, 16),
        date(2026, 9, 17),
        date(2026, 9, 18),
    ]
    assert result.dates[0].limit_up.status == "available"
    assert result.dates[1].indices.csi300.status == "available"
    assert result.dates[0].limit_up.completeness == "presence_only"
    assert result.dates[0].limit_up_close_count == 0
    assert result.dates[0].limit_down_close_count == 2
    assert result.dates[1].limit_down_close_count == 0
    assert result.dates[-1].limit_up_close_count == 3
    assert result.dates[-1].limit_down_close_count == 5
    assert result.dates[-1].market_state_counts is not None


def test_dates_keep_missing_market_state_counts_null_and_emit_an_issue():
    result = service(market_state_counts=FakeMarketStateCountSource([])).dates(
        date(2026, 9, 15),
        date(2026, 9, 18),
    )

    assert all(row.market_state_counts is None for row in result.dates)
    assert all(row.limit_up_close_count is None for row in result.dates)
    assert all(row.limit_down_close_count is None for row in result.dates)
    assert "market_state_counts_unavailable" in {issue.code for issue in result.issues}


def test_dates_report_partial_market_state_coverage():
    only_first = [
        replace(
            FakeMarketStateCountSource().rows[0],
            coverage_status="EXPLORATORY",
        )
    ]
    result = service(market_state_counts=FakeMarketStateCountSource(only_first)).dates(
        date(2026, 9, 15),
        date(2026, 9, 18),
    )

    assert result.dates[0].market_state_counts is not None
    assert result.dates[-1].market_state_counts is None
    assert {issue.code for issue in result.issues} >= {
        "market_state_counts_unavailable",
        "market_state_counts_unverified",
    }


@pytest.mark.parametrize(
    ("error_code", "issue_code"),
    [
        ("SOURCE_NOT_CONFIGURED", "market_state_counts_not_configured"),
        ("MARKET_STATE_SOURCE_UNAVAILABLE", "market_state_counts_source_unavailable"),
        ("MARKET_STATE_SOURCE_BAD_DATA", "market_state_counts_source_bad_data"),
    ],
)
def test_dates_distinguish_market_state_failure_reasons(error_code, issue_code):
    result = service(market_state_counts=FakeMarketStateCountSource(error_code=error_code)).dates(
        date(2026, 9, 15),
        date(2026, 9, 18),
    )

    assert all(row.market_state_counts is None for row in result.dates)
    assert issue_code in {issue.code for issue in result.issues}


def test_dates_report_an_unconfigured_market_state_dependency():
    result = MarketReviewService(
        FakeReviewSource(),
        ReviewConfig(),
        market_state_counts=None,
    ).dates(
        date(2026, 9, 15),
        date(2026, 9, 18),
    )

    assert all(row.market_state_counts is None for row in result.dates)
    assert "market_state_counts_not_configured" in {issue.code for issue in result.issues}


def test_context_defaults_to_latest_limit_up_day_and_returns_neighbours():
    result = service().context(as_of=date(2026, 9, 20))

    assert result.default_date == date(2026, 9, 18)
    assert result.default_date_reason == "latest_limit_up"
    assert result.latest_limit_up_date == date(2026, 9, 18)
    assert result.previous_trading_day == date(2026, 9, 17)
    assert result.next_trading_day is None
    assert result.requested_date_known is None


def test_context_keeps_explicit_unknown_date_visible():
    result = service().context(date(2026, 9, 19), as_of=date(2026, 9, 20))

    assert result.default_date == date(2026, 9, 18)
    assert result.requested_date == date(2026, 9, 19)
    assert result.requested_date_known is False
    assert result.previous_trading_day == date(2026, 9, 18)
    assert result.next_trading_day is None


def test_context_uses_latest_limit_day_that_is_also_in_calendar():
    source = FakeReviewSource(
        [
            record("000001.SZ", "2026-09-16"),
            record("000002.SZ", "2026-09-19"),
        ]
    )
    source.days = [date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 18)]
    result = service(source).context(as_of=date(2026, 9, 20))

    assert result.latest_limit_up_date == date(2026, 9, 19)
    assert result.default_date == date(2026, 9, 16)
    assert result.default_date_reason == "latest_limit_up"


def test_context_falls_back_to_calendar_when_limit_days_have_no_intersection():
    source = FakeReviewSource([record("000001.SZ", "2026-09-19")])
    source.days = [date(2026, 9, 17), date(2026, 9, 18)]
    result = service(source).context(as_of=date(2026, 9, 20))

    assert result.default_date == date(2026, 9, 18)
    assert result.default_date_reason == "latest_calendar"


def test_indices_calculate_change_and_only_complete_moving_averages():
    result = service().indices(date(2026, 9, 18), 4)
    shanghai = result.indices[0]

    assert shanghai.symbol == "000001.SH"
    assert [bar.close for bar in shanghai.bars] == [
        Decimal("3000"),
        Decimal("3010"),
        Decimal("3020"),
        Decimal("3030"),
    ]
    assert shanghai.bars[0].change_pct is None
    assert shanghai.bars[1].change_pct == Decimal("0.33")
    assert shanghai.bars[3].ma5 is None
    assert result.window_actual == 4


def test_single_index_window_still_prefetches_complete_ma_history():
    source = FakeReviewSource([])
    source.days = [date(2026, 9, 1) + timedelta(days=index) for index in range(20)]
    result = service(source).indices(source.days[-1], 1)

    for item in result.indices[:4]:
        target = item.bars[0]
        assert target.ma5 == Decimal("3170.00")
        assert target.ma20 == Decimal("3095.00")
    chinext, star50 = result.indices[4:]
    assert chinext.bars[0].ma5 == Decimal("4170.00")
    assert chinext.bars[0].ma20 == Decimal("4095.00")
    assert star50.bars[0].ma5 == Decimal("1170.00")
    assert star50.bars[0].ma20 == Decimal("1095.00")


def test_review_merges_four_legacy_indices_with_two_public_indices_in_order():
    source = FakeReviewSource()
    supplement = FakeIndexSupplement(source.days)
    review = service(source, index_supplement=supplement)

    result = review.indices(date(2026, 9, 18), 4)
    overview = review.overview(date(2026, 9, 18), 4)

    assert [item.symbol for item in result.indices] == [
        *LEGACY_INDEX_SYMBOLS,
        *PUBLIC_INDEX_SYMBOLS,
    ]
    assert [item.symbol for item in overview.indices] == [
        *LEGACY_INDEX_SYMBOLS,
        *PUBLIC_INDEX_SYMBOLS,
    ]
    assert [call[2] for call in supplement.calls] == [["399006.SZ"], ["000688.SH"]] * 2
    chinext = result.indices[4]
    star50 = result.indices[5]
    assert (chinext.symbol, chinext.name, chinext.bars[-1].close) == (
        "399006.SZ",
        "创业板指",
        Decimal("4030"),
    )
    assert (star50.symbol, star50.name, star50.bars[-1].close) == (
        "000688.SH",
        "科创50",
        Decimal("1030"),
    )
    assert chinext.bars[-1].amount_source is None
    assert overview.indices[-2].close == Decimal("4010")
    assert overview.indices[-1].change_pct == Decimal("1.00")


def test_120_day_window_has_complete_ma_inputs_for_public_indices():
    source = FakeReviewSource([])
    source.days = [date(2026, 1, 1) + timedelta(days=index) for index in range(139)]
    supplement = FakeIndexSupplement(source.days)

    result = service(source, index_supplement=supplement).indices(source.days[-1], 120)

    assert result.window_actual == 120
    for item in result.indices[-2:]:
        assert len(item.bars) == 120
        assert item.missing_days == 0
        assert item.bars[0].ma20 is not None
        assert item.bars[-1].ma20 is not None
    assert supplement.calls[0][:2] == (source.days[0], source.days[-1])


def test_public_index_history_older_than_coverage_stays_missing():
    source = FakeReviewSource([])
    source.days = [date(2026, 1, 5), date(2026, 1, 6)]
    supplement = FakeIndexSupplement([date(2026, 3, 2), date(2026, 3, 3)])

    result = service(source, index_supplement=supplement).indices(date(2026, 1, 6), 2)
    overview = service(source, index_supplement=supplement).overview(date(2026, 1, 6), 2)

    for item in result.indices[-2:]:
        assert item.coverage.status == "missing"
        assert item.missing_days == 2
        assert all(bar.close is None for bar in item.bars)
    for item in overview.indices[-2:]:
        assert item.coverage.status == "missing"
        assert item.close is None


def test_one_public_index_failure_does_not_hide_the_other_or_legacy_indices():
    source = FakeReviewSource()
    supplement = FakeIndexSupplement(source.days, fail_symbols={"399006.SZ"})

    result = service(source, index_supplement=supplement).indices(date(2026, 9, 18), 4)

    assert result.indices[0].coverage.status == "available"
    assert result.indices[4].coverage.status == "missing"
    assert result.indices[5].coverage.status == "available"
    assert result.indices[5].bars[-1].close == Decimal("1030")


def test_range_and_window_limits_fail_with_stable_codes():
    review = service(max_range_days=366, max_window=120)
    with pytest.raises(DomainError) as bad_range:
        review.dates(date(2026, 1, 1), date(2026, 1, 1) + timedelta(days=366))
    assert bad_range.value.code == "MARKET_REVIEW_RANGE_INVALID"

    with pytest.raises(DomainError) as bad_window:
        review.overview(date(2026, 9, 18), 121)
    assert bad_window.value.code == "MARKET_REVIEW_RANGE_INVALID"

    with pytest.raises(ValidationError):
        Settings(review={"max_range_days": 367}, _env_file=None)


def test_legacy_source_reads_reviewed_columns_from_sqlite():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE index_daily (
                    indexCode TEXT, tradeDate TEXT, open REAL, high REAL, low REAL,
                    close REAL, amount REAL, volume REAL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE limit_up_records (
                    stockCode TEXT, stockName TEXT, limitUpDate TEXT,
                    limitUpTime TEXT, sector TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE stock_daily_prices (
                    stockCode TEXT, tradeDate TEXT, openPrice TEXT, highPrice TEXT,
                    lowPrice TEXT, closePrice TEXT, preClosePrice TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE market_data (
                    dataDate TEXT, turnover TEXT, marginBalance TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO index_daily VALUES
                ('000001.SH', '2026-09-18', 3000, 3040, 2990, 3030, 500000, 250000)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO limit_up_records VALUES
                ('000001.SZ', '甲', '2026-09-18', '09:30:00', '半导体')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO stock_daily_prices VALUES
                ('000001.SZ', '2026-09-18', '10', '10', '10', '10', '9'),
                ('000002.SZ', '2026-09-18', '10', '10', '10', '9', '10')
                """
            )
        )
        connection.execute(
            text("INSERT INTO market_data VALUES ('2026-09-18', '12000.5', '18000.25')")
        )
    source = LegacyMarketReviewSource(engine)

    assert source.trading_days(date(2026, 9, 18), date(2026, 9, 18)) == [date(2026, 9, 18)]
    assert source.calendar_bounds(date(2026, 9, 20)) == (date(2026, 9, 18), date(2026, 9, 18))
    assert source.latest_trading_day(date(2026, 9, 20)) == date(2026, 9, 18)
    assert source.latest_limit_up_date(date(2026, 9, 20)) == date(2026, 9, 18)
    assert source.latest_review_date(date(2026, 9, 20)) == date(2026, 9, 18)
    assert source.trading_day_neighbours(date(2026, 9, 18), date(2026, 9, 20)) == (None, None)
    coverage = source.daily_coverage(date(2026, 9, 18), date(2026, 9, 18))[0]
    assert coverage.limit_up_rows == 1
    assert coverage.shanghai_rows == 1
    assert source.limit_up_records(date(2026, 9, 18), date(2026, 9, 18))[0].sector == "半导体"
    quote = source.stock_quotes(date(2026, 9, 18), ["000001.SZ"])[0]
    assert quote.change_pct == Decimal("11.11111111111111111111111111")
    assert quote.one_word_board is True
    down_quote = source.stock_quotes(date(2026, 9, 18), ["000002.SZ"])[0]
    assert down_quote.one_word_board is False
    stock_bar = source.stock_bars_range(
        date(2026, 9, 18),
        date(2026, 9, 18),
        "000001.SZ",
    )[0]
    assert (stock_bar.open, stock_bar.high, stock_bar.low, stock_bar.close) == (
        Decimal("10.0"),
        Decimal("10.0"),
        Decimal("10.0"),
        Decimal("10.0"),
    )
    market = source.market_wide_rows(date(2026, 9, 18), date(2026, 9, 18))[0]
    assert market.turnover_100m_cny == Decimal("12000.5")
    index = source.index_rows(date(2026, 9, 18), date(2026, 9, 18), ["000001.SH"])[0]
    assert index.close == Decimal("3030.0")
    engine.dispose()


def test_legacy_source_schema_failure_maps_to_unavailable():
    engine = create_engine("sqlite://")
    source = LegacyMarketReviewSource(engine)
    with pytest.raises(DomainError) as failure:
        source.trading_days(date(2026, 9, 18), date(2026, 9, 18))
    assert failure.value.code == "MARKET_REVIEW_SOURCE_UNAVAILABLE"
    engine.dispose()


@pytest.mark.parametrize(
    ("server_code", "sqlstate", "expected_code"),
    [
        (1045, None, "MARKET_REVIEW_SOURCE_AUTH_FAILED"),
        (1044, "42000", "MARKET_REVIEW_SOURCE_AUTH_FAILED"),
        (1142, "42000", "MARKET_REVIEW_SOURCE_AUTH_FAILED"),
        (1143, "42000", "MARKET_REVIEW_SOURCE_AUTH_FAILED"),
        (9999, "28000", "MARKET_REVIEW_SOURCE_AUTH_FAILED"),
        (1146, None, "MARKET_REVIEW_SOURCE_UNAVAILABLE"),
    ],
)
def test_legacy_source_error_classification(server_code, sqlstate, expected_code):
    class DatabaseAuthError(Exception):
        pass

    DatabaseAuthError.args = (server_code, "database error")
    if sqlstate is not None:
        DatabaseAuthError.sqlstate = sqlstate

    engine = MagicMock()
    engine.connect.side_effect = OperationalError("SELECT 1", {}, DatabaseAuthError())
    source = LegacyMarketReviewSource(engine)

    with pytest.raises(DomainError) as failure:
        source.trading_days(date(2026, 9, 18), date(2026, 9, 18))

    assert failure.value.code == expected_code


def _review_client(database_url, source: FakeReviewSource, user_id: int = 1):
    settings = Settings(environment="test", database_url=database_url, _env_file=None)
    app = create_app(settings)
    app.dependency_overrides[require_actor] = lambda: Actor(user_id=user_id)
    app.state.market_review = MarketReviewService(
        source,
        settings.review,
        market_state_counts=FakeMarketStateCountSource(),
        index_supplement=FakeIndexSupplement(source.days),
    )
    return TestClient(app)


def test_review_api_requires_identity_and_rejects_unknown_query(database_url):
    settings = Settings(environment="test", database_url=database_url, _env_file=None)
    with TestClient(create_app(settings)) as anonymous:
        denied = anonymous.get(
            "/api/v1/market/review/overview",
            params={"date": "2026-09-18"},
        )
    assert denied.status_code == 503
    assert denied.json()["detail"]["code"] == "AUTH_NOT_CONFIGURED"

    client = _review_client(database_url, FakeReviewSource())
    with client:
        typo = client.get(
            "/api/v1/market/review/overview",
            params={"date": "2026-09-18", "widnow": 20},
        )
    assert typo.status_code == 400
    assert typo.json()["detail"]["code"] == "REQUEST_INVALID"


def test_review_api_is_shared_across_actors_and_returns_decimal_strings(database_url):
    for user_id in (1, 2):
        client = _review_client(database_url, FakeReviewSource(), user_id)
        with client:
            response = client.get(
                "/api/v1/market/review/overview",
                params={"date": "2026-09-18", "window": 4},
            )
            limit_up = client.get(
                "/api/v1/market/review/limit-up",
                params={"date": "2026-09-18", "window": 2},
            )
            stock_series = client.get(
                "/api/v1/market/review/stock-series",
                params={"symbol": "000001.SZ", "date": "2026-09-18", "window": 4},
            )
        assert response.status_code == 200
        assert limit_up.status_code == 200
        assert stock_series.status_code == 200
        body = response.json()
        assert body["summary"]["emotion_score"] == 52
        assert body["ladder"]["connection"][0]["change_pct"] == "10.00"
        assert body["turnover_100m_cny"] == "12000.50"
        assert body["methodology"]["version"] == "market-review-v1"
        assert limit_up.json()["window_actual"] == 2
        assert stock_series.json()["bars"][-1]["close"] == "13.20"


def test_review_api_dates_and_indices_contract(database_url):
    client = _review_client(database_url, FakeReviewSource())
    with client:
        schema = client.app.openapi()
        dates = client.get(
            "/api/v1/market/review/dates",
            params={"start": "2026-09-15", "end": "2026-09-18"},
        )
        indices = client.get(
            "/api/v1/market/review/indices",
            params={"date": "2026-09-18", "window": 4},
        )
        context = client.get(
            "/api/v1/market/review/context",
            params={"date": "2026-09-18"},
        )
        limit_up = client.get(
            "/api/v1/market/review/limit-up",
            params={"date": "2026-09-18", "window": 2},
        )
        stock_series = client.get(
            "/api/v1/market/review/stock-series",
            params={"symbol": "000001.SZ", "date": "2026-09-18", "window": 4},
        )
    assert dates.status_code == 200
    assert dates.json()["dates"][-1]["limit_up"]["completeness"] == "presence_only"
    assert dates.json()["dates"][-1]["market_state_counts"]["status"] == "available"
    assert dates.json()["dates"][-1]["limit_up_close_count"] == 3
    assert dates.json()["dates"][-1]["limit_down_close_count"] == 5
    assert indices.status_code == 200
    assert context.status_code == 200
    assert context.json()["default_date"] == "2026-09-18"
    assert context.json()["requested_date_known"] is True
    assert context.json()["window_max"] == 120
    assert "502" in schema["paths"]["/api/v1/market/review/indices"]["get"]["responses"]
    assert limit_up.status_code == 200
    assert limit_up.json()["rows"][0]["boards_as_of_date"] is not None
    assert "502" in schema["paths"]["/api/v1/market/review/limit-up"]["get"]["responses"]
    assert stock_series.status_code == 200
    assert stock_series.json()["missing_days"] == 0
    assert "502" in schema["paths"]["/api/v1/market/review/stock-series"]["get"]["responses"]
    assert [item["symbol"] for item in indices.json()["indices"]] == [
        "000001.SH",
        "399001.SZ",
        "000300.SH",
        "000905.SH",
        "399006.SZ",
        "000688.SH",
    ]


def test_review_api_unconfigured_source_and_runtime_limits(database_url):
    settings = Settings(
        environment="test",
        database_url=database_url,
        _env_file=None,
        review={"max_range_days": 3},
    )
    app = create_app(settings)
    app.dependency_overrides[require_actor] = lambda: Actor(user_id=1)
    with TestClient(app) as client:
        unconfigured = client.get(
            "/api/v1/market/review/dates",
            params={"start": "2026-09-15", "end": "2026-09-17"},
        )
    assert unconfigured.status_code == 503
    assert unconfigured.json()["detail"]["code"] == "SOURCE_NOT_CONFIGURED"

    client = _review_client(database_url, FakeReviewSource())
    with client:
        too_wide = client.get(
            "/api/v1/market/review/dates",
            params={"start": "2025-12-31", "end": "2027-01-01"},
        )
        wrong_window = client.get(
            "/api/v1/market/review/overview",
            params={"date": "2026-09-18", "window": 0},
        )
    assert too_wide.status_code == 400
    assert too_wide.json()["detail"]["code"] == "MARKET_REVIEW_RANGE_INVALID"
    assert wrong_window.status_code == 422
    assert wrong_window.json()["detail"]["code"] == "VALIDATION_FAILED"
