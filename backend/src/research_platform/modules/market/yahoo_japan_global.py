"""Yahoo Japan history fallback for the Nikkei 225."""

from __future__ import annotations

import json
import math
import re

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .global_types import GlobalBar, GlobalInstrument, change_percent
from .parsing import finite_decimal, parse_day

PROVIDER = "yahoo_japan"
HISTORY_URL = "https://finance.yahoo.co.jp/quote/998407.O/history"
HEADERS = {
    "Referer": "https://finance.yahoo.co.jp/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141.0 Safari/537.36"
    ),
}
_HISTORY_ITEMS = re.compile(
    r'\\"historyTable\\":\{\\"items\\":(\[.*?\]),\\"',
    re.DOTALL,
)


class YahooJapanGlobalSource:
    provider = PROVIDER

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def history(self, instrument: GlobalInstrument, window: int) -> list[GlobalBar]:
        if instrument.key != "nikkei":
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        pages = min(6, math.ceil((window + 1) / 20))
        rows: dict[str, dict] = {}
        for page in range(1, pages + 1):
            text = self._client.get_text(
                provider=PROVIDER,
                url=HISTORY_URL,
                params={"page": str(page)},
                headers=HEADERS,
            )
            for row in _page_rows(text):
                rows[str(row["date"])] = row
        if not rows:
            raise DomainError("MARKET_DATA_UNAVAILABLE")

        bars: list[GlobalBar] = []
        previous_close = None
        previous_day = None
        for row in sorted(rows.values(), key=lambda item: _sort_day(str(item["date"]))):
            trading_day = parse_day(row["date"], "%Y/%m/%d")
            open_price = finite_decimal(str(row["openPrice"]).replace(",", ""))
            high = finite_decimal(str(row["highPrice"]).replace(",", ""))
            low = finite_decimal(str(row["lowPrice"]).replace(",", ""))
            close = finite_decimal(str(row["closePrice"]).replace(",", ""))
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


def _page_rows(text: str) -> list[dict]:
    match = _HISTORY_ITEMS.search(text)
    if match is None:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    try:
        decoded = json.loads(f'"{match.group(1)}"')
        rows = json.loads(decoded)
    except json.JSONDecodeError:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
    if not isinstance(rows, list) or not rows:
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    required = {"date", "openPrice", "highPrice", "lowPrice", "closePrice"}
    if not all(isinstance(row, dict) and required <= row.keys() for row in rows):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    return rows


def _sort_day(value: str) -> tuple[int, int, int]:
    try:
        year, month, day = (int(part) for part in value.split("/"))
    except (TypeError, ValueError):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
    return year, month, day
