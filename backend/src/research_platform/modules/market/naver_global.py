"""Naver daily history fallback for KOSPI."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .global_types import GlobalBar, GlobalInstrument, change_percent
from .parsing import finite_decimal, parse_day

PROVIDER = "naver"
HISTORY_URL = "https://api.finance.naver.com/siseJson.naver"
HEADERS = {"Referer": "https://finance.naver.com/"}


class NaverGlobalSource:
    provider = PROVIDER

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def history(self, instrument: GlobalInstrument, window: int) -> list[GlobalBar]:
        if instrument.key != "kospi":
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        end = datetime.now(UTC).date()
        begin = end - timedelta(days=max(400, window * 4))
        text = self._client.get_text(
            provider=PROVIDER,
            url=HISTORY_URL,
            params={
                "symbol": "KOSPI",
                "requestType": "1",
                "startTime": begin.strftime("%Y%m%d"),
                "endTime": end.strftime("%Y%m%d"),
                "timeframe": "day",
            },
            headers=HEADERS,
            encoding="euc-kr",
        )
        try:
            payload = ast.literal_eval(text.strip())
        except (SyntaxError, ValueError):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
        if not isinstance(payload, list) or not payload:
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")

        bars: list[GlobalBar] = []
        previous_close = None
        previous_day = None
        for row in payload:
            if not isinstance(row, list):
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            if not row or not str(row[0]).isdigit() or len(str(row[0])) != 8:
                continue
            if len(row) < 5:
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            trading_day = parse_day(row[0], "%Y%m%d")
            open_price = finite_decimal(row[1])
            high = finite_decimal(row[2])
            low = finite_decimal(row[3])
            close = finite_decimal(row[4])
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
