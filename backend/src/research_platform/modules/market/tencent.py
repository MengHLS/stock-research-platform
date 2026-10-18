"""Tencent public quote endpoints: intraday K lines and the auction trade fallback.

Endpoints (undocumented public web APIs, no key, no login):

- ``ifzq.gtimg.cn/appstock/app/kline/mkline?param=<qq_code>,<period>,,<count>``
  for minute bars;
- ``stock.gtimg.cn/data/index.php?appn=detail&action=data&c=<qq_code>&p=0`` for
  the per-trade detail of the most recent trading day (page 0 begins with the
  09:25 opening-auction trade).

Contract details verified against the 2026-10-16 session and cross-checked with
Tushare daily volume and with the bars themselves:

- bar arrays are ``[time, open, close, high, low, volume, {}, extra]``; the
  ``extra`` field is not a documented turnover figure and is deliberately not
  exposed (it does not reconcile with the daily turnover rate);
- volume is 手 (100 shares) for every board except STAR (688/689), i.e. 股;
- the 09:30 one-minute bar contains only the opening call auction, so its trades
  happened at 09:25 although it is labelled 09:30;
- at most ~800 bars are returned regardless of a larger ``count`` request, so the
  caller must not assume the requested window was honoured;
- BSE (``bj`` prefix) returns an empty bar list: no coverage, not a failure;
- the per-trade detail has no date field: only the latest session is available.
"""

from __future__ import annotations

import re

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .market_time import MARKET_TZ, parse_minute_timestamp
from .parsing import finite_decimal
from .symbols import Symbol, shares, tencent_volume_unit

PROVIDER = "tencent"
KLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
TICK_URL = "https://stock.gtimg.cn/data/index.php"
HEADERS = {"Referer": "https://gu.qq.com/"}

PERIOD_MINUTES: dict[str, int] = {"m1": 1, "m5": 5, "m15": 15, "m30": 30, "m60": 60}
MAX_BARS = 800

_TICK_LINE = re.compile(
    r'^v_detail_data_(?P<symbol>[a-z]{2}\d{6})=\[(?P<page>\d+),"(?P<body>[^"]*)"\]$'
)

# The tick detail returns one trade per ~3 seconds; page 0 always starts with the
# 09:25 auction trade. Only that record is used, so no paging is needed.
OPENING_AUCTION_CLOCK = ("09:25", "09:26")


class IntradayBar:
    __slots__ = ("start", "trading_day", "open", "high", "low", "close", "volume_shares")

    def __init__(self, start, trading_day, open_, high, low, close, volume_shares: str) -> None:
        self.start = start
        self.trading_day = trading_day
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume_shares = volume_shares


class AuctionTrade:
    """The 09:25 call-auction trade, from the per-trade detail."""

    __slots__ = ("clock", "trading_day", "price", "volume_shares", "amount")

    def __init__(self, clock, trading_day, price: str, volume_shares: str, amount: str) -> None:
        self.clock = clock
        self.trading_day = trading_day
        self.price = price
        self.volume_shares = volume_shares
        self.amount = amount


class TencentSource:
    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def intraday(self, symbol: Symbol, period: str, limit: int) -> list[IntradayBar]:
        if period not in PERIOD_MINUTES:
            raise DomainError("MARKET_SYMBOL_INVALID", "不支持的分钟周期。")
        if not symbol.is_tencent_supported:
            raise DomainError("MARKET_DATA_UNAVAILABLE", "腾讯行情不覆盖北交所标的。")
        count = max(1, min(limit, MAX_BARS))
        payload = self._client.get_json(
            provider=PROVIDER,
            url=KLINE_URL,
            params={"param": f"{symbol.qq_code},{period},,{count}"},
            headers=HEADERS,
        )
        node = _node(payload, symbol)
        rows = node.get(period)
        if rows is None or rows == []:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        if not isinstance(rows, list):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        unit = tencent_volume_unit(symbol)
        bars = [_bar(row, unit) for row in rows]
        return bars[-count:]

    def opening_auction(self, symbol: Symbol, trading_day) -> AuctionTrade | None:
        """The 09:25 auction trade for the latest session, or None when absent.

        Volume here is 手 on every board (see the note in the parser), so the
        returned share count is exact for 600519 but rounded to whole 手 for STAR
        instruments. ``amount`` is authoritative in both cases.

        The trade list carries no date, so the caller supplies the trading day it
        wants to annotate; a mismatch cannot be detected here and is therefore
        also not fabricated by this provider.
        """
        if not symbol.is_tencent_supported:
            return None
        text = self._client.get_text(
            provider=PROVIDER,
            url=TICK_URL,
            params={"appn": "detail", "action": "data", "c": symbol.qq_code, "p": "0"},
            headers=HEADERS,
            encoding="gbk",
        ).strip()
        if not text:
            # Indices and suspended instruments have no per-trade detail.
            return None
        match = _TICK_LINE.match(text)
        if match is None or match.group("symbol") != symbol.qq_code:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        if match.group("page") != "0":
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        body = match.group("body")
        if not body:
            return None
        parts = body.split("|", 1)[0].split("/")
        if len(parts) != 7:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        clock = parts[1]
        if not clock.startswith(OPENING_AUCTION_CLOCK):
            # The list no longer starts with the auction (e.g. it was cleared
            # before the open): report "no auction trade", never a wrong one.
            return None
        finite_decimal(parts[2])
        finite_decimal(parts[5])
        # Per-trade detail volume is 手 on every board, including STAR, unlike the
        # minute bars. Verification: 688017's 09:25 trade reports 151 手 and
        # 3,599,988 元, i.e. 15,126 shares, which the 09:30 bar also contains.
        volume = shares(parts[4], "lots")
        return AuctionTrade(clock, trading_day, parts[2], volume, parts[5])


def _node(payload, symbol: Symbol) -> dict:
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    node = data.get(symbol.qq_code)
    if not isinstance(node, dict):
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    return node


def _bar(row, unit) -> IntradayBar:
    if not isinstance(row, list) or len(row) < 6:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    try:
        start = parse_minute_timestamp(str(row[0]))
    except ValueError:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
    for value in row[1:6]:
        finite_decimal(value)
    volume = shares(str(row[5]), unit)
    return IntradayBar(
        start=start,
        trading_day=start.astimezone(MARKET_TZ).date(),
        open_=str(row[1]),
        high=str(row[3]),
        low=str(row[4]),
        close=str(row[2]),
        volume_shares=volume,
    )
