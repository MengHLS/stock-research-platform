"""Eastmoney public quote endpoint: the opening call-auction (09:15–09:25) series.

Tencent's minute K lines only expose the *matched* auction result (folded into the
09:30 bar), not the virtual-match curve that forms between 09:15 and 09:25. The
public Eastmoney intraday-trends endpoint returns that curve when asked for the
pre-market segment:

``push2.eastmoney.com/api/qt/stock/trends2/get?...&iscr=1`` — one row per minute.

- rows ``09:15``–``09:25`` carry the virtual matching price with zero traded
  volume (nothing has traded yet): the "竞价快照" series;
- the first row after 09:25 that carries volume is the actual auction result
  (price, volume, amount). Verified 2026-10-16: it equals the 09:25 trade from
  Tencent's tick detail for 600519, 000001, 688017 and 510300;
- volume is **手 for every board including STAR** (unlike Tencent's minute bars,
  where 688/689 are 股): 688017 matched 151 手 = 15,100 shares against an amount
  of 3,599,988 元. It is therefore always converted with the "lots" unit here.
  The provider rounds to whole 手, so a STAR share count derived this way can
  differ from the exact figure by less than 100 shares; the 09:30 one-minute bar
  carries the exact value and ``matched_amount`` remains authoritative;
- ``preClose`` comes back separately;
- the endpoint expects a browser-like ``Referer``; without it the peer sometimes
  drops the connection, which the shared UpstreamClient bounds and retries.
"""

from __future__ import annotations

from decimal import Decimal

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .market_time import MARKET_TZ, parse_quote_timestamp
from .parsing import finite_decimal, optional_decimal
from .symbols import Symbol, shares

PROVIDER = "eastmoney"
# Host rotation for the same endpoint. ``push2his`` serves the identical payload and
# is reachable in environments where ``push2`` is not (verified 2026-10-18 on a
# local machine whose DNS/proxy resolves push2 to a fake-ip in 198.18.0.0/15 and
# whose TLS stack cannot satisfy push2's renegotiation request). Order is
# deliberate: the documented page host first, then the historical host.
TRENDS_HOSTS = ("push2.eastmoney.com", "push2his.eastmoney.com")
TRENDS_PATH = "/api/qt/stock/trends2/get"
PROFILE_PATH = "/api/qt/stock/get"
HEADERS = {"Referer": "https://quote.eastmoney.com/", "Accept": "*/*"}
# Public web token the Eastmoney page itself uses; not a user credential.
PUBLIC_UT = "fa5fd1943c7b386f172d6893dbfba10b"
OPEN_AUCTION_END = "09:25"
CONTINUOUS_START = "09:30"

# Failures that justify trying the next host instead of giving up.
_HOST_FALLBACK_CODES = frozenset({"MARKET_SOURCE_UNAVAILABLE"})


class AuctionSnapshot:
    """One minute of the 09:15–09:25 virtual matching curve."""

    __slots__ = ("time", "price")

    def __init__(self, time, price: str) -> None:
        self.time = time
        self.price = price


class AuctionResult:
    __slots__ = (
        "snapshots",
        "matched_time",
        "matched_price",
        "volume_shares",
        "amount",
        "pre_close",
    )

    def __init__(self, snapshots, matched_time, matched_price, volume_shares, amount, pre_close):
        self.snapshots = snapshots
        self.matched_time = matched_time
        self.matched_price = matched_price
        self.volume_shares = volume_shares
        self.amount = amount
        self.pre_close = pre_close


class StockProfile:
    __slots__ = ("name", "industry")

    def __init__(self, name: str, industry: str | None) -> None:
        self.name = name
        self.industry = industry


def _trends_params(symbol: Symbol) -> dict[str, str]:
    return {
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "ut": PUBLIC_UT,
        "ndays": "1",
        # iscr=1 includes the 09:15-09:29 pre-market segment.
        "iscr": "1",
        "iscca": "0",
        "secid": symbol.eastmoney_secid,
    }


def _profile_params(symbol: Symbol) -> dict[str, str]:
    return {
        "fields": "f57,f58,f127",
        "ut": PUBLIC_UT,
        "secid": symbol.eastmoney_secid,
    }


class EastmoneySource:
    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def _fetch(self, path: str, params: dict[str, str]):
        """Try each reviewed host in order; the first usable payload wins.

        A host that is unreachable (DNS fake-ip, TLS renegotiation refusal, 5xx)
        must not decide the answer for the others: the same endpoint is served by
        more than one Eastmoney host, and which ones are reachable depends on the
        operator's network. Only when every host fails is the source unavailable.
        """
        last: DomainError | None = None
        for host in TRENDS_HOSTS:
            try:
                return self._client.get_json(
                    provider=PROVIDER,
                    url=f"https://{host}{path}",
                    params=params,
                    headers=HEADERS,
                )
            except DomainError as error:
                if error.code not in _HOST_FALLBACK_CODES:
                    raise
                last = error
        assert last is not None
        raise last

    def _fetch_trends(self, symbol: Symbol):
        return self._fetch(TRENDS_PATH, _trends_params(symbol))

    def opening_auction(self, symbol: Symbol) -> AuctionResult:
        payload = self._fetch_trends(symbol)
        if not isinstance(payload, dict):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        # A missing container is a *different* failure from an explicit empty
        # one: it means the response shape changed, not that the instrument has
        # no auction. Reporting it as "no data" would hide a provider change and
        # also stop the auction degradation chain from trying the next source.
        if "data" not in payload:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        data = payload["data"]
        if data is None:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        if not isinstance(data, dict):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        if "trends" not in data:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        rows = data["trends"]
        if rows is None:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        if not isinstance(rows, list):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        unit = "lots"  # Eastmoney quotes auction volume in 手 on every board.
        snapshots: list[AuctionSnapshot] = []
        matched = None
        for raw in rows:
            parsed = _row(raw)
            if parsed is None:
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            moment, _open, close, _high, _low, volume, amount = parsed
            clock = moment.astimezone(MARKET_TZ).strftime("%H:%M")
            if clock >= CONTINUOUS_START:
                break
            if clock <= OPEN_AUCTION_END:
                snapshots.append(AuctionSnapshot(moment, close))
            elif Decimal(volume) > 0:
                # The first row after 09:25 that traded is the auction result.
                # Later rows belong to continuous trading and must not overwrite
                # it: the loop used to keep assigning and the *last* non-zero row
                # won, which silently reported a continuous-trading print as the
                # auction whenever the provider emitted one inside 09:26-09:29.
                matched = (moment, close, shares(volume, unit), amount)
                break
        if not snapshots and matched is None:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        # `matched` stays None before 09:25: the virtual curve is still the
        # requested data, so it is returned without inventing a matched result.
        pre_close = _decimal_or_none(data.get("preClose"))
        if matched is None:
            return AuctionResult(snapshots, None, None, None, None, pre_close)
        moment, price, volume_shares, amount = matched
        return AuctionResult(snapshots, moment, price, volume_shares, amount, pre_close)

    def stock_profile(self, symbol: Symbol) -> StockProfile:
        payload = self._fetch(PROFILE_PATH, _profile_params(symbol))
        if not isinstance(payload, dict):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        if "data" not in payload:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        data = payload["data"]
        if data is None:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        if not isinstance(data, dict):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        code = data.get("f57")
        name = data.get("f58")
        if not isinstance(code, str) or code != symbol.code:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        if not isinstance(name, str) or not name.strip():
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        industry = data.get("f127")
        if industry is not None and not isinstance(industry, str):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        return StockProfile(name=name.strip(), industry=(industry or "").strip() or None)


def _row(raw):
    if not isinstance(raw, str):
        return None
    parts = raw.split(",")
    if len(parts) < 7:
        return None
    try:
        moment = parse_quote_timestamp(parts[0])
        for value in parts[1:7]:
            finite_decimal(value)
    except (ValueError, DomainError):
        return None
    return moment, parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]


def _decimal_or_none(value):
    parsed = optional_decimal(value)
    return None if parsed is None else str(parsed)
