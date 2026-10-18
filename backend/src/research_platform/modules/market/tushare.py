"""Tushare Pro adapter: daily bars used for reconciliation and history.

Tushare is a token-authenticated HTTP query API. Only reviewed, permission-checked
api names are called; the token goes to Tushare only and is never logged or
returned. Errors are mapped instead of surfaced verbatim:

- ``code`` 0: success; ``data.fields`` + ``data.items`` is the payload;
- permission (40203 with "没有接口...权限") → ``MARKET_SOURCE_PERMISSION_DENIED``;
- rate limit (40203 with "频率") → ``MARKET_SOURCE_RATE_LIMITED``;
- anything else → ``MARKET_SOURCE_UNAVAILABLE``.

Verified with the inherited legacy token on 2026-10-18: ``daily``,
``daily_basic``, ``trade_cal`` work; ``stk_mins`` is rate-limited to one call per
hour on that account, ``stk_auction`` / ``rt_k`` / ``fund_daily`` have no
permission. Therefore the auction series here comes from Eastmoney/Tencent and
Tushare is used for daily reconciliation, not as the intraday source.
"""

from __future__ import annotations

from datetime import datetime

from research_platform.core.config import TushareConfig
from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient

from .parsing import finite_decimal
from .symbols import Symbol

PROVIDER = "tushare"

# Tushare daily ``vol`` is 手 and ``amount`` is 千元 for stocks (index_daily vol
# is 手 as well); both are converted to shares / 元 at this boundary so the
# public contract stays consistent across providers.
DAYS_URL_LIMIT = 600


class DailyBar:
    __slots__ = ("trading_day", "open", "high", "low", "close", "volume_shares", "amount")

    def __init__(self, trading_day, open_, high, low, close, volume_shares, amount) -> None:
        self.trading_day = trading_day
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume_shares = volume_shares
        self.amount = amount


class TushareSource:
    def __init__(self, client: UpstreamClient, config: TushareConfig | None) -> None:
        self._client = client
        self._config = config

    @property
    def configured(self) -> bool:
        return self._config is not None

    def daily(self, symbol: Symbol, start_date: str, end_date: str) -> list[DailyBar]:
        rows = self._call(
            "daily",
            {
                "ts_code": symbol.ts_code,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        fields = rows["fields"]
        index = {name: position for position, name in enumerate(fields)}
        required = {"trade_date", "open", "high", "low", "close", "vol", "amount"}
        if not required.issubset(index):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        bars: list[DailyBar] = []
        for item in rows["items"]:
            try:
                bars.append(
                    DailyBar(
                        trading_day=_trading_day(item[index["trade_date"]]),
                        open_=_decimal(item[index["open"]]),
                        high=_decimal(item[index["high"]]),
                        low=_decimal(item[index["low"]]),
                        close=_decimal(item[index["close"]]),
                        volume_shares=_decimal(item[index["vol"]], scale=100),
                        amount=_decimal(item[index["amount"]], scale=1000),
                    )
                )
            except (IndexError, TypeError, KeyError):
                raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
        if not bars:
            # Tushare answers with an empty item list for an index/ETF (not served
            # by ``daily``), a suspended day or an empty range. Returning 200 with
            # ``bars=[]`` would report "success" for a question it did not answer.
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        bars.sort(key=lambda bar: bar.trading_day)
        return bars

    def _call(self, api_name: str, params: dict) -> dict:
        config = self._config
        if config is None:
            raise DomainError("MARKET_SOURCE_NOT_CONFIGURED")
        payload = self._client.post_json(
            provider=PROVIDER,
            url=config.url,
            payload={
                "api_name": api_name,
                "token": config.token.get_secret_value(),
                "params": params,
                "fields": "",
            },
            headers={"Content-Type": "application/json"},
        )
        if not isinstance(payload, dict):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        code = payload.get("code")
        if code != 0:
            raise _mapped_error(code, str(payload.get("msg") or ""))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        fields = data.get("fields")
        items = data.get("items")
        if not isinstance(fields, list) or not isinstance(items, list):
            raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
        return {"fields": [str(name) for name in fields], "items": items}


def _mapped_error(code, message: str) -> DomainError:
    """Map Tushare's errcode/message pair onto our vocabulary.

    Only the classification is kept: the upstream message is not returned to the
    caller, and it is not logged either (it can echo request parameters).
    """
    lowered = message.lower()
    if "频率" in message or "每分钟" in message or "每小时" in message or "rate" in lowered:
        return DomainError("MARKET_SOURCE_RATE_LIMITED")
    if "权限" in message or "permission" in lowered:
        return DomainError("MARKET_SOURCE_PERMISSION_DENIED")
    if code == 40203:
        return DomainError("MARKET_SOURCE_PERMISSION_DENIED")
    return DomainError("MARKET_SOURCE_UNAVAILABLE")


def _decimal(value, scale: int = 1) -> str:
    """Provider numbers to a decimal string; never float arithmetic."""
    amount = finite_decimal(value) * scale
    return format(amount.normalize(), "f")


def _trading_day(value) -> str:
    """Validate the provider's ``YYYYMMDD``; keep it as a string for sorting."""
    text = str(value).strip()
    try:
        datetime.strptime(text, "%Y%m%d")
    except ValueError:
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
    return text
