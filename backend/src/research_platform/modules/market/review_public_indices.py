"""Public daily bars for reviewed indices absent from the legacy source."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import date, datetime, timedelta

from research_platform.core.cache import TTLCache
from research_platform.core.errors import DomainError
from research_platform.core.logging import log_event

from .global_types import GLOBAL_INSTRUMENTS, GlobalBar, GlobalInstrument
from .models import utc_now
from .review import IndexBar
from .review_index_store import ReviewIndexBarStore, ReviewIndexStoreError
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
        store: ReviewIndexBarStore,
        *,
        cache: TTLCache | None = None,
        cache_seconds: float = 60,
        refresh_seconds: float = 3600,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self._client = client
        self._store = store
        self._cache = cache if cache is not None else TTLCache()
        self._cache_seconds = cache_seconds
        self._refresh_seconds = refresh_seconds
        self._now = now
        self._refresh_locks = {
            symbol: threading.Lock() for symbol in PUBLIC_REVIEW_INDEX_INSTRUMENTS
        }

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
            self._refresh_if_stale(symbol, instrument)
            try:
                rows[symbol] = self._store.index_rows(start, end, [symbol])[symbol]
            except ReviewIndexStoreError as error:
                log_event(
                    "market.review.index_store_degraded",
                    level=logging.ERROR,
                    symbol=symbol,
                    error_type=type(error).__name__,
                )
                rows[symbol] = []
        return rows

    def _refresh_if_stale(
        self,
        symbol: str,
        instrument: GlobalInstrument,
    ) -> None:
        with self._refresh_locks[symbol]:
            try:
                latest = self._store.latest_fetched_at(symbol)
            except ReviewIndexStoreError as error:
                log_event(
                    "market.review.index_store_degraded",
                    level=logging.ERROR,
                    symbol=symbol,
                    error_type=type(error).__name__,
                )
                return
            now = self._now()
            if latest is not None and latest > now - timedelta(seconds=self._refresh_seconds):
                return
            try:
                history, fetched_at = self._cache.get_or_create(
                    ("review-public-index", symbol),
                    min(self._cache_seconds, self._refresh_seconds),
                    lambda: (
                        self._client.history(
                            instrument,
                            PUBLIC_INDEX_HISTORY_BARS,
                        ),
                        self._now(),
                    ),
                )
            except DomainError as error:
                log_event(
                    "market.review.index_refresh_degraded",
                    level=logging.WARNING,
                    symbol=symbol,
                    error_code=error.code,
                )
                return
            if latest is not None and fetched_at <= latest:
                return
            bars = [_index_bar(symbol, bar) for bar in history]
            try:
                self._store.upsert(
                    symbol,
                    bars,
                    provider=self.provider,
                    fetched_at=fetched_at,
                )
            except ReviewIndexStoreError as error:
                log_event(
                    "market.review.index_store_degraded",
                    level=logging.ERROR,
                    symbol=symbol,
                    error_type=type(error).__name__,
                )


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
