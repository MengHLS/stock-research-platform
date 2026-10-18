"""Tencent real-time quote snapshot: prices, limits and the live clock.

``qt.gtimg.cn/q=<code>` returns one ``~``-separated record per requested symbol
(GBK text). Verified on 2026-10-16 for SSE, SZSE, BSE, STAR, ETF and index codes:

- field 1 name, 2 code, 3 last price, 4 previous close, 5 open, 6 volume,
  30 ``YYYYMMDDHHMMSS`` quote time, 32 change pct, 33/34 day high/low,
  35 ``price/volume/amount``, 37 amount in 万元, 38 turnover pct,
  47/48 limit-up/limit-down (``-1`` for instruments without limits, e.g. indices);
- volume is 手 for stocks/ETFs and 股-like units for indices, so it is **not**
  exposed as shares here: the snapshot's own volume field is unit-ambiguous
  across instruments and only ``amount`` (元, field 35) reconciles. Intraday bars
  are the place where a share-denominated volume is published;
- the record is missing for a code Tencent does not know: that is
  ``MARKET_DATA_UNAVAILABLE``, not an empty quote.
"""

from __future__ import annotations

from decimal import Decimal

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .market_time import MARKET_TZ
from .parsing import finite_decimal, optional_decimal
from .symbols import Symbol

PROVIDER = "tencent"
QUOTE_URL = "https://qt.gtimg.cn/q="
HEADERS = {"Referer": "https://gu.qq.com/"}
NO_LIMIT = "-1"


class Quote:
    __slots__ = (
        "symbol",
        "name",
        "price",
        "previous_close",
        "open",
        "high",
        "low",
        "quote_time",
        "change_pct",
        "volume_lots",
        "amount",
        "turnover_pct",
        "limit_up",
        "limit_down",
    )

    def __init__(self, **values) -> None:
        for name in self.__slots__:
            setattr(self, name, values.get(name))


class TencentQuoteSource:
    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def quote(self, symbol: Symbol) -> Quote:
        text = self._client.get_text(
            provider=PROVIDER,
            url=f"{QUOTE_URL}{symbol.qq_code}",
            headers=HEADERS,
            encoding="gbk",
        )
        record = _record(text, symbol)
        fields = record.split("~")
        if len(fields) < 39:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        try:
            quote_time = _parse_quote_time(fields[30])
            price = _decimal(fields[3])
            previous_close = _decimal(fields[4])
            turnover = _optional_decimal(fields[38])
            parts = fields[35].split("/")
            if len(parts) != 3:
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            amount = _decimal(parts[2])
            volume_lots = _decimal(parts[1])
            limit_up = _limit(fields[47] if len(fields) > 47 else NO_LIMIT)
            limit_down = _limit(fields[48] if len(fields) > 48 else NO_LIMIT)
        except ValueError:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
        return Quote(
            symbol=symbol.display,
            name=fields[1],
            price=price,
            previous_close=previous_close,
            open=_optional_decimal(fields[5]),
            high=_optional_decimal(fields[33]),
            low=_optional_decimal(fields[34]),
            quote_time=quote_time,
            change_pct=_optional_decimal(fields[32]),
            volume_lots=volume_lots,
            amount=amount,
            turnover_pct=turnover,
            limit_up=limit_up,
            limit_down=limit_down,
        )


def _record(text: str, symbol: Symbol) -> str:
    """Extract the ``v_<code>="..."`` payload; an unknown code has no record."""
    marker = f'v_{symbol.qq_code}="'
    start = text.find(marker)
    if start < 0:
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    start += len(marker)
    end = text.find('"', start)
    if end < 0:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    return text[start:end]


def _parse_quote_time(value: str):
    if len(value) != 14 or not value.isdigit():
        raise ValueError("quote time must be YYYYMMDDHHMMSS")
    from datetime import UTC, datetime

    # Provider sends exchange-local time; the public contract is UTC.
    local = datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=MARKET_TZ)
    return local.astimezone(UTC)


def _decimal(value: str) -> Decimal:
    return finite_decimal(value)


def _optional_decimal(value: str) -> Decimal | None:
    return optional_decimal(value)


def _limit(value: str) -> Decimal | None:
    if not value or value == NO_LIMIT:
        return None
    return finite_decimal(value)
