"""Historical market-review reads and calculations.

The module separates a replaceable read-only source from pure assessment logic.
Legacy tables are one adapter, not the public domain model. Missing rows remain
missing: this service never converts an unknown board count or absent source day
into a reassuring zero.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, DecimalException
from typing import Literal, Protocol

from research_platform.core.cache import TTLCache
from research_platform.core.config import ReviewConfig
from research_platform.core.errors import DomainError

from .market_time import exchange_now
from .review_schemas import (
    CoverageRead,
    IndexCoverageRead,
    LadderRead,
    LadderRowRead,
    LimitUpReviewDayRead,
    LimitUpReviewRowRead,
    MarketHistoryRowRead,
    MaxBoardStockRead,
    OverviewIndexRead,
    ReviewContextRead,
    ReviewDateRead,
    ReviewDatesRead,
    ReviewIndexBarRead,
    ReviewIndexSeriesRead,
    ReviewIndicesRead,
    ReviewIssueRead,
    ReviewLimitUpRead,
    ReviewMethodologyRead,
    ReviewOverviewRead,
    ReviewStockBarRead,
    ReviewStockSeriesRead,
    ReviewSummaryRead,
    ThemeCountRead,
)
from .symbols import parse_symbol

REVIEW_VERSION = "market-review-v1"
CALENDAR_PROVIDER = "legacy.index_daily"
INDEX_NAMES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
}
INDEX_SYMBOLS = tuple(INDEX_NAMES)
SOURCE_ISSUES = (
    ReviewIssueRead(
        code="source_presence_only",
        scope="source",
        message="覆盖状态由源中是否存在行判定，不能证明完整采集。",
    ),
    ReviewIssueRead(
        code="calendar_derived_from_index_daily",
        scope="calendar",
        message="交易日由旧库 index_daily 日期推导，不是独立维护的交易日历。",
    ),
)


@dataclass(frozen=True)
class LimitUpRecord:
    trading_day: date
    symbol: str
    name: str
    sector: str | None
    limit_up_time: str | None


@dataclass(frozen=True)
class StockQuote:
    trading_day: date
    symbol: str
    change_pct: Decimal | None
    one_word_board: bool | None


@dataclass(frozen=True)
class StockBar:
    trading_day: date
    symbol: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    previous_close: Decimal | None


@dataclass(frozen=True)
class MarketWideRow:
    trading_day: date
    turnover_100m_cny: Decimal | None
    margin_balance_100m_cny: Decimal | None


@dataclass(frozen=True)
class IndexBar:
    trading_day: date
    symbol: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    amount_source: Decimal | None
    volume_source: Decimal | None


@dataclass(frozen=True)
class ReviewDateCoverage:
    trading_day: date
    limit_up_rows: int
    market_wide_rows: int
    shanghai_rows: int
    shenzhen_rows: int
    csi300_rows: int
    csi500_rows: int


class ReviewSource(Protocol):
    def trading_days(self, start: date, end: date) -> list[date]: ...

    def calendar_bounds(self, end: date) -> tuple[date | None, date | None]: ...

    def latest_trading_day(self, end: date) -> date | None: ...

    def latest_limit_up_date(self, end: date) -> date | None: ...

    def latest_review_date(self, end: date) -> date | None: ...

    def trading_day_neighbours(
        self, trading_day: date, end: date
    ) -> tuple[date | None, date | None]: ...

    def daily_coverage(self, start: date, end: date) -> list[ReviewDateCoverage]: ...

    def limit_up_records(self, start: date, end: date) -> list[LimitUpRecord]: ...

    def stock_quotes(self, trading_day: date, symbols: list[str]) -> list[StockQuote]: ...

    def stock_quotes_range(
        self,
        start: date,
        end: date,
        symbols: list[str],
    ) -> list[StockQuote]: ...

    def stock_bars_range(
        self,
        start: date,
        end: date,
        symbol: str,
    ) -> list[StockBar]: ...

    def market_wide_rows(self, start: date, end: date) -> list[MarketWideRow]: ...

    def index_rows(self, start: date, end: date, symbols: list[str]) -> list[IndexBar]: ...


class ReviewSourceDataError(ValueError):
    """A source row cannot be interpreted under the reviewed schema."""


@dataclass(frozen=True)
class _BoardResult:
    boards: int | None
    exhausted: bool


@dataclass(frozen=True)
class _LimitUpDayResult:
    day: date
    previous_day: date | None
    current: dict[str, LimitUpRecord]
    previous: dict[str, LimitUpRecord]
    assessments: dict[str, _BoardResult]
    broken_records: list[tuple[LimitUpRecord, _BoardResult]]
    summary: ReviewSummaryRead
    quote_symbols: list[str]


class MarketReviewService:
    def __init__(
        self,
        source: ReviewSource | None,
        config: ReviewConfig,
        *,
        cache: TTLCache | None = None,
    ) -> None:
        self._source = source
        self._config = config
        self._cache = cache if cache is not None else TTLCache()

    @property
    def cache(self) -> TTLCache:
        return self._cache

    def dates(self, start: date, end: date) -> ReviewDatesRead:
        self._validate_range(start, end)
        key = ("market-review-dates", REVIEW_VERSION, start, end)
        return self._cache.get_or_create(
            key,
            self._config.cache_seconds,
            lambda: self._dates(start, end),
        )

    def context(
        self,
        requested_date: date | None = None,
        *,
        as_of: date | None = None,
    ) -> ReviewContextRead:
        as_of_date = as_of or exchange_now().date()
        key = ("market-review-context", REVIEW_VERSION, requested_date, as_of_date)
        return self._cache.get_or_create(
            key,
            self._config.cache_seconds,
            lambda: self._context(requested_date, as_of_date),
        )

    def overview(self, trading_day: date, window: int) -> ReviewOverviewRead:
        self._validate_window(window)
        key = ("market-review-overview", REVIEW_VERSION, trading_day, window)
        return self._cache.get_or_create(
            key,
            self._config.cache_seconds,
            lambda: self._overview(trading_day, window),
        )

    def indices(self, trading_day: date, window: int) -> ReviewIndicesRead:
        self._validate_window(window)
        key = ("market-review-indices", REVIEW_VERSION, trading_day, window)
        return self._cache.get_or_create(
            key,
            self._config.cache_seconds,
            lambda: self._indices(trading_day, window),
        )

    def limit_up(self, trading_day: date, window: int) -> ReviewLimitUpRead:
        self._validate_window(window)
        key = ("market-review-limit-up", REVIEW_VERSION, trading_day, window)
        return self._cache.get_or_create(
            key,
            self._config.cache_seconds,
            lambda: self._limit_up(trading_day, window),
        )

    def stock_series(self, symbol: str, trading_day: date, window: int) -> ReviewStockSeriesRead:
        self._validate_window(window)
        canonical = parse_symbol(symbol).display
        key = ("market-review-stock-series", REVIEW_VERSION, canonical, trading_day, window)
        try:
            return self._cache.get_or_create(
                key,
                self._config.cache_seconds,
                lambda: self._stock_series(canonical, trading_day, window),
            )
        except DecimalException:
            raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None

    def _source_or_fail(self) -> ReviewSource:
        if self._source is None:
            raise DomainError("SOURCE_NOT_CONFIGURED")
        return self._source

    def _validate_range(self, start: date, end: date) -> None:
        if start > end or (end - start).days + 1 > self._config.max_range_days:
            raise DomainError("MARKET_REVIEW_RANGE_INVALID")

    def _validate_window(self, window: int) -> None:
        if window < 1 or window > self._config.max_window:
            raise DomainError("MARKET_REVIEW_RANGE_INVALID")

    def _dates(self, start: date, end: date) -> ReviewDatesRead:
        source = self._source_or_fail()
        coverage_rows = sorted(
            source.daily_coverage(start, end),
            key=lambda row: _as_date(row.trading_day),
        )
        rows: list[ReviewDateRead] = []
        for coverage in coverage_rows:
            day = _as_date(coverage.trading_day)
            index_coverage = IndexCoverageRead(
                shanghai=_coverage(coverage.shanghai_rows),
                shenzhen=_coverage(coverage.shenzhen_rows),
                csi300=_coverage(coverage.csi300_rows),
                csi500=_coverage(coverage.csi500_rows),
            )
            rows.append(
                ReviewDateRead(
                    date=day,
                    limit_up=_coverage(coverage.limit_up_rows),
                    market_wide=_coverage(coverage.market_wide_rows),
                    indices=index_coverage,
                )
            )
        return ReviewDatesRead(
            start=start,
            end=end,
            dates=rows,
            issues=list(SOURCE_ISSUES),
        )

    def _context(
        self,
        requested_date: date | None,
        as_of: date,
    ) -> ReviewContextRead:
        source = self._source_or_fail()
        calendar_start, calendar_end = source.calendar_bounds(as_of)
        latest_calendar = source.latest_trading_day(as_of)
        latest_limit_up = source.latest_limit_up_date(as_of)
        default_date = source.latest_review_date(as_of)
        default_reason = "none"
        if default_date is not None:
            default_reason = "latest_limit_up"
        if default_date is None and latest_calendar is not None:
            default_date = latest_calendar
            default_reason = "latest_calendar"
        focus_day = requested_date or default_date
        previous_day = None
        next_day = None
        if focus_day is not None:
            previous_day, next_day = source.trading_day_neighbours(focus_day, as_of)
        requested_known = None
        if requested_date is not None:
            requested_known = requested_date <= as_of and requested_date in self._calendar(
                source.trading_days(requested_date, requested_date)
            )
        return ReviewContextRead(
            as_of_date=as_of,
            default_date=default_date,
            default_date_reason=default_reason,
            requested_date=requested_date,
            requested_date_known=requested_known,
            calendar_start=calendar_start,
            calendar_end=calendar_end,
            latest_limit_up_date=latest_limit_up,
            previous_trading_day=previous_day,
            next_trading_day=next_day,
            window_max=self._config.max_window,
        )

    def _overview(self, requested_day: date, window: int) -> ReviewOverviewRead:
        source = self._source_or_fail()
        lookback_start = requested_day - timedelta(days=self._config.lookback_days)
        calendar_days = self._calendar(source.trading_days(lookback_start, requested_day))
        if requested_day not in calendar_days:
            raise DomainError("MARKET_REVIEW_DATE_UNAVAILABLE")
        target_index = calendar_days.index(requested_day)
        history_dates = calendar_days[max(0, target_index - window + 1) : target_index + 1]
        records_all = self._normalize_records(
            source.limit_up_records(calendar_days[0], requested_day)
        )
        records_by_day: dict[date, dict[str, LimitUpRecord]] = defaultdict(dict)
        for record in records_all:
            records_by_day[record.trading_day][record.symbol] = record
        history_start = history_dates[0]
        market = self._market_rows(source.market_wide_rows(history_start, requested_day))
        previous_day = calendar_days[target_index - 1] if target_index > 0 else None
        issues = list(SOURCE_ISSUES)
        current = records_by_day[requested_day]
        previous = records_by_day[previous_day] if previous_day else {}
        quote_count = 0

        if not current:
            issues.append(_issue("target_limit_up_missing", requested_day))
            summary = ReviewSummaryRead(assessment="missing")
            ladder = LadderRead(connection=[], first=[], broken=[], unknown=[])
            themes: list[ThemeCountRead] = []
        else:
            if previous_day is None or not previous:
                issues.append(
                    _issue(
                        "previous_limit_up_missing",
                        previous_day or requested_day,
                    )
                )
            assessments = {
                symbol: self._boards_at(
                    symbol,
                    requested_day,
                    calendar_days,
                    records_by_day,
                )
                for symbol in current
            }
            if any(result.exhausted for result in assessments.values()):
                issues.append(_issue("board_history_exhausted", requested_day))
            if any(result.exhausted for result in assessments.values()):
                issues.append(_issue("history_window_truncated", requested_day))
            ladder_rows = [
                self._ladder_row(
                    record,
                    assessments[record.symbol].boards,
                    requested_day,
                    {},
                )
                for record in current.values()
            ]
            broken_rows: list[LadderRowRead] = []
            if previous:
                for symbol, record in previous.items():
                    if symbol in current:
                        continue
                    result = self._boards_at(
                        symbol,
                        previous_day,
                        calendar_days,
                        records_by_day,
                    )
                    if result.exhausted:
                        issues.append(_issue("board_history_exhausted", previous_day))
                    if result.exhausted:
                        issues.append(_issue("history_window_truncated", previous_day))
                    broken_kind = (
                        None
                        if result.boards is None
                        else ("connection" if result.boards >= 2 else "first")
                    )
                    broken_rows.append(
                        self._ladder_row(
                            record,
                            result.boards,
                            previous_day,
                            {},
                            broken_kind=broken_kind,
                        )
                    )
            quote_symbols = sorted({*current, *(row.symbol for row in broken_rows)})
            quotes = self._quotes(
                source.stock_quotes(requested_day, quote_symbols),
                requested_day,
            )
            quote_count = len(quotes)
            ladder_rows = [
                self._ladder_row(
                    record,
                    assessments[record.symbol].boards,
                    requested_day,
                    quotes,
                )
                for record in current.values()
            ]
            broken_rows = [
                self._ladder_row(
                    previous[row.symbol],
                    row.boards,
                    previous_day,
                    quotes,
                    broken_kind=row.broken_kind,
                )
                for row in broken_rows
            ]
            if len(quotes) < len(quote_symbols):
                issues.append(_issue("stock_quote_missing", requested_day))
            ladder = _ladder(ladder_rows, broken_rows)
            themes = _themes(current.values())
            summary = _summary(
                current,
                assessments,
                broken_rows,
                previous_known=bool(previous),
            )

        market_quote = market.get(requested_day)
        history = [
            self._history_row(
                day,
                calendar_days,
                records_by_day,
                market,
            )
            for day in history_dates
        ]
        index_bars = self._index_rows(
            source.index_rows(previous_day or requested_day, requested_day, list(INDEX_SYMBOLS))
        )
        overview_indices: list[OverviewIndexRead] = []
        for symbol, name in INDEX_NAMES.items():
            current_bars = [bar for bar in index_bars[symbol] if bar.trading_day == requested_day]
            previous_bar = (
                next(
                    (
                        bar
                        for bar in reversed(index_bars[symbol])
                        if previous_day and bar.trading_day == previous_day
                    ),
                    None,
                )
                if previous_day
                else None
            )
            bar = current_bars[0] if current_bars else None
            overview_indices.append(
                OverviewIndexRead(
                    symbol=symbol,
                    name=name,
                    coverage=_coverage(1 if bar else 0),
                    close=bar.close if bar else None,
                    change_pct=(
                        _change_pct(bar.close, previous_bar.close) if bar and previous_bar else None
                    ),
                )
            )
        if any(item.coverage.status == "missing" for item in overview_indices):
            issues.append(_issue("index_history_missing", requested_day))

        return ReviewOverviewRead(
            date=requested_day,
            previous_trading_day=previous_day,
            window_requested=window,
            window_actual=len(history_dates),
            coverage={
                "limit_up": _coverage(len(current)),
                "quotes": _coverage(quote_count),
                "market_wide": _coverage(1 if market_quote else 0),
                "indices": _coverage(
                    sum(item.coverage.status == "available" for item in overview_indices)
                ),
            },
            summary=summary,
            ladder=ladder,
            themes=themes,
            market_wide=_coverage(1 if market_quote else 0),
            turnover_100m_cny=(market_quote.turnover_100m_cny if market_quote else None),
            margin_balance_100m_cny=(
                market_quote.margin_balance_100m_cny if market_quote else None
            ),
            indices=overview_indices,
            history=history,
            issues=_dedupe_issues(issues),
            methodology=ReviewMethodologyRead(),
        )

    def _indices(self, requested_day: date, window: int) -> ReviewIndicesRead:
        source = self._source_or_fail()
        lookback_start = requested_day - timedelta(days=self._config.lookback_days)
        calendar_days = self._calendar(source.trading_days(lookback_start, requested_day))
        if requested_day not in calendar_days:
            raise DomainError("MARKET_REVIEW_DATE_UNAVAILABLE")
        target_index = calendar_days.index(requested_day)
        history_dates = calendar_days[max(0, target_index - window + 1) : target_index + 1]
        first_history_index = calendar_days.index(history_dates[0])
        # MA20 needs the current day plus 19 prior trading days, even when the
        # caller only requests one visible bar.
        query_start = calendar_days[max(0, first_history_index - 19)]
        rows = self._index_rows(source.index_rows(query_start, requested_day, list(INDEX_SYMBOLS)))
        series: list[ReviewIndexSeriesRead] = []
        for symbol, name in INDEX_NAMES.items():
            by_day = {bar.trading_day: bar for bar in rows[symbol]}
            bars: list[ReviewIndexBarRead] = []
            for day in history_dates:
                position = calendar_days.index(day)
                bar = by_day.get(day)
                previous = by_day.get(calendar_days[position - 1]) if position > 0 else None
                bars.append(
                    ReviewIndexBarRead(
                        date=day,
                        open=bar.open if bar else None,
                        high=bar.high if bar else None,
                        low=bar.low if bar else None,
                        close=bar.close if bar else None,
                        change_pct=(
                            _change_pct(bar.close, previous.close) if bar and previous else None
                        ),
                        ma5=_moving_average(calendar_days, by_day, day, 5),
                        ma20=_moving_average(calendar_days, by_day, day, 20),
                        amount_source=bar.amount_source if bar else None,
                        volume_source=bar.volume_source if bar else None,
                    )
                )
            missing_days = sum(bar.close is None for bar in bars)
            series.append(
                ReviewIndexSeriesRead(
                    symbol=symbol,
                    name=name,
                    coverage=_coverage(len(bars) - missing_days),
                    missing_days=missing_days,
                    bars=bars,
                )
            )
        issues = list(SOURCE_ISSUES)
        if any(item.missing_days for item in series):
            issues.append(_issue("index_history_missing", requested_day))
        return ReviewIndicesRead(
            date=requested_day,
            window_requested=window,
            window_actual=len(history_dates),
            history_dates=history_dates,
            indices=series,
            issues=issues,
            methodology=ReviewMethodologyRead(),
        )

    def _stock_series(
        self,
        symbol: str,
        requested_day: date,
        window: int,
    ) -> ReviewStockSeriesRead:
        source = self._source_or_fail()
        lookback_start = requested_day - timedelta(days=self._config.lookback_days)
        calendar_days = self._calendar(source.trading_days(lookback_start, requested_day))
        if requested_day not in calendar_days:
            raise DomainError("MARKET_REVIEW_DATE_UNAVAILABLE")

        target_index = calendar_days.index(requested_day)
        history_dates = calendar_days[max(0, target_index - window + 1) : target_index + 1]
        first_history_index = calendar_days.index(history_dates[0])
        query_start = calendar_days[max(0, first_history_index - 19)]
        by_day = self._stock_bars(
            source.stock_bars_range(query_start, requested_day, symbol),
            symbol,
        )
        bars: list[ReviewStockBarRead] = []
        for day in history_dates:
            bar = by_day.get(day)
            bars.append(
                ReviewStockBarRead(
                    date=day,
                    open=bar.open if bar else None,
                    high=bar.high if bar else None,
                    low=bar.low if bar else None,
                    close=bar.close if bar else None,
                    change_pct=(_change_pct(bar.close, bar.previous_close) if bar else None),
                    ma5=_stock_moving_average(calendar_days, by_day, day, 5),
                    ma20=_stock_moving_average(calendar_days, by_day, day, 20),
                )
            )
        missing_days = sum(
            any(value is None for value in (bar.open, bar.high, bar.low, bar.close)) for bar in bars
        )
        issues = list(SOURCE_ISSUES)
        if missing_days:
            issues.append(_issue("stock_history_missing", requested_day))
        return ReviewStockSeriesRead(
            symbol=symbol,
            window_requested=window,
            window_actual=len(history_dates),
            coverage=_coverage(sum(day in by_day for day in history_dates)),
            missing_days=missing_days,
            bars=bars,
            issues=issues,
            methodology=ReviewMethodologyRead(),
        )

    def _limit_up(self, requested_day: date, window: int) -> ReviewLimitUpRead:
        source = self._source_or_fail()
        lookback_start = requested_day - timedelta(days=self._config.lookback_days)
        calendar_days = self._calendar(source.trading_days(lookback_start, requested_day))
        if requested_day not in calendar_days:
            raise DomainError("MARKET_REVIEW_DATE_UNAVAILABLE")

        target_index = calendar_days.index(requested_day)
        history_dates = calendar_days[max(0, target_index - window + 1) : target_index + 1]
        records_all = self._normalize_records(
            source.limit_up_records(calendar_days[0], requested_day)
        )
        records_by_day: dict[date, dict[str, LimitUpRecord]] = defaultdict(dict)
        for record in records_all:
            records_by_day[record.trading_day][record.symbol] = record

        day_results: list[_LimitUpDayResult] = []
        expected_quotes: dict[date, set[str]] = {}
        all_quote_symbols: set[str] = set()
        issues = list(SOURCE_ISSUES)
        for day in history_dates:
            current = records_by_day.get(day, {})
            day_index = calendar_days.index(day)
            previous_day = calendar_days[day_index - 1] if day_index > 0 else None
            previous = records_by_day.get(previous_day, {}) if previous_day else {}
            if not current:
                day_results.append(
                    _LimitUpDayResult(
                        day=day,
                        previous_day=previous_day,
                        current={},
                        previous=previous,
                        assessments={},
                        broken_records=[],
                        summary=ReviewSummaryRead(assessment="missing"),
                        quote_symbols=[],
                    )
                )
                if day == requested_day:
                    issues.append(_issue("target_limit_up_missing", day))
                continue

            if previous_day is None or not previous:
                issues.append(_issue("previous_limit_up_missing", previous_day or day))
            assessments = {
                symbol: self._boards_at(symbol, day, calendar_days, records_by_day)
                for symbol in current
            }
            if any(result.exhausted for result in assessments.values()):
                issues.append(_issue("board_history_exhausted", day))
                issues.append(_issue("history_window_truncated", day))

            broken_records: list[tuple[LimitUpRecord, _BoardResult]] = []
            for symbol, record in previous.items():
                if symbol in current:
                    continue
                result = self._boards_at(symbol, previous_day, calendar_days, records_by_day)
                if result.exhausted:
                    issues.append(_issue("board_history_exhausted", previous_day))
                    issues.append(_issue("history_window_truncated", previous_day))
                broken_records.append((record, result))

            quote_symbols = sorted({*current, *(record.symbol for record, _ in broken_records)})
            broken_ladder_rows = [
                self._ladder_row(
                    record,
                    result.boards,
                    previous_day,
                    {},
                    broken_kind=(
                        None
                        if result.boards is None
                        else "connection"
                        if result.boards >= 2
                        else "first"
                    ),
                )
                for record, result in broken_records
            ]
            summary = _summary(
                current,
                assessments,
                broken_ladder_rows,
                previous_known=bool(previous),
            )
            expected_quotes[day] = set(quote_symbols)
            all_quote_symbols.update(quote_symbols)
            day_results.append(
                _LimitUpDayResult(
                    day=day,
                    previous_day=previous_day,
                    current=current,
                    previous=previous,
                    assessments=assessments,
                    broken_records=broken_records,
                    summary=summary,
                    quote_symbols=quote_symbols,
                )
            )

        quotes_by_day = (
            self._quotes_by_day(
                source.stock_quotes_range(
                    history_dates[0],
                    requested_day,
                    sorted(all_quote_symbols),
                ),
                expected_quotes,
            )
            if all_quote_symbols
            else {}
        )
        rows: list[LimitUpReviewRowRead] = []
        days: list[LimitUpReviewDayRead] = []
        for result in day_results:
            quotes = quotes_by_day.get(result.day, {})
            if len(quotes) < len(result.quote_symbols):
                issues.append(_issue("stock_quote_missing", result.day))
            if result.current:
                rows.extend(
                    self._limit_up_row(
                        result.day,
                        record,
                        result.assessments[record.symbol].boards,
                        result.day,
                        quotes,
                        status="limit_up",
                    )
                    for record in result.current.values()
                )
                rows.extend(
                    self._limit_up_row(
                        result.day,
                        record,
                        board_result.boards,
                        result.previous_day,
                        quotes,
                        status="broken",
                        broken_kind=(
                            None
                            if board_result.boards is None
                            else "connection"
                            if board_result.boards >= 2
                            else "first"
                        ),
                    )
                    for record, board_result in result.broken_records
                )
            days.append(
                LimitUpReviewDayRead(
                    date=result.day,
                    assessment=result.summary.assessment,
                    total_limit_up=result.summary.total_limit_up,
                    broken_count=result.summary.broken_count,
                    limit_up=_coverage(len(result.current)),
                )
            )

        rows.sort(
            key=lambda row: (
                row.date,
                row.boards if row.boards is not None else -1,
                row.limit_up_time or "",
                row.symbol,
            ),
            reverse=True,
        )
        return ReviewLimitUpRead(
            date=requested_day,
            window_requested=window,
            window_actual=len(history_dates),
            rows=rows,
            days=days,
            issues=_dedupe_issues(issues),
            methodology=ReviewMethodologyRead(),
        )

    def _calendar(self, rows: list[date]) -> list[date]:
        try:
            return sorted({_as_date(row) for row in rows})
        except ReviewSourceDataError:
            raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None

    def _normalize_records(self, rows: list[LimitUpRecord]) -> list[LimitUpRecord]:
        by_key: dict[tuple[date, str], LimitUpRecord] = {}
        for row in rows:
            try:
                day = _as_date(row.trading_day)
                symbol = _canonical_source_symbol(row.symbol)
            except (DomainError, ReviewSourceDataError):
                raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None
            normalized = LimitUpRecord(
                trading_day=day,
                symbol=symbol,
                name=(row.name or "").strip(),
                sector=(row.sector or "").strip() or None,
                limit_up_time=(row.limit_up_time or "").strip() or None,
            )
            key = (day, symbol)
            existing = by_key.get(key)
            if existing is None or _time_key(normalized) < _time_key(existing):
                by_key[key] = normalized
        return sorted(by_key.values(), key=lambda row: (row.trading_day, row.symbol))

    def _market_rows(self, rows: list[MarketWideRow]) -> dict[date, MarketWideRow]:
        result: dict[date, MarketWideRow] = {}
        try:
            for row in rows:
                day = _as_date(row.trading_day)
                _finite_optional(row.turnover_100m_cny)
                _finite_optional(row.margin_balance_100m_cny)
                if day in result:
                    raise ReviewSourceDataError("duplicate market row")
                result[day] = row
        except ReviewSourceDataError:
            raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None
        return result

    def _index_rows(self, rows: list[IndexBar]) -> dict[str, list[IndexBar]]:
        grouped: dict[str, dict[date, IndexBar]] = defaultdict(dict)
        try:
            for row in rows:
                symbol = _canonical_source_symbol(row.symbol)
                day = _as_date(row.trading_day)
                for value in (
                    row.open,
                    row.high,
                    row.low,
                    row.close,
                    row.amount_source,
                    row.volume_source,
                ):
                    _finite_optional(value)
                if day in grouped[symbol]:
                    raise ReviewSourceDataError("duplicate index row")
                grouped[symbol][day] = row
        except (DomainError, ReviewSourceDataError):
            raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None
        return {
            symbol: [grouped[symbol][day] for day in sorted(grouped[symbol])]
            for symbol in INDEX_SYMBOLS
        }

    def _stock_bars(self, rows: list[StockBar], expected_symbol: str) -> dict[date, StockBar]:
        result: dict[date, StockBar] = {}
        try:
            for row in rows:
                day = _as_date(row.trading_day)
                symbol = _canonical_source_symbol(row.symbol)
                if symbol != expected_symbol:
                    raise ReviewSourceDataError("unexpected stock symbol")
                for value in (row.open, row.high, row.low, row.close, row.previous_close):
                    _finite_optional(value)
                    if value is not None and value <= 0:
                        raise ReviewSourceDataError("non-positive stock price")
                if all(value is not None for value in (row.open, row.high, row.low, row.close)):
                    if not (row.low <= row.open <= row.high and row.low <= row.close <= row.high):
                        raise ReviewSourceDataError("inconsistent stock OHLC")
                if day in result:
                    raise ReviewSourceDataError("duplicate stock bar")
                result[day] = row
        except (DomainError, ReviewSourceDataError):
            raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None
        return result

    def _quotes(self, rows: list[StockQuote], expected_day: date) -> dict[str, StockQuote]:
        result: dict[str, StockQuote] = {}
        try:
            for row in rows:
                if _as_date(row.trading_day) != expected_day:
                    raise ReviewSourceDataError("quote day mismatch")
                symbol = _canonical_source_symbol(row.symbol)
                if symbol in result:
                    raise ReviewSourceDataError("duplicate quote")
                _finite_optional(row.change_pct)
                result[symbol] = StockQuote(
                    trading_day=row.trading_day,
                    symbol=symbol,
                    change_pct=(
                        row.change_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        if row.change_pct is not None
                        else None
                    ),
                    one_word_board=row.one_word_board,
                )
        except (DomainError, ReviewSourceDataError):
            raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None
        return result

    def _quotes_by_day(
        self,
        rows: list[StockQuote],
        expected: dict[date, set[str]],
    ) -> dict[date, dict[str, StockQuote]]:
        result: dict[date, dict[str, StockQuote]] = defaultdict(dict)
        try:
            for row in rows:
                day = _as_date(row.trading_day)
                symbol = _canonical_source_symbol(row.symbol)
                if symbol not in expected.get(day, set()):
                    continue
                if symbol in result[day]:
                    raise ReviewSourceDataError("duplicate quote")
                _finite_optional(row.change_pct)
                result[day][symbol] = StockQuote(
                    trading_day=day,
                    symbol=symbol,
                    change_pct=(
                        row.change_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        if row.change_pct is not None
                        else None
                    ),
                    one_word_board=row.one_word_board,
                )
        except (DomainError, ReviewSourceDataError):
            raise DomainError("MARKET_REVIEW_SOURCE_BAD_DATA") from None
        return result

    def _boards_at(
        self,
        symbol: str,
        target_day: date,
        calendar_days: list[date],
        records_by_day: dict[date, dict[str, LimitUpRecord]],
    ) -> _BoardResult:
        start = calendar_days.index(target_day)
        boards = 1
        cursor = start - 1
        while cursor >= 0 and symbol in records_by_day.get(calendar_days[cursor], {}):
            boards += 1
            cursor -= 1
        if cursor < 0:
            return _BoardResult(boards=None, exhausted=True)
        gap_day = calendar_days[cursor]
        if not records_by_day.get(gap_day):
            return _BoardResult(boards=None, exhausted=False)
        return _BoardResult(boards=boards, exhausted=False)

    def _ladder_row(
        self,
        record: LimitUpRecord,
        boards: int | None,
        boards_as_of_date: date,
        quotes: dict[str, StockQuote],
        *,
        broken_kind: str | None = None,
    ) -> LadderRowRead:
        quote = quotes.get(record.symbol)
        return LadderRowRead(
            symbol=record.symbol,
            name=record.name or record.symbol,
            sector=record.sector or "未知",
            limit_up_time=record.limit_up_time or "",
            boards=boards,
            boards_as_of_date=boards_as_of_date,
            broken_kind=broken_kind,
            change_pct=quote.change_pct if quote else None,
            one_word_board=quote.one_word_board if quote else None,
        )

    def _limit_up_row(
        self,
        observation_day: date,
        record: LimitUpRecord,
        boards: int | None,
        boards_as_of_date: date,
        quotes: dict[str, StockQuote],
        *,
        status: Literal["limit_up", "broken"],
        broken_kind: str | None = None,
    ) -> LimitUpReviewRowRead:
        quote = quotes.get(record.symbol)
        return LimitUpReviewRowRead(
            date=observation_day,
            symbol=record.symbol,
            name=record.name or record.symbol,
            sector=record.sector or "未知",
            status=status,
            boards=boards,
            boards_as_of_date=boards_as_of_date,
            limit_up_time=record.limit_up_time or "",
            limit_up_time_as_of_date=boards_as_of_date,
            broken_kind=broken_kind,
            change_pct=quote.change_pct if quote else None,
            one_word_board=quote.one_word_board if quote and status == "limit_up" else None,
        )

    def _history_row(
        self,
        day: date,
        calendar_days: list[date],
        records_by_day: dict[date, dict[str, LimitUpRecord]],
        market: dict[date, MarketWideRow],
    ) -> MarketHistoryRowRead:
        records = records_by_day.get(day, {})
        market_row = market.get(day)
        if not records:
            return MarketHistoryRowRead(
                date=day,
                assessment="missing",
                unknown_fields=[
                    *([] if market_row else ["market_wide"]),
                    "limit_up",
                ],
                turnover_100m_cny=(market_row.turnover_100m_cny if market_row else None),
                margin_balance_100m_cny=(
                    market_row.margin_balance_100m_cny if market_row else None
                ),
            )
        assessments = {
            symbol: self._boards_at(symbol, day, calendar_days, records_by_day)
            for symbol in records
        }
        position = calendar_days.index(day)
        previous_day = calendar_days[position - 1] if position > 0 else None
        previous_records = records_by_day.get(previous_day, {}) if previous_day else {}
        broken_rows: list[LadderRowRead] = []
        for symbol, record in previous_records.items():
            if symbol in records:
                continue
            result = self._boards_at(symbol, previous_day, calendar_days, records_by_day)
            broken_rows.append(
                self._ladder_row(
                    record,
                    result.boards,
                    previous_day,
                    {},
                    broken_kind=(
                        None
                        if result.boards is None
                        else "connection"
                        if result.boards >= 2
                        else "first"
                    ),
                )
            )
        summary = _summary(
            records,
            assessments,
            broken_rows,
            previous_known=bool(previous_records),
        )
        max_board_stocks: list[MaxBoardStockRead] = []
        if summary.max_board is not None:
            max_board_stocks = [
                MaxBoardStockRead(symbol=record.symbol, name=record.name or record.symbol)
                for symbol, record in records.items()
                if assessments[symbol].boards == summary.max_board
            ]
            max_board_stocks.sort(key=lambda item: item.symbol)
        unknown_fields: list[str] = []
        for field_name, value in (
            ("first_board_count", summary.first_board_count),
            ("connection_board_count", summary.connection_board_count),
            ("max_board", summary.max_board),
            ("three_board_plus_count", summary.three_board_plus_count),
            ("emotion_score", summary.emotion_score),
            ("broken_count", summary.broken_count),
            ("broken_connection_count", summary.broken_connection_count),
        ):
            if value is None:
                unknown_fields.append(field_name)
        if not market_row:
            unknown_fields.append("market_wide")
        return MarketHistoryRowRead(
            date=day,
            assessment=summary.assessment,
            total_limit_up=summary.total_limit_up,
            first_board_count=summary.first_board_count,
            connection_board_count=summary.connection_board_count,
            max_board=summary.max_board,
            three_board_plus_count=summary.three_board_plus_count,
            emotion_score=summary.emotion_score,
            broken_count=summary.broken_count,
            broken_connection_count=summary.broken_connection_count,
            max_board_stock_total=(
                len(max_board_stocks) if summary.max_board is not None else None
            ),
            max_board_stocks=max_board_stocks[:12],
            unknown_fields=unknown_fields,
            turnover_100m_cny=(market_row.turnover_100m_cny if market_row else None),
            margin_balance_100m_cny=(market_row.margin_balance_100m_cny if market_row else None),
            themes=_themes(records.values()),
        )


def _coverage(row_count: int) -> CoverageRead:
    return CoverageRead(
        status="available" if row_count > 0 else "missing",
        row_count=row_count,
    )


def _issue(code: str, scope: date) -> ReviewIssueRead:
    messages = {
        "target_limit_up_missing": "目标交易日没有涨停记录，无法区分真实零值与缺失。",
        "previous_limit_up_missing": "前一交易日没有涨停记录，无法确认首板或断板。",
        "board_history_exhausted": "连板链触及查询起点，相关板数保持未知。",
        "stock_quote_missing": "部分梯队股票缺少目标日行情，涨跌幅或一字板保持未知。",
        "history_window_truncated": "历史查询窗口不足以确认部分连板高度。",
        "index_history_missing": "目标历史窗口内存在缺失的指数日线。",
        "stock_history_missing": "目标历史窗口内存在缺失的个股日线。",
    }
    return ReviewIssueRead(code=code, scope=scope.isoformat(), message=messages[code])


def _dedupe_issues(issues: list[ReviewIssueRead]) -> list[ReviewIssueRead]:
    result: list[ReviewIssueRead] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (issue.code, issue.scope)
        if key not in seen:
            result.append(issue)
            seen.add(key)
    return result


def _time_key(record: LimitUpRecord) -> str:
    return record.limit_up_time or "99:99:99"


def _ladder(
    current_rows: list[LadderRowRead],
    broken_rows: list[LadderRowRead],
) -> LadderRead:
    known_current = [row for row in current_rows if row.boards is not None]
    return LadderRead(
        connection=sorted(
            (row for row in known_current if row.boards >= 2),
            key=_row_sort_key,
        ),
        first=sorted(
            (row for row in known_current if row.boards == 1),
            key=_row_sort_key,
        ),
        broken=sorted(broken_rows, key=_row_sort_key),
        unknown=sorted(
            (row for row in current_rows if row.boards is None),
            key=_row_sort_key,
        ),
    )


def _row_sort_key(row: LadderRowRead) -> tuple[int, str, str]:
    return (-(row.boards or 0), row.limit_up_time or "99:99:99", row.symbol)


def _summary(
    records: dict[str, LimitUpRecord],
    assessments: dict[str, _BoardResult],
    broken_rows: list[LadderRowRead],
    *,
    previous_known: bool,
) -> ReviewSummaryRead:
    if not records:
        return ReviewSummaryRead(assessment="missing")
    boards = [result.boards for result in assessments.values()]
    total = len(records)
    if any(value is None for value in boards):
        return ReviewSummaryRead(
            assessment="partial",
            total_limit_up=total,
        )
    concrete = [value for value in boards if value is not None]
    connections = sum(value >= 2 for value in concrete)
    three_plus = sum(value >= 3 for value in concrete)
    max_board = max(concrete)
    broken_known = previous_known and all(row.boards is not None for row in broken_rows)
    return ReviewSummaryRead(
        assessment="available" if previous_known and broken_known else "partial",
        total_limit_up=total,
        first_board_count=total - connections,
        connection_board_count=connections,
        max_board=max_board,
        three_board_plus_count=three_plus,
        broken_count=len(broken_rows) if previous_known and broken_known else None,
        broken_connection_count=(
            sum((row.boards or 0) >= 2 for row in broken_rows) if broken_known else None
        ),
        emotion_score=_emotion_score(total, connections, max_board, three_plus),
    )


def _emotion_score(
    total_limit_up: int,
    connection_boards: int,
    max_boards: int,
    board3_plus: int,
) -> int:
    connection_ratio = Decimal(connection_boards) / Decimal(total_limit_up)
    max_score = min(Decimal(max_boards) / Decimal(10), Decimal(1))
    concentration = (
        Decimal(board3_plus) / Decimal(connection_boards) if connection_boards > 0 else Decimal(0)
    )
    value = connection_ratio * 40 + max_score * 30 + concentration * 30
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _themes(records) -> list[ThemeCountRead]:
    counts = Counter((record.sector or "未知") for record in records)
    return [
        ThemeCountRead(theme=theme, count=count)
        for theme, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _count_by_day(records: list[LimitUpRecord]) -> Counter[date]:
    return Counter(record.trading_day for record in records)


def _as_date(value: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ReviewSourceDataError("invalid date")


def _canonical_source_symbol(value: str) -> str:
    raw = str(value).strip()
    try:
        symbol = parse_symbol(raw)
    except DomainError:
        raise ReviewSourceDataError("invalid symbol") from None
    if raw != symbol.display:
        raise ReviewSourceDataError("non-canonical symbol")
    return symbol.display


def _finite_optional(value: Decimal | None) -> None:
    if value is not None and not value.is_finite():
        raise ReviewSourceDataError("non-finite decimal")


def _change_pct(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None or previous == 0:
        return None
    value = (current - previous) / previous * 100
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _moving_average(
    calendar_days: list[date],
    by_day: dict[date, IndexBar],
    day: date,
    periods: int,
) -> Decimal | None:
    position = calendar_days.index(day)
    if position + 1 < periods:
        return None
    values: list[Decimal] = []
    for current_day in calendar_days[position - periods + 1 : position + 1]:
        bar = by_day.get(current_day)
        if bar is None or bar.close is None:
            return None
        values.append(bar.close)
    return (sum(values, Decimal(0)) / Decimal(periods)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _stock_moving_average(
    calendar_days: list[date],
    by_day: dict[date, StockBar],
    day: date,
    periods: int,
) -> Decimal | None:
    position = calendar_days.index(day)
    if position + 1 < periods:
        return None
    values: list[Decimal] = []
    for current_day in calendar_days[position - periods + 1 : position + 1]:
        bar = by_day.get(current_day)
        if bar is None or bar.close is None:
            return None
        values.append(bar.close)
    return (sum(values, Decimal(0)) / Decimal(periods)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
