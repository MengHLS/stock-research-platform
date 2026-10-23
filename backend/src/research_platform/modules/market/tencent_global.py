"""Tencent daily K-line fallback for cross-market instruments it covers."""

from __future__ import annotations

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .global_types import GlobalBar, GlobalInstrument, change_percent
from .parsing import finite_decimal, parse_day

PROVIDER = "tencent"
# The legacy fqkline path now returns a Tencent WAF 501 for some networks.
# Keep two documented K-line hosts so a single endpoint change degrades only
# this provider attempt instead of turning valid index history into "missing".
TENCENT_KLINE_URLS = (
    "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
    "https://web.ifzq.gtimg.cn/appstock/app/kline/kline",
)
KLINE_URL = TENCENT_KLINE_URLS[0]
HEADERS = {"Referer": "https://gu.qq.com/"}
_DEGRADABLE_ENDPOINT_ERRORS = frozenset(
    {
        "MARKET_DATA_UNAVAILABLE",
        "MARKET_SOURCE_BAD_RESPONSE",
        "MARKET_SOURCE_RATE_LIMITED",
        "MARKET_SOURCE_UNAVAILABLE",
    }
)


class TencentGlobalSource:
    provider = PROVIDER

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def history(self, instrument: GlobalInstrument, window: int) -> list[GlobalBar]:
        if instrument.tencent_symbol is None:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        last_error: DomainError | None = None
        for url in TENCENT_KLINE_URLS:
            try:
                payload = self._client.get_json(
                    provider=PROVIDER,
                    url=url,
                    params={"param": f"{instrument.tencent_symbol},day,,,{window + 1},"},
                    headers=HEADERS,
                )
                return _parse_history(payload, instrument, window)
            except DomainError as error:
                if error.code not in _DEGRADABLE_ENDPOINT_ERRORS:
                    raise
                last_error = error
        if last_error is not None:
            raise DomainError(last_error.code)
        raise DomainError("MARKET_DATA_UNAVAILABLE")


def _parse_history(
    payload: object,
    instrument: GlobalInstrument,
    window: int,
) -> list[GlobalBar]:
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    node = data.get(instrument.tencent_symbol)
    if not isinstance(node, dict):
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    rows = node.get("day")
    if rows == []:
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    if not isinstance(rows, list):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")

    bars: list[GlobalBar] = []
    previous_close = None
    previous_day = None
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        trading_day = parse_day(row[0], "%Y-%m-%d")
        open_price = finite_decimal(row[1])
        close = finite_decimal(row[2])
        high = finite_decimal(row[3])
        low = finite_decimal(row[4])
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
