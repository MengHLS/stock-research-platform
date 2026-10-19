"""Yahoo Finance chart fallback for quotes and daily history."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .global_types import (
    GLOBAL_INSTRUMENTS,
    GlobalBar,
    GlobalInstrument,
    GlobalQuote,
    change_percent,
)
from .parsing import finite_decimal, optional_decimal

PROVIDER = "yahoo"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
HEADERS = {
    "Referer": "https://finance.yahoo.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


class YahooGlobalSource:
    provider = PROVIDER

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def quotes(self) -> dict[str, GlobalQuote]:
        result: dict[str, GlobalQuote] = {}
        for instrument in GLOBAL_INSTRUMENTS:
            if instrument.yahoo_symbol is None:
                continue
            try:
                chart = self._chart(instrument, "5d")
            except DomainError:
                continue
            quote = _quote(chart)
            if quote is not None:
                result[instrument.key] = quote
        if not result:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        return result

    def history(self, instrument: GlobalInstrument, window: int) -> list[GlobalBar]:
        chart = self._chart(instrument, "1y")
        return _history(chart, window)

    def _chart(self, instrument: GlobalInstrument, period: str) -> dict:
        if instrument.yahoo_symbol is None:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        symbol = quote(instrument.yahoo_symbol, safe="")
        payload = self._client.get_json(
            provider=PROVIDER,
            url=f"{CHART_URL}{symbol}",
            params={"range": period, "interval": "1d"},
            headers={**HEADERS, "Referer": f"https://finance.yahoo.com/quote/{symbol}/"},
        )
        root = _mapping(payload)
        chart = _mapping(root.get("chart"))
        if chart.get("error") is not None:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        results = chart.get("result")
        if not isinstance(results, list) or not results:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        return _mapping(results[0])


def _quote(chart: dict) -> GlobalQuote | None:
    meta = _mapping(chart.get("meta"))
    price = optional_decimal(meta.get("regularMarketPrice") or meta.get("fulldayPrice"))
    if price is None:
        return None
    change = optional_decimal(meta.get("fulldayChange") or meta.get("regularMarketChange"))
    change_pct = optional_decimal(
        meta.get("fulldayChangePercent") or meta.get("regularMarketChangePercent")
    )
    previous_close = optional_decimal(meta.get("previousClose"))
    if previous_close is None and change is not None:
        previous_close = price - change

    open_price = high = low = None
    timestamps = chart.get("timestamp")
    quote_rows = _chart_quote(chart)
    if isinstance(timestamps, list) and timestamps and quote_rows is not None:
        open_values = quote_rows.get("open")
        high_values = quote_rows.get("high")
        low_values = quote_rows.get("low")
        if all(
            isinstance(values, list) and values for values in (open_values, high_values, low_values)
        ):
            open_price = optional_decimal(open_values[-1])
            high = optional_decimal(high_values[-1])
            low = optional_decimal(low_values[-1])

    timestamp = optional_decimal(meta.get("regularMarketTime"))
    quote_time = None
    if timestamp is not None:
        try:
            quote_time = datetime.fromtimestamp(int(timestamp), tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
    return GlobalQuote(
        price=price,
        previous_close=previous_close,
        open=open_price,
        high=high,
        low=low,
        change=change,
        change_pct=change_pct,
        quote_time=quote_time,
        provider=PROVIDER,
    )


def _history(chart: dict, window: int) -> list[GlobalBar]:
    meta = _mapping(chart.get("meta"))
    offset_seconds = int(optional_decimal(meta.get("gmtoffset")) or 0)
    timestamps = chart.get("timestamp")
    quote_rows = _chart_quote(chart)
    if not isinstance(timestamps, list) or quote_rows is None:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    opens = quote_rows.get("open")
    highs = quote_rows.get("high")
    lows = quote_rows.get("low")
    closes = quote_rows.get("close")
    if not all(isinstance(values, list) for values in (opens, highs, lows, closes)):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    if not (len(timestamps) == len(opens) == len(highs) == len(lows) == len(closes)):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")

    bars: list[GlobalBar] = []
    previous_close = None
    previous_day = None
    for timestamp, open_value, high_value, low_value, close_value in zip(
        timestamps, opens, highs, lows, closes, strict=True
    ):
        if None in (open_value, high_value, low_value, close_value):
            continue
        try:
            moment = datetime.fromtimestamp(int(timestamp), tz=UTC) + timedelta(
                seconds=offset_seconds
            )
        except (OverflowError, OSError, TypeError, ValueError):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
        trading_day = moment.date()
        open_price = finite_decimal(open_value)
        high = finite_decimal(high_value)
        low = finite_decimal(low_value)
        close = finite_decimal(close_value)
        if previous_day is not None and trading_day <= previous_day:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        if high < low or not (low <= open_price <= high and low <= close <= high):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        bars.append(
            GlobalBar(
                trading_day=trading_day,
                open=open_price,
                high=high,
                low=low,
                close=close,
                change_pct=change_percent(close, previous_close),
            )
        )
        previous_close = close
        previous_day = trading_day
    if not bars:
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    return bars[-window:]


def _chart_quote(chart: dict) -> dict | None:
    indicators = _mapping(chart.get("indicators"))
    rows = indicators.get("quote")
    if not isinstance(rows, list) or not rows:
        return None
    return _mapping(rows[0])


def _mapping(value: object) -> dict:
    if not isinstance(value, dict):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    return value
