"""Public daily bars for reviewed indices absent from the legacy source."""

from __future__ import annotations

from datetime import date

from research_platform.core.cache import TTLCache

from .global_types import GLOBAL_INSTRUMENTS, GlobalBar, GlobalInstrument
from .review import IndexBar
from .tencent_global import TencentGlobalSource

# The public endpoint currently returns at most 160 bars. That still covers a
# 120-day response window plus the 19 prior observations needed by MA20.
PUBLIC_INDEX_HISTORY_BARS = 160


def _instrument(key: str) -> GlobalInstrument:
    return next(item for item in GLOBAL_INSTRUMENTS if item.key == key)


PUBLIC_REVIEW_INDEX_INSTRUMENTS = {
    "399006.SZ": _instrument("chinext"),
    "000688.SH": _instrument("star50"),
}


class PublicReviewIndexSource:
    """Tencent's unadjusted index daily bars, bounded to reviewed symbols."""

    provider = "tencent"

    def __init__(
        self,
        client: TencentGlobalSource,
        *,
        cache: TTLCache | None = None,
        cache_seconds: float = 60,
    ) -> None:
        self._client = client
        self._cache = cache if cache is not None else TTLCache()
        self._cache_seconds = cache_seconds

    def index_rows(
        self,
        start: date,
        end: date,
        symbols: list[str],
    ) -> dict[str, list[IndexBar]]:
        rows: dict[str, list[IndexBar]] = {}
        for symbol in symbols:
            instrument = PUBLIC_REVIEW_INDEX_INSTRUMENTS.get(symbol)
            if instrument is None:
                raise ValueError(f"unsupported public review index: {symbol}")
            history = self._cache.get_or_create(
                ("review-public-index", symbol),
                self._cache_seconds,
                lambda instrument=instrument: self._client.history(
                    instrument,
                    PUBLIC_INDEX_HISTORY_BARS,
                ),
            )
            rows[symbol] = [
                _index_bar(symbol, bar) for bar in history if start <= bar.trading_day <= end
            ]
        return rows


def _index_bar(symbol: str, bar: GlobalBar) -> IndexBar:
    return IndexBar(
        trading_day=bar.trading_day,
        symbol=symbol,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        amount_source=None,
        volume_source=None,
    )
