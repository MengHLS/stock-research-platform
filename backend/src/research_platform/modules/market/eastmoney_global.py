"""Cross-market quote and daily-bar fallback from Eastmoney."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .global_types import GLOBAL_INSTRUMENTS, GlobalBar, GlobalInstrument, GlobalQuote
from .parsing import finite_decimal, optional_decimal, parse_day

PROVIDER = "eastmoney"
QUOTE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
HEADERS = {"Referer": "https://quote.eastmoney.com/", "Accept": "*/*"}

_QUOTE_FIELDS = "f2,f3,f4,f12,f13,f14,f15,f16,f17,f18,f124"
_KLINE_FIELDS_1 = "f1,f2,f3,f4,f5,f6"
_KLINE_FIELDS_2 = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"


class EastmoneyGlobalSource:
    """Provider-level parsing for Eastmoney's global quote and K-line endpoints."""

    provider = PROVIDER

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    def quotes(self) -> dict[str, GlobalQuote]:
        payload = self._client.get_json(
            provider=PROVIDER,
            url=QUOTE_URL,
            params={
                "fltt": "2",
                "invt": "2",
                "fields": _QUOTE_FIELDS,
                "secids": ",".join(item.secid for item in GLOBAL_INSTRUMENTS),
            },
            headers=HEADERS,
        )
        root = _mapping(payload)
        data = _mapping(root.get("data"))
        rows = data.get("diff")
        if not isinstance(rows, list):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")

        by_secid: dict[str, dict] = {}
        for raw in rows:
            row = _mapping(raw)
            code = "" if row.get("f12") is None else str(row["f12"]).strip()
            market = "" if row.get("f13") is None else str(row["f13"]).strip()
            if not code or not market:
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            by_secid[f"{market}.{code}"] = row

        result: dict[str, GlobalQuote] = {}
        for instrument in GLOBAL_INSTRUMENTS:
            row = by_secid.get(instrument.secid)
            if row is None:
                continue
            price = optional_decimal(row.get("f2"))
            if price is None:
                continue
            result[instrument.key] = GlobalQuote(
                price=price,
                previous_close=optional_decimal(row.get("f18")),
                open=optional_decimal(row.get("f17")),
                high=optional_decimal(row.get("f15")),
                low=optional_decimal(row.get("f16")),
                change=optional_decimal(row.get("f4")),
                change_pct=optional_decimal(row.get("f3")),
                quote_time=_timestamp(row.get("f124")),
                provider=PROVIDER,
            )
        return result

    def history(self, instrument: GlobalInstrument, window: int) -> list[GlobalBar]:
        end = datetime.now(UTC).date()
        begin = end - timedelta(days=max(120, window * 4))
        payload = self._client.get_json(
            provider=PROVIDER,
            url=KLINE_URL,
            params={
                "secid": instrument.secid,
                "fields1": _KLINE_FIELDS_1,
                "fields2": _KLINE_FIELDS_2,
                "klt": "101",
                "fqt": "1",
                "beg": begin.strftime("%Y%m%d"),
                "end": "20500101",
                "lmt": str(window),
            },
            headers=HEADERS,
        )
        root = _mapping(payload)
        data = _mapping(root.get("data"))
        rows = data.get("klines")
        if not isinstance(rows, list) or not rows:
            raise DomainError("MARKET_DATA_UNAVAILABLE")

        bars: list[GlobalBar] = []
        previous_day = None
        for raw in rows[-window:]:
            fields = str(raw).split(",")
            if len(fields) < 9:
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            trading_day = parse_day(fields[0], "%Y-%m-%d")
            if previous_day is not None and trading_day <= previous_day:
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            open_price = finite_decimal(fields[1])
            close = finite_decimal(fields[2])
            high = finite_decimal(fields[3])
            low = finite_decimal(fields[4])
            if high < low or not (low <= open_price <= high and low <= close <= high):
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
            bars.append(
                GlobalBar(
                    trading_day=trading_day,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    change_pct=optional_decimal(fields[8]),
                )
            )
            previous_day = trading_day
        return bars


# Kept as a compatibility alias for callers that imported the former class name.
GlobalMarketSource = EastmoneyGlobalSource


def _mapping(value: object) -> dict:
    if not isinstance(value, dict):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    return value


def _timestamp(value: object) -> datetime | None:
    seconds = optional_decimal(value)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(int(seconds), tz=UTC)
    except (OverflowError, OSError, ValueError):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
