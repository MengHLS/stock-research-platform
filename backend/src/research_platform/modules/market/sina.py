"""Sina public quote endpoints: the matched opening-auction trade.

``quotes.sina.cn/cn/api/openapi.php/CN_MinlineService.getMinlineData?symbol=<code>``
returns the current session's minute series (GBK-free JSON). The first row is the
09:25 opening call-auction trade:

- ``{"m": "09:25:00", "v": "<shares>", "p": "<price>", "avg_p": "<avg price>"}``
- volume is **shares on every board**, including STAR and BSE (verified
  2026-10-16: 688017 reports 15,126 shares and ``vol × price`` equals the tick
  detail amount 3,599,988 元 exactly);
- coverage includes SSE, SZSE, BSE, STAR, ETFs and indices;
- the series has no date; ``hq.sinajs.cn/list=<code>`` supplies the session date
  (field 30) and the previous close (field 2) for the same symbol.

This source is used for the *matched* auction result because it is reliable and
share-exact; the 09:15–09:25 virtual curve only exists on Eastmoney.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .market_time import at_market_clock
from .parsing import finite_decimal, parse_day
from .symbols import Symbol

PROVIDER = "sina"
MINLINE_URL = "https://quotes.sina.cn/cn/api/openapi.php/CN_MinlineService.getMinlineData"
SNAPSHOT_URL = "https://hq.sinajs.cn/list"
HEADERS = {"Referer": "https://finance.sina.com.cn/"}
OPENING_AUCTION_CLOCK = "09:25:00"


class AuctionMatch:
    __slots__ = ("trading_day", "matched_time", "price", "volume_shares", "amount", "pre_close")

    def __init__(self, trading_day, matched_time, price, volume_shares, amount, pre_close) -> None:
        self.trading_day = trading_day
        self.matched_time = matched_time
        self.price = price
        self.volume_shares = volume_shares
        self.amount = amount
        self.pre_close = pre_close


class SinaSource:
    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def opening_auction(self, symbol: Symbol) -> AuctionMatch:
        """Auction trade from the minute series, whose rows carry no date.

        The series has no date field, so the trading day has to come from the
        snapshot. That is only sound if the session did not roll over between the
        two calls: the snapshot is therefore read *before* and *after* the series
        and the two dates must agree. Otherwise the 09:25 row could belong to the
        previous session while the second snapshot already names the new one, and
        the auction would be filed under the wrong day.
        """
        before_day, _ = self._session(symbol)
        payload = self._client.get_json(
            provider=PROVIDER, url=MINLINE_URL, params={"symbol": symbol.qq_code}, headers=HEADERS
        )
        rows = _rows(payload)
        if not rows:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        first = rows[0]
        if not isinstance(first, dict):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        if "m" not in first:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        if str(first.get("m")) != OPENING_AUCTION_CLOCK:
            # The series only starts at 09:25 once the auction has matched; a
            # different first row means there is no auction row to report.
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        try:
            price = finite_decimal(first["p"])
            volume = finite_decimal(first["v"])
        except KeyError:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
        if volume <= 0:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        after_day, pre_close = self._session(symbol)
        if after_day != before_day:
            # The session rolled over while the series was being read: the row's
            # date cannot be attributed, so refuse to guess.
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        trading_day = after_day
        moment = at_market_clock(trading_day, OPENING_AUCTION_CLOCK)
        return AuctionMatch(
            trading_day=trading_day,
            matched_time=moment,
            price=format(price.normalize(), "f"),
            volume_shares=format(volume.normalize(), "f"),
            amount=format((price * volume).normalize(), "f"),
            pre_close=format(pre_close.normalize(), "f") if pre_close is not None else None,
        )

    def _session(self, symbol: Symbol) -> tuple[date, Decimal | None]:
        """Trading day and previous close from the snapshot.

        The snapshot date is the last *traded* session, not necessarily today: on
        a trading morning before 09:25 it still names the previous session, and
        the minute series also still holds that session's 09:25 row. Callers must
        therefore treat a day older than the current exchange date as "no auction
        for today yet" instead of reporting yesterday's auction as today's.
        """
        text = self._client.get_text(
            provider=PROVIDER,
            url=f"{SNAPSHOT_URL}={symbol.qq_code}",
            headers=HEADERS,
            encoding="gbk",
        )
        marker = f'hq_str_{symbol.qq_code}="'
        start = text.find(marker)
        if start < 0:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        start += len(marker)
        end = text.find('"', start)
        if end < 0:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        fields = text[start:end].split(",")
        if len(fields) < 31 or not fields[30]:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        trading_day = parse_day(fields[30], "%Y-%m-%d")
        pre_close = finite_decimal(fields[2]) if fields[2] else None
        return trading_day, pre_close


def _rows(payload):
    if not isinstance(payload, dict):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    status = result.get("status")
    if not isinstance(status, dict) or status.get("code") != 0:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    # ``data`` missing entirely means the shape changed; ``data: null`` is the
    # provider's explicit "nothing to return". Only the latter is "no data".
    if "data" not in result:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    rows = result["data"]
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    return rows
