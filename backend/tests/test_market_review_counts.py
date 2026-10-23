from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from research_platform.core.config import ReviewConfig, ReviewCountsConfig
from research_platform.core.database import Base
from research_platform.modules.market.market_time import MARKET_TZ
from research_platform.modules.market.review import MarketReviewService, ReviewDateCoverage
from research_platform.modules.market.review_counts import (
    COVERAGE_DERIVED,
    COVERAGE_PARTIAL,
    DailyBar,
    LimitCounts,
    SecurityMetadata,
    classify_board,
    compute_daily_counts,
    limit_price,
)
from research_platform.modules.market.review_counts_refresh import (
    ReviewCountsScheduler,
    ReviewCountsService,
)
from research_platform.modules.market.review_counts_store import SqlReviewCountsStore
from research_platform.modules.market.state_description import MarketStateLimitCounts


def metadata_for(
    *,
    codes: list[str] | None = None,
    listed: dict[str, date] | None = None,
    st: dict[str, list[tuple[date, date | None, str]]] | None = None,
) -> SecurityMetadata:
    codes = codes or ["000001.SZ", "600000.SH", "300001.SZ", "688001.SH"]
    # Default listings are far older than any test calendar, like established stocks.
    listing = {code: date(2010, 1, 4) for code in codes} if listed is None else dict(listed)
    return SecurityMetadata(
        security_by_code={code: f"sec-{code}" for code in codes},
        listed_by_code=listing,
        st_intervals=st or {},
    )


def calendar(*days: str) -> list[date]:
    return [date.fromisoformat(day) for day in days]


def test_board_classification_matches_legacy_rules():
    assert classify_board("600000.SH") == "main"
    assert classify_board("000001.SZ") == "main"
    assert classify_board("300001.SZ") == "chinext"
    assert classify_board("688001.SH") == "star"
    assert classify_board("920001.BJ") == "bse"
    assert classify_board("510300.SH") == "unknown"


def test_limit_price_rounds_half_up_to_cent():
    assert limit_price(Decimal("6.81"), Decimal("0.10"), up=True) == Decimal("7.49")
    assert limit_price(Decimal("6.81"), Decimal("0.10"), up=False) == Decimal("6.13")


def test_main_board_counts_split_raw_and_ordinary():
    day = date(2026, 10, 23)
    meta = metadata_for(codes=["600000.SH", "000001.SZ", "000002.SZ"])
    bars = [
        DailyBar("600000.SH", Decimal("11.00"), Decimal("10.00")),
        DailyBar("000001.SZ", Decimal("9.00"), Decimal("10.00")),
        DailyBar("000002.SZ", Decimal("10.30"), Decimal("10.00")),
    ]
    result = compute_daily_counts(day, bars, meta, calendar("2026-10-22", "2026-10-23"))
    assert result.limit_up_close_count == 1
    assert result.limit_down_close_count == 1
    assert result.raw_limit_up_close_count == 1
    assert result.raw_limit_down_close_count == 1
    assert result.rule_known_bar_count == 3
    assert result.coverage_status == COVERAGE_DERIVED


def test_observed_st_bars_are_excluded_from_ordinary_counts():
    day = date(2026, 10, 23)
    st_code = "600001.SH"
    meta = metadata_for(
        codes=[st_code],
        st={f"sec-{st_code}": [(date(2026, 1, 1), None, "ST")]},
    )
    bars = [DailyBar(st_code, Decimal("9.50"), Decimal("10.00"))]
    result = compute_daily_counts(day, bars, meta, calendar("2026-10-23"))
    assert result.raw_limit_down_close_count == 1
    assert result.limit_down_close_count == 0
    assert result.st_observed_bar_count == 1


def test_chinext_uses_twenty_percent_after_2020_08_24():
    meta = metadata_for(codes=["300001.SZ"])
    old_day = date(2019, 6, 3)
    old = compute_daily_counts(
        old_day,
        [DailyBar("300001.SZ", Decimal("9.00"), Decimal("10.00"))],
        meta,
        [old_day],
    )
    assert old.limit_down_close_count == 1
    new_day = date(2021, 6, 1)
    new = compute_daily_counts(
        new_day,
        [DailyBar("300001.SZ", Decimal("9.00"), Decimal("10.00"))],
        meta,
        [new_day],
    )
    assert new.limit_down_close_count == 0
    new_20 = compute_daily_counts(
        new_day,
        [DailyBar("300001.SZ", Decimal("8.00"), Decimal("10.00"))],
        meta,
        [new_day],
    )
    assert new_20.limit_down_close_count == 1


def test_bse_and_unknown_boards_are_outside_the_derived_universe():
    day = date(2026, 10, 23)
    meta = metadata_for(codes=["920001.BJ", "510300.SH"])
    bars = [
        DailyBar("920001.BJ", Decimal("7.00"), Decimal("10.00")),
        DailyBar("510300.SH", Decimal("3.00"), Decimal("3.00")),
    ]
    result = compute_daily_counts(day, bars, meta, [day])
    assert result.rule_known_bar_count == 0
    assert result.raw_limit_up_close_count == 0
    assert result.raw_limit_down_close_count == 0


def test_ipo_window_is_ordinary_excluded_but_stays_raw():
    day = date(2026, 10, 23)
    listed = date(2026, 10, 20)
    meta = metadata_for(codes=["600002.SH"], listed={"600002.SH": listed})
    days = calendar("2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23")
    bars = [DailyBar("600002.SH", Decimal("11.00"), Decimal("10.00"))]
    result = compute_daily_counts(day, bars, meta, days)
    assert result.ipo_window_bar_count == 1
    assert result.raw_limit_up_close_count == 1
    assert result.limit_up_close_count == 0


def test_established_listing_before_a_truncated_calendar_stays_ordinary():
    day = date(2026, 10, 23)
    meta = metadata_for(codes=["600000.SH"], listed={"600000.SH": date(2010, 1, 4)})
    days = calendar("2026-10-22", "2026-10-23")
    result = compute_daily_counts(
        day,
        [DailyBar("600000.SH", Decimal("11.00"), Decimal("10.00"))],
        meta,
        days,
    )
    assert result.ipo_window_bar_count == 0
    assert result.limit_up_close_count == 1
    assert result.coverage_status == COVERAGE_DERIVED


def test_missing_listing_date_is_unknown_and_marks_partial():
    day = date(2026, 10, 23)
    meta = metadata_for(codes=["600003.SH"], listed={})
    result = compute_daily_counts(
        day,
        [DailyBar("600003.SH", Decimal("11.00"), Decimal("10.00"))],
        meta,
        [day],
    )
    assert result.raw_limit_up_close_count == 1
    assert result.limit_up_close_count == 0
    assert result.ipo_window_bar_count == 0
    assert result.coverage_status == COVERAGE_PARTIAL


def test_recent_listing_before_the_calendar_start_is_unknown_and_not_counted():
    day = date(2026, 10, 23)
    meta = metadata_for(codes=["600004.SH"], listed={"600004.SH": date(2026, 10, 20)})
    days = calendar("2026-10-22", "2026-10-23")
    result = compute_daily_counts(
        day,
        [DailyBar("600004.SH", Decimal("11.00"), Decimal("10.00"))],
        meta,
        days,
    )
    assert result.raw_limit_up_close_count == 1
    assert result.limit_up_close_count == 0
    assert result.coverage_status == COVERAGE_PARTIAL


def test_unverified_identity_is_not_counted_and_marks_partial_coverage():
    day = date(2026, 10, 23)
    meta = metadata_for(codes=["600000.SH"])
    bars = [DailyBar("000009.SZ", Decimal("11.00"), Decimal("10.00"))]
    result = compute_daily_counts(day, bars, meta, [day])
    assert result.raw_limit_up_close_count == 0
    assert result.coverage_status == COVERAGE_PARTIAL


def test_sql_store_upserts_and_reads_back():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    store = SqlReviewCountsStore(sessionmaker(engine, expire_on_commit=False))
    first = LimitCounts(
        trading_day=date(2026, 10, 23),
        limit_up_close_count=80,
        limit_down_close_count=9,
        raw_limit_up_close_count=82,
        raw_limit_down_close_count=9,
        rule_known_bar_count=5200,
        st_observed_bar_count=190,
        ipo_window_bar_count=3,
    )
    assert store.upsert([first]) == 1
    assert store.latest_trading_day() == date(2026, 10, 23)
    updated = LimitCounts(
        trading_day=date(2026, 10, 23),
        limit_up_close_count=81,
        limit_down_close_count=10,
        raw_limit_up_close_count=83,
        raw_limit_down_close_count=10,
        rule_known_bar_count=5201,
        st_observed_bar_count=190,
        ipo_window_bar_count=3,
    )
    assert store.upsert([updated]) == 1
    loaded = store.counts(date(2026, 10, 20), date(2026, 10, 24))
    assert loaded[date(2026, 10, 23)].limit_up_close_count == 81
    engine.dispose()


def test_sql_store_keeps_the_better_row_when_a_stale_upsert_arrives():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    store = SqlReviewCountsStore(sessionmaker(engine, expire_on_commit=False))
    day = date(2026, 10, 23)
    complete = LimitCounts(
        trading_day=day,
        limit_up_close_count=2,
        limit_down_close_count=0,
        raw_limit_up_close_count=2,
        raw_limit_down_close_count=0,
        rule_known_bar_count=2,
        st_observed_bar_count=0,
        ipo_window_bar_count=0,
        coverage_status=COVERAGE_DERIVED,
    )
    stale = LimitCounts(
        trading_day=day,
        limit_up_close_count=1,
        limit_down_close_count=0,
        raw_limit_up_close_count=1,
        raw_limit_down_close_count=0,
        rule_known_bar_count=1,
        st_observed_bar_count=0,
        ipo_window_bar_count=0,
        coverage_status=COVERAGE_DERIVED,
    )
    store.upsert([complete])
    store.upsert([stale])
    loaded = store.counts(day, day)[day]
    assert loaded.rule_known_bar_count == 2
    assert loaded.limit_up_close_count == 2
    engine.dispose()


def test_sql_store_keeps_verified_coverage_when_a_partial_upsert_arrives():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    store = SqlReviewCountsStore(sessionmaker(engine, expire_on_commit=False))
    day = date(2026, 10, 23)
    complete = LimitCounts(
        trading_day=day,
        limit_up_close_count=2,
        limit_down_close_count=0,
        raw_limit_up_close_count=2,
        raw_limit_down_close_count=0,
        rule_known_bar_count=2,
        st_observed_bar_count=0,
        ipo_window_bar_count=0,
        coverage_status=COVERAGE_DERIVED,
    )
    partial = LimitCounts(
        trading_day=day,
        limit_up_close_count=3,
        limit_down_close_count=0,
        raw_limit_up_close_count=3,
        raw_limit_down_close_count=0,
        rule_known_bar_count=3,
        st_observed_bar_count=0,
        ipo_window_bar_count=0,
        coverage_status=COVERAGE_PARTIAL,
    )
    store.upsert([complete])
    store.upsert([partial])
    loaded = store.counts(day, day)[day]
    assert loaded.coverage_status == COVERAGE_DERIVED
    assert loaded.limit_up_close_count == 2
    engine.dispose()


class FakeCountsSource:
    def __init__(self, days: list[date], bars: dict[date, list[DailyBar]] | None = None) -> None:
        self.days = days
        self.bars = bars or {}
        self.meta = metadata_for()

    def trading_days(self, start: date, end: date) -> list[date]:
        return [day for day in self.days if start <= day <= end]

    def daily_bars(self, trading_day: date) -> list[DailyBar]:
        return self.bars.get(trading_day, [])

    def security_metadata(self) -> SecurityMetadata:
        return self.meta


class MemoryCountsStore:
    def __init__(self) -> None:
        self.rows: dict[date, LimitCounts] = {}

    def counts(self, start: date, end: date) -> dict[date, LimitCounts]:
        return {day: row for day, row in self.rows.items() if start <= day <= end}

    def latest_trading_day(self) -> date | None:
        return max(self.rows) if self.rows else None

    def upsert(self, counts: list[LimitCounts]) -> int:
        for item in counts:
            self.rows[item.trading_day] = item
        return len(counts)


def test_refresh_service_backfills_and_is_idempotent():
    days = [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
    bars = {day: [DailyBar("600000.SH", Decimal("11.00"), Decimal("10.00"))] for day in days}
    store = MemoryCountsStore()
    service = ReviewCountsService(
        FakeCountsSource(days, bars),
        store,
        ReviewCountsConfig(backfill_days=4),
        lookback_days=400,
    )
    result = service.refresh(as_of=date(2026, 10, 23))
    assert result.trading_days == tuple(days)
    assert store.latest_trading_day() == date(2026, 10, 23)
    assert all(row.limit_up_close_count == 1 for row in store.rows.values())
    service.refresh(as_of=date(2026, 10, 23))
    assert len(store.rows) == 4


def test_scheduler_refreshes_again_after_the_interval():
    days = [date(2026, 10, 23)]
    bars = {days[0]: [DailyBar("600000.SH", Decimal("11.00"), Decimal("10.00"))]}
    store = MemoryCountsStore()
    service = ReviewCountsService(
        FakeCountsSource(days, bars),
        store,
        ReviewCountsConfig(backfill_days=1),
    )
    clock = [datetime(2026, 10, 23, 15, 0, tzinfo=MARKET_TZ)]
    scheduler = ReviewCountsScheduler(
        service,
        ReviewCountsConfig(backfill_days=1, after_close_hour=15, after_close_minute=30),
        now=lambda: clock[0],
    )
    assert scheduler.due() is False
    clock[0] = clock[0].replace(hour=15, minute=45)
    assert scheduler.run_if_due() is True
    assert store.latest_trading_day() == date(2026, 10, 23)
    # Source rows and security metadata may still change; the same window is
    # recomputed on the next interval rather than trusting the first batch.
    assert scheduler.due() is False
    clock[0] = clock[0].replace(hour=18, minute=0)
    assert scheduler.due() is True


def test_scheduler_catches_up_missing_days_on_a_weekend():
    days = [date(2026, 10, 22), date(2026, 10, 23)]
    bars = {day: [DailyBar("600000.SH", Decimal("11.00"), Decimal("10.00"))] for day in days}
    store = MemoryCountsStore()
    service = ReviewCountsService(
        FakeCountsSource(days, bars),
        store,
        ReviewCountsConfig(backfill_days=2),
    )
    scheduler = ReviewCountsScheduler(
        service,
        ReviewCountsConfig(backfill_days=2, after_close_hour=15, after_close_minute=30),
        now=lambda: datetime(2026, 10, 24, 10, 0, tzinfo=MARKET_TZ),
    )
    assert scheduler.due() is True
    assert scheduler.run_if_due() is True
    assert store.latest_trading_day() == date(2026, 10, 23)


def test_refresh_before_close_never_derives_today():
    days = [date(2026, 10, 22), date(2026, 10, 23)]
    bars = {day: [DailyBar("600000.SH", Decimal("11.00"), Decimal("10.00"))] for day in days}
    store = MemoryCountsStore()
    service = ReviewCountsService(
        FakeCountsSource(days, bars),
        store,
        ReviewCountsConfig(backfill_days=2),
    )
    result = service.refresh(now=datetime(2026, 10, 23, 10, 0, tzinfo=MARKET_TZ))
    assert result.trading_days == (date(2026, 10, 22),)
    assert store.latest_trading_day() == date(2026, 10, 22)


def test_scheduler_retries_an_incomplete_day_after_the_interval():
    days = [date(2026, 10, 23)]
    bars = {days[0]: [DailyBar("600000.SH", Decimal("11.00"), Decimal("10.00"))]}
    store = MemoryCountsStore()
    store.rows[days[0]] = LimitCounts(
        trading_day=days[0],
        limit_up_close_count=0,
        limit_down_close_count=0,
        raw_limit_up_close_count=0,
        raw_limit_down_close_count=0,
        rule_known_bar_count=1,
        st_observed_bar_count=0,
        ipo_window_bar_count=0,
        coverage_status="PARTIAL_IDENTITY",
    )
    service = ReviewCountsService(
        FakeCountsSource(days, bars),
        store,
        ReviewCountsConfig(backfill_days=1),
    )
    scheduler = ReviewCountsScheduler(
        service,
        ReviewCountsConfig(backfill_days=1, after_close_hour=15, after_close_minute=30),
        now=lambda: datetime(2026, 10, 23, 18, 0, tzinfo=MARKET_TZ),
    )
    assert scheduler.due() is True
    assert scheduler.run_if_due() is True
    refreshed = store.rows[days[0]]
    assert refreshed.coverage_status == COVERAGE_DERIVED
    assert refreshed.limit_up_close_count == 1
    assert scheduler.due() is False


def test_refresh_keeps_the_previous_result_when_source_rows_regress():
    day = date(2026, 10, 23)
    store = MemoryCountsStore()
    store.rows[day] = LimitCounts(
        trading_day=day,
        limit_up_close_count=2,
        limit_down_close_count=0,
        raw_limit_up_close_count=2,
        raw_limit_down_close_count=0,
        rule_known_bar_count=2,
        st_observed_bar_count=0,
        ipo_window_bar_count=0,
        coverage_status=COVERAGE_DERIVED,
    )
    service = ReviewCountsService(
        FakeCountsSource(
            [day],
            {day: [DailyBar("600000.SH", Decimal("11.00"), Decimal("10.00"))]},
        ),
        store,
        ReviewCountsConfig(backfill_days=1),
    )
    result = service.refresh(as_of=day, now=datetime(2026, 10, 23, 18, 0, tzinfo=MARKET_TZ))
    assert result.skipped_days == (day,)
    assert store.rows[day].limit_up_close_count == 2
    assert store.rows[day].rule_known_bar_count == 2


class FakeDailyCountsStore:
    def __init__(self, rows: dict[date, LimitCounts]) -> None:
        self.rows = rows

    def counts(self, start: date, end: date) -> dict[date, LimitCounts]:
        return {day: row for day, row in self.rows.items() if start <= day <= end}

    def latest_trading_day(self) -> date | None:
        return max(self.rows) if self.rows else None

    def upsert(self, counts: list[LimitCounts]) -> int:
        return 0


class ReviewSourceStub:
    def __init__(self) -> None:
        self.days = [date(2026, 10, 19), date(2026, 10, 20)]

    def trading_days(self, start: date, end: date) -> list[date]:
        return [day for day in self.days if start <= day <= end]

    def calendar_bounds(self, end: date) -> tuple[date | None, date | None]:
        return self.days[0], self.days[-1]

    def latest_trading_day(self, end: date) -> date | None:
        return self.days[-1]

    def latest_limit_up_date(self, end: date) -> date | None:
        return self.days[-1]

    def latest_review_date(self, end: date) -> date | None:
        return self.days[-1]

    def trading_day_neighbours(
        self, trading_day: date, end: date
    ) -> tuple[date | None, date | None]:
        return None, None

    def daily_coverage(self, start: date, end: date) -> list[ReviewDateCoverage]:
        return [
            ReviewDateCoverage(
                trading_day=day,
                limit_up_rows=1,
                market_wide_rows=1,
                shanghai_rows=1,
                shenzhen_rows=1,
                csi300_rows=1,
                csi500_rows=1,
            )
            for day in self.days
            if start <= day <= end
        ]


def test_dates_merge_platform_counts_for_days_missing_from_frozen_delivery():
    frozen = {
        date(2026, 10, 19): MarketStateLimitCounts(
            trading_day=date(2026, 10, 19),
            limit_up_close_count=47,
            limit_down_close_count=24,
            broken_board_count=None,
            broken_board_rate_pct=None,
            coverage_status="VERIFIED_UNIVERSE",
        )
    }
    derived = {
        date(2026, 10, 20): LimitCounts(
            trading_day=date(2026, 10, 20),
            limit_up_close_count=55,
            limit_down_close_count=7,
            raw_limit_up_close_count=55,
            raw_limit_down_close_count=7,
            rule_known_bar_count=5200,
            st_observed_bar_count=190,
            ipo_window_bar_count=2,
        )
    }

    class FrozenCounts:
        def limit_counts(self, start: date, end: date):
            return {day: row for day, row in frozen.items() if start <= day <= end}

    service = MarketReviewService(
        ReviewSourceStub(),
        ReviewConfig(),
        market_state_counts=FrozenCounts(),
        daily_counts=FakeDailyCountsStore(derived),
    )
    dates = service.dates(date(2026, 10, 19), date(2026, 10, 20))
    by_day = {row.date: row for row in dates.dates}
    assert by_day[date(2026, 10, 19)].limit_up_close_count == 47
    assert by_day[date(2026, 10, 19)].market_state_coverage_status == "VERIFIED_UNIVERSE"
    assert by_day[date(2026, 10, 20)].limit_up_close_count == 55
    assert by_day[date(2026, 10, 20)].market_state_coverage_status == COVERAGE_DERIVED
    assert any(issue.code == "market_state_counts_unverified" for issue in dates.issues)


def test_dates_without_frozen_configuration_still_use_platform_counts():
    derived = {
        date(2026, 10, 20): LimitCounts(
            trading_day=date(2026, 10, 20),
            limit_up_close_count=55,
            limit_down_close_count=7,
            raw_limit_up_close_count=55,
            raw_limit_down_close_count=7,
            rule_known_bar_count=5200,
            st_observed_bar_count=190,
            ipo_window_bar_count=2,
        )
    }
    service = MarketReviewService(
        ReviewSourceStub(),
        ReviewConfig(),
        daily_counts=FakeDailyCountsStore(derived),
    )
    dates = service.dates(date(2026, 10, 20), date(2026, 10, 20))
    assert dates.dates[0].limit_up_close_count == 55
    assert not any(issue.code == "market_state_counts_not_configured" for issue in dates.issues)
