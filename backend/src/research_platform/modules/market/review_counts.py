"""Pure per-day limit-up/down derivation from read-only daily bars.

The verified frozen market-state delivery is produced by the legacy batch and
stops at its build date. This module derives the same *ordinary* counts for
recent trading days from the source database so the review calendar keeps
working: SH/SZ universe only, exchange-rounded limit prices, and ordinary counts
that exclude observed ST/*ST bars and the first five listing trading days.

The rule table mirrors ``server/data/boardRules.ts`` (the legacy authority) and
is kept here as a small, tested port rather than an implicit approximation.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

CHINEXT_20PCT_EFFECTIVE_DATE = date(2020, 8, 24)
IPO_NO_LIMIT_TRADING_DAYS = 5
# A listing this far before a truncated calendar cannot be inside a 5-day window.
_IPO_CALENDAR_MARGIN_DAYS = 14
COVERAGE_DERIVED = "DERIVED_UNIVERSE"
COVERAGE_PARTIAL = "PARTIAL_IDENTITY"
PLATFORM_SOURCE = "source_db_daily"

BoardCategory = Literal["main", "chinext", "star", "bse", "unknown"]
StStatus = Literal["NORMAL", "ST", "UNKNOWN"]

ONE_CENT = Decimal("0.01")


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    close: Decimal | None
    pre_close: Decimal | None


@dataclass(frozen=True)
class LimitCounts:
    """One derived trading day; raw counts stay for audit next to ordinary ones."""

    trading_day: date
    limit_up_close_count: int
    limit_down_close_count: int
    raw_limit_up_close_count: int
    raw_limit_down_close_count: int
    rule_known_bar_count: int
    st_observed_bar_count: int
    ipo_window_bar_count: int
    coverage_status: str = COVERAGE_DERIVED
    source: str = PLATFORM_SOURCE


@dataclass(frozen=True)
class SecurityMetadata:
    """Identity, listing date and observed ST intervals keyed by legacy code."""

    security_by_code: dict[str, str]
    listed_by_code: dict[str, date]
    st_intervals: dict[str, tuple[tuple[date, date | None, str], ...]]


class MarketCountsSource(Protocol):
    def trading_days(self, start: date, end: date) -> list[date]: ...

    def daily_bars(self, trading_day: date) -> list[DailyBar]: ...

    def security_metadata(self) -> SecurityMetadata: ...


def classify_board(symbol: str) -> BoardCategory:
    code = symbol.split(".", 1)[0]
    if len(code) != 6 or not code.isdigit():
        return "unknown"
    if code.startswith(("300", "301")):
        return "chinext"
    if code.startswith(("688", "689")):
        return "star"
    if code.startswith(("920", "43", "83", "87", "88", "4", "8")):
        return "bse"
    if code.startswith(("60", "000", "001", "002", "003")):
        return "main"
    return "unknown"


def limit_ratio(board: BoardCategory, trading_day: date, st: bool) -> Decimal | None:
    if board == "main":
        return Decimal("0.05") if st else Decimal("0.10")
    if board in ("chinext", "star"):
        return (
            Decimal("0.20")
            if board == "star" or trading_day >= CHINEXT_20PCT_EFFECTIVE_DATE
            else Decimal("0.10")
        )
    if board == "bse":
        return Decimal("0.30")
    return None


def limit_price(pre_close: Decimal, ratio: Decimal, *, up: bool) -> Decimal:
    raw = pre_close * (Decimal(1) + ratio) if up else pre_close * (Decimal(1) - ratio)
    return raw.quantize(ONE_CENT, rounding=ROUND_HALF_UP)


def st_status_at(metadata: SecurityMetadata, symbol: str, trading_day: date) -> StStatus:
    security_id = metadata.security_by_code.get(symbol)
    if security_id is None:
        return "UNKNOWN"
    for start, end, value in metadata.st_intervals.get(security_id, ()):
        if value not in ("ST", "*ST"):
            continue
        if trading_day < start:
            continue
        if end is not None and trading_day > end:
            continue
        return "ST"
    return "NORMAL"


def ipo_window_status(
    calendar: list[date], metadata: SecurityMetadata, symbol: str, trading_day: date
) -> bool | None:
    """Whether the bar is inside the no-limit IPO window; None means unknown.

    A listing date before the supplied calendar cannot be aged exactly. Treat it
    as old when the gap leaves no room for the five-day window; otherwise report
    unknown instead of silently counting it as an established stock.
    """

    listed = metadata.listed_by_code.get(symbol)
    if listed is None or listed > trading_day or not calendar:
        return None
    index_day = bisect.bisect_left(calendar, trading_day)
    if listed < calendar[0]:
        if (calendar[0] - listed).days > _IPO_CALENDAR_MARGIN_DAYS:
            return False
        return False if index_day >= IPO_NO_LIMIT_TRADING_DAYS else None
    index_listed = bisect.bisect_left(calendar, listed)
    if index_listed >= len(calendar) or calendar[index_listed] != listed:
        return None
    age = index_day - index_listed + 1
    return 1 <= age <= IPO_NO_LIMIT_TRADING_DAYS


def compute_daily_counts(
    trading_day: date,
    bars: list[DailyBar],
    metadata: SecurityMetadata,
    calendar: list[date],
) -> LimitCounts:
    ordinary_up = ordinary_down = 0
    raw_up = raw_down = 0
    rule_known = st_observed = ipo_window = 0
    listing_unknown = 0
    for bar in bars:
        board = classify_board(bar.symbol)
        # The derived universe is SH/SZ only; BJ stays outside like the frozen delivery.
        if board in ("bse", "unknown"):
            continue
        status = st_status_at(metadata, bar.symbol, trading_day)
        ratio = limit_ratio(board, trading_day, status == "ST")
        if status == "UNKNOWN" or ratio is None:
            continue
        if bar.close is None or bar.pre_close is None or bar.pre_close <= 0:
            continue
        if bar.close <= 0:
            continue
        rule_known += 1
        st = status == "ST"
        if st:
            st_observed += 1
        in_ipo_window = ipo_window_status(calendar, metadata, bar.symbol, trading_day)
        if in_ipo_window is None:
            listing_unknown += 1
        elif in_ipo_window:
            ipo_window += 1
        up = limit_price(bar.pre_close, ratio, up=True)
        down = limit_price(bar.pre_close, ratio, up=False)
        is_up = bar.close == up
        is_down = bar.close == down
        if is_up:
            raw_up += 1
        if is_down:
            raw_down += 1
        if not st and in_ipo_window is False:
            if is_up:
                ordinary_up += 1
            if is_down:
                ordinary_down += 1
    counted = [bar for bar in bars if classify_board(bar.symbol) not in ("bse", "unknown")]
    verified = all(bar.symbol in metadata.security_by_code for bar in counted)
    complete = verified and listing_unknown == 0
    return LimitCounts(
        trading_day=trading_day,
        limit_up_close_count=ordinary_up,
        limit_down_close_count=ordinary_down,
        raw_limit_up_close_count=raw_up,
        raw_limit_down_close_count=raw_down,
        rule_known_bar_count=rule_known,
        st_observed_bar_count=st_observed,
        ipo_window_bar_count=ipo_window,
        coverage_status=COVERAGE_DERIVED if complete else COVERAGE_PARTIAL,
    )
