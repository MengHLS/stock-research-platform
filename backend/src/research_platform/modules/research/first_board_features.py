"""Pure T-1 price features for the first-board background classifier."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from .first_board_classifier import (
    PositionBand,
    ShortPath,
    Trend,
    position_band,
)

FEATURE_VERSION = "first-board-prefix-v1"
ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")

QualityStatus = Literal["COMPLETE", "PARTIAL", "INSUFFICIENT"]


@dataclass(frozen=True, slots=True)
class HistoricalBar:
    trading_day: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    adjustment_factor: Decimal | None


@dataclass(frozen=True, slots=True)
class BackgroundFeatures:
    position_60d_pct: Decimal | None
    position_band: PositionBand
    trend: Trend
    short_path: ShortPath
    return_5d_pct: Decimal | None
    return_20d_pct: Decimal | None
    return_60d_pct: Decimal | None
    ma_20: Decimal | None
    ma_60: Decimal | None
    quality_status: QualityStatus
    feature_reason: str | None


def compute_background_features(
    calendar_before_event: list[date],
    bars: dict[date, HistoricalBar],
) -> BackgroundFeatures:
    """Compute the same position/trend/short-path axes from T-1 and earlier.

    The caller supplies the trading calendar in ascending order, with at least
    the latest 61 sessions. Missing sessions are not forward-filled. Prices are
    multiplied by the cumulative back-adjustment factor visible on that date.
    """
    if calendar_before_event != sorted(set(calendar_before_event)):
        raise ValueError("Calendar must contain unique ascending trading days")
    if not calendar_before_event:
        return _empty("INSUFFICIENT_CALENDAR")

    adjusted = _adjusted_series(calendar_before_event, bars)
    reasons: list[str] = []
    window_days = calendar_before_event[-61:]
    if any(day not in bars for day in window_days):
        reasons.append("MISSING_DAILY_BAR")
    if any(bars[day].adjustment_factor is None for day in window_days if day in bars):
        reasons.append("MISSING_OR_UNSAFE_ADJUSTMENT_FACTOR")

    def window(n: int):
        if len(adjusted) < n:
            reasons.append(f"INSUFFICIENT_{n}D_HISTORY")
            return None
        rows = adjusted[-n:]
        if any(row is None for row in rows):
            reasons.append(f"{n}D_PRICE_OR_FACTOR_GAP")
            return None
        return [row for row in rows if row is not None]

    values60 = window(60)
    position = _position(values60, reasons) if values60 else None
    ma20_values = window(20)
    ma20 = sum((row[2] for row in ma20_values), ZERO) / Decimal(20) if ma20_values else None
    ma60 = sum((row[2] for row in values60), ZERO) / Decimal(60) if values60 else None

    def historical_return(n: int):
        rows = window(n + 1)
        return _return_pct(rows[-1][2], rows[0][2]) if rows else None

    return_5, return_20, return_60 = [historical_return(n) for n in (5, 20, 60)]
    last_close = adjusted[-1][2] if adjusted[-1] else None
    trend = _trend(last_close, ma20, ma60, return_20, reasons)
    short_path = _short_path(return_5, return_20)

    position_value = position
    band = position_band(position_value)
    quality = _quality(position_value, trend, short_path)
    if quality == "COMPLETE" and return_60 is None:
        quality = "PARTIAL"
    return BackgroundFeatures(
        position_60d_pct=position_value,
        position_band=band,
        trend=trend,
        short_path=short_path,
        return_5d_pct=return_5,
        return_20d_pct=return_20,
        return_60d_pct=return_60,
        ma_20=ma20,
        ma_60=ma60,
        quality_status=quality,
        feature_reason=";".join(dict.fromkeys(reasons)) or None,
    )


def _adjusted_series(
    calendar: list[date], bars: dict[date, HistoricalBar]
) -> list[tuple[Decimal, Decimal, Decimal] | None]:
    values: list[tuple[Decimal, Decimal, Decimal] | None] = []
    for day in calendar:
        bar = bars.get(day)
        if (
            bar is None
            or bar.high is None
            or bar.low is None
            or bar.close is None
            or bar.adjustment_factor is None
            or not all(
                value.is_finite() for value in (bar.high, bar.low, bar.close, bar.adjustment_factor)
            )
            or bar.adjustment_factor <= ZERO
        ):
            values.append(None)
            continue
        high = bar.high * bar.adjustment_factor
        low = bar.low * bar.adjustment_factor
        close = bar.close * bar.adjustment_factor
        if (
            high <= ZERO
            or low <= ZERO
            or close <= ZERO
            or high < low
            or close < low
            or close > high
        ):
            values.append(None)
            continue
        values.append((high, low, close))
    return values


def _position(
    values: list[tuple[Decimal, Decimal, Decimal]],
    reasons: list[str],
) -> Decimal | None:
    top = max(value[0] for value in values)
    bottom = min(value[1] for value in values)
    last_close = values[-1][2]
    if top <= bottom:
        reasons.append("FLAT_60D_RANGE")
        return None
    return ONE_HUNDRED * (last_close - bottom) / (top - bottom)


def _trend(
    last_close: Decimal | None,
    ma20: Decimal | None,
    ma60: Decimal | None,
    return_20: Decimal | None,
    reasons: list[str],
) -> Trend:
    if last_close is None or ma20 is None or ma60 is None or return_20 is None:
        reasons.append("TREND_WINDOW_INCOMPLETE")
        return Trend.UNKNOWN
    if last_close > ma20 >= ma60 and return_20 > ZERO:
        return Trend.UP
    if last_close < ma20 <= ma60 and return_20 < ZERO:
        return Trend.DOWN
    return Trend.SIDEWAYS


def _short_path(return_5: Decimal | None, return_20: Decimal | None) -> ShortPath:
    if return_5 is None or return_20 is None:
        return ShortPath.UNKNOWN
    if abs(return_5) <= Decimal("1") or abs(return_20) <= Decimal("2"):
        return ShortPath.NEUTRAL
    if return_20 > ZERO:
        return ShortPath.UP_CONTINUATION if return_5 > ZERO else ShortPath.UP_PULLBACK
    return ShortPath.DOWN_REBOUND if return_5 > ZERO else ShortPath.DOWN_CONTINUATION


def _quality(
    position: Decimal | None,
    trend: Trend,
    short_path: ShortPath,
) -> QualityStatus:
    known = (
        position is not None and trend is not Trend.UNKNOWN and short_path is not ShortPath.UNKNOWN
    )
    if known:
        return "COMPLETE"
    if trend is not Trend.UNKNOWN or short_path is not ShortPath.UNKNOWN or position is not None:
        return "PARTIAL"
    return "INSUFFICIENT"


def _return_pct(last: Decimal, first: Decimal) -> Decimal | None:
    if first <= ZERO:
        return None
    return ONE_HUNDRED * (last / first - Decimal(1))


def _empty(reason: str) -> BackgroundFeatures:
    return BackgroundFeatures(
        position_60d_pct=None,
        position_band=PositionBand.UNKNOWN,
        trend=Trend.UNKNOWN,
        short_path=ShortPath.UNKNOWN,
        return_5d_pct=None,
        return_20d_pct=None,
        return_60d_pct=None,
        ma_20=None,
        ma_60=None,
        quality_status="INSUFFICIENT",
        feature_reason=reason,
    )
