"""Cross-market Sina snapshots and venue daily-history endpoints."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from research_platform.core.errors import DomainError
from research_platform.core.logging import log_event
from research_platform.core.upstream import UpstreamClient

from .global_types import (
    GLOBAL_INSTRUMENTS,
    GlobalBar,
    GlobalInstrument,
    GlobalQuote,
    change_percent,
)
from .parsing import finite_decimal, optional_decimal, parse_day

PROVIDER = "sina"
QUOTE_URL = "https://hq.sinajs.cn/list"
US_HISTORY_URL = (
    "https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var%20t=/US_MinKService.getDailyK"
)
FUTURES_HISTORY_URL = (
    "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
    "var%20t=/GlobalFuturesService.getGlobalFuturesDailyKLine"
)
HEADERS = {"Referer": "https://finance.sina.com.cn/"}

_US_HISTORY_SYMBOLS = {
    "nasdaq": ".IXIC",
    "dow": ".DJI",
    "phlx_semiconductor": ".SOX",
}
_FUTURES_HISTORY_SYMBOLS = {"gold": "GC", "wti": "CL"}
_JSONP = re.compile(r"var\s+t=\((.*)\);?\s*$", re.DOTALL)


class SinaGlobalSource:
    provider = PROVIDER

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def quotes(self) -> dict[str, GlobalQuote]:
        text = self._client.get_text(
            provider=PROVIDER,
            url=f"{QUOTE_URL}=" + ",".join(item.sina_symbol for item in GLOBAL_INSTRUMENTS),
            headers=HEADERS,
            encoding="gbk",
        )
        records = _records(text)
        result: dict[str, GlobalQuote] = {}
        last_error: DomainError | None = None
        for instrument in GLOBAL_INSTRUMENTS:
            raw = records.get(instrument.sina_symbol)
            if not raw:
                continue
            try:
                result[instrument.key] = _quote(instrument, raw)
            except DomainError as error:
                last_error = error
                log_event(
                    "market.global_quote_instrument_degraded",
                    level=logging.ERROR
                    if error.code == "MARKET_SOURCE_BAD_RESPONSE"
                    else logging.WARNING,
                    provider=PROVIDER,
                    instrument=instrument.key,
                    reason=error.code,
                )
        if not result:
            if last_error is not None and last_error.code == "MARKET_SOURCE_BAD_RESPONSE":
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        return result

    def history(self, instrument: GlobalInstrument, window: int) -> list[GlobalBar]:
        us_symbol = _US_HISTORY_SYMBOLS.get(instrument.key)
        if us_symbol is not None:
            text = self._client.get_text(
                provider=PROVIDER,
                url=US_HISTORY_URL,
                params={"symbol": us_symbol, "___qn": "3"},
                headers=HEADERS,
            )
            rows = _jsonp_rows(text)
            return _history_rows(rows, window, "d", "o", "h", "l", "c")

        futures_symbol = _FUTURES_HISTORY_SYMBOLS.get(instrument.key)
        if futures_symbol is not None:
            text = self._client.get_text(
                provider=PROVIDER,
                url=FUTURES_HISTORY_URL,
                params={"symbol": futures_symbol},
                headers=HEADERS,
            )
            rows = _jsonp_rows(text)
            return _history_rows(rows, window, "date", "open", "high", "low", "close")
        raise DomainError("MARKET_DATA_UNAVAILABLE")


def _records(text: str) -> dict[str, str]:
    records: dict[str, str] = {}
    marker = "hq_str_"
    for line in text.splitlines():
        start = line.find(marker)
        if start < 0:
            continue
        start += len(marker)
        equals = line.find('="', start)
        if equals < 0:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        end = line.find('"', equals + 2)
        if end < 0:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        records[line[start:equals]] = line[equals + 2 : end]
    if not records:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    return records


def _quote(instrument: GlobalInstrument, raw: str) -> GlobalQuote:
    fields = raw.split(",")
    symbol = instrument.sina_symbol
    if symbol.startswith("gb_"):
        return _us_quote(fields)
    if symbol.startswith("b_"):
        return _regional_index_quote(fields, instrument.quote_timezone_hours)
    if symbol.startswith("hf_"):
        return _futures_quote(fields)
    return _china_quote(fields)


def _us_quote(fields: list[str]) -> GlobalQuote:
    if len(fields) < 27:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    price = _positive_price(fields[1])
    previous_close = optional_decimal(fields[26])
    change = optional_decimal(fields[4])
    if previous_close is None and change is not None:
        previous_close = price - change
    return GlobalQuote(
        price=price,
        previous_close=previous_close,
        open=optional_decimal(fields[5]),
        high=optional_decimal(fields[6]),
        low=optional_decimal(fields[7]),
        change=change,
        change_pct=optional_decimal(fields[2]),
        quote_time=_local_datetime(fields[3], 8, "%Y-%m-%d %H:%M:%S"),
        provider=PROVIDER,
    )


def _regional_index_quote(fields: list[str], offset_hours: int) -> GlobalQuote:
    if len(fields) < 12:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    price = _positive_price(fields[1])
    change = optional_decimal(fields[2])
    return GlobalQuote(
        price=price,
        previous_close=optional_decimal(fields[9]),
        open=None,
        high=optional_decimal(fields[10]),
        low=optional_decimal(fields[11]),
        change=change,
        change_pct=optional_decimal(fields[3]),
        quote_time=_local_datetime(
            f"{fields[6]} {fields[5]}",
            offset_hours,
            "%Y-%m-%d %H:%M:%S",
        ),
        provider=PROVIDER,
    )


def _china_quote(fields: list[str]) -> GlobalQuote:
    if len(fields) < 32:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    price = _positive_price(fields[3])
    previous_close = optional_decimal(fields[2])
    return GlobalQuote(
        price=price,
        previous_close=previous_close,
        open=optional_decimal(fields[1]),
        high=optional_decimal(fields[4]),
        low=optional_decimal(fields[5]),
        change=price - previous_close if previous_close is not None else None,
        change_pct=change_percent(price, previous_close),
        quote_time=_local_datetime(
            f"{fields[30]} {fields[31]}",
            8,
            "%Y-%m-%d %H:%M:%S",
        ),
        provider=PROVIDER,
    )


def _futures_quote(fields: list[str]) -> GlobalQuote:
    if len(fields) < 14:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    price = _positive_price(fields[0])
    previous_close = optional_decimal(fields[7])
    return GlobalQuote(
        price=price,
        previous_close=previous_close,
        open=optional_decimal(fields[8]),
        high=optional_decimal(fields[4]),
        low=optional_decimal(fields[5]),
        change=price - previous_close if previous_close is not None else None,
        change_pct=change_percent(price, previous_close),
        quote_time=_local_datetime(
            f"{fields[12]} {fields[6]}",
            8,
            "%Y-%m-%d %H:%M:%S",
        ),
        provider=PROVIDER,
    )


def _local_datetime(value: str, offset_hours: int, fmt: str) -> datetime | None:
    try:
        local = datetime.strptime(value.strip(), fmt)
    except ValueError:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
    return local.replace(tzinfo=timezone(timedelta(hours=offset_hours)))


def _positive_price(value: object) -> Decimal:
    price = optional_decimal(value)
    if price is None or price <= 0:
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    return price


def _jsonp_rows(text: str) -> list[dict]:
    match = _JSONP.search(text)
    if match is None:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
    if payload is None:
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    if not isinstance(payload, list) or not payload:
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    if not all(isinstance(row, dict) for row in payload):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    return payload


def _history_rows(
    rows: list[dict],
    window: int,
    day_key: str,
    open_key: str,
    high_key: str,
    low_key: str,
    close_key: str,
) -> list[GlobalBar]:
    result: list[GlobalBar] = []
    previous_close = None
    previous_day = None
    invalid_rows = 0
    for row in rows[-(window + 1) :]:
        try:
            trading_day = parse_day(row[day_key], "%Y-%m-%d")
            open_price = finite_decimal(row[open_key])
            high = finite_decimal(row[high_key])
            low = finite_decimal(row[low_key])
            close = finite_decimal(row[close_key])
        except (DomainError, KeyError):
            invalid_rows += 1
            previous_close = None
            continue
        if previous_day is not None and trading_day <= previous_day:
            invalid_rows += 1
            previous_close = None
            continue
        if high < low or not (low <= open_price <= high and low <= close <= high):
            invalid_rows += 1
            previous_close = None
            continue
        result.append(
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
    if not result:
        if invalid_rows:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    return result[-window:]
