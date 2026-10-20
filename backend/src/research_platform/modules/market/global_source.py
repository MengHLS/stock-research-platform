"""Provider failover for the cross-market overview."""

from __future__ import annotations

import logging
import threading
import time

from research_platform.core.errors import DomainError
from research_platform.core.logging import log_event
from research_platform.core.upstream import UpstreamClient

from .eastmoney_global import EastmoneyGlobalSource
from .global_types import GLOBAL_INSTRUMENTS, GlobalBar, GlobalInstrument, GlobalQuote
from .naver_global import NaverGlobalSource
from .sina_global import SinaGlobalSource
from .tencent_global import TencentGlobalSource
from .yahoo_global import YahooGlobalSource
from .yahoo_japan_global import YahooJapanGlobalSource

_DEGRADABLE_CODES = frozenset(
    {
        "MARKET_DATA_UNAVAILABLE",
        "MARKET_SOURCE_BAD_RESPONSE",
        "MARKET_SOURCE_RATE_LIMITED",
        "MARKET_SOURCE_UNAVAILABLE",
    }
)
_SOURCE_FAILURE_CODES = frozenset(
    {
        "MARKET_SOURCE_BAD_RESPONSE",
        "MARKET_SOURCE_RATE_LIMITED",
        "MARKET_SOURCE_UNAVAILABLE",
    }
)
_PROVIDER_COOLDOWN_SECONDS = 60


class GlobalMarketSource:
    """Use a batch quote source first and venue-specific history fallbacks."""

    def __init__(
        self,
        client: UpstreamClient,
        *,
        quote_sources=None,
        history_sources=None,
    ) -> None:
        self._quote_sources = (
            tuple(quote_sources)
            if quote_sources is not None
            else (
                SinaGlobalSource(client),
                EastmoneyGlobalSource(client),
                YahooGlobalSource(client),
            )
        )
        self._history_sources = (
            dict(history_sources)
            if history_sources is not None
            else {
                "sina": SinaGlobalSource(client),
                "yahoo": YahooGlobalSource(client),
                "tencent": TencentGlobalSource(client),
                "naver": NaverGlobalSource(client),
                "yahoo_japan": YahooJapanGlobalSource(client),
                "eastmoney": EastmoneyGlobalSource(client),
            }
        )
        self.last_quote_provider = "unknown"
        self.last_history_providers: dict[str, str] = {}
        self._health_lock = threading.Lock()
        self._provider_cooldown_until: dict[str, float] = {}

    def quotes(self) -> dict[str, GlobalQuote]:
        last_error: DomainError | None = None
        for source in self._quote_sources:
            health_key = f"quote:{source.provider}"
            if not self._provider_available(health_key):
                continue
            try:
                quotes = source.quotes()
            except DomainError as error:
                if error.code not in _DEGRADABLE_CODES:
                    raise
                last_error = error
                self._mark_degraded(health_key, error.code)
                log_event(
                    "market.global_quote_degraded",
                    level=logging.ERROR
                    if error.code == "MARKET_SOURCE_BAD_RESPONSE"
                    else logging.WARNING,
                    provider=source.provider,
                    reason=error.code,
                )
                continue
            if quotes:
                self._mark_healthy(health_key)
                self.last_quote_provider = source.provider
                return quotes
        if last_error is not None:
            raise DomainError(last_error.code)
        raise DomainError("MARKET_DATA_UNAVAILABLE")

    def history(self, instrument: GlobalInstrument, window: int) -> list[GlobalBar]:
        last_error: DomainError | None = None
        for name in instrument.history_sources:
            source = self._history_sources.get(name)
            if source is None:
                continue
            health_key = f"history:{name}"
            if not self._provider_available(health_key):
                continue
            try:
                bars = source.history(instrument, window)
            except DomainError as error:
                if error.code not in _DEGRADABLE_CODES:
                    raise
                last_error = error
                self._mark_degraded(health_key, error.code)
                log_event(
                    "market.global_history_provider_degraded",
                    level=logging.ERROR
                    if error.code == "MARKET_SOURCE_BAD_RESPONSE"
                    else logging.WARNING,
                    provider=name,
                    instrument=instrument.key,
                    reason=error.code,
                )
                continue
            if not bars:
                continue
            self._mark_healthy(health_key)
            self.last_history_providers[instrument.key] = source.provider
            return bars
        if last_error is not None:
            raise DomainError(last_error.code)
        raise DomainError("MARKET_DATA_UNAVAILABLE")

    def _provider_available(self, provider: str) -> bool:
        now = time.monotonic()
        with self._health_lock:
            until = self._provider_cooldown_until.get(provider)
            if until is None:
                return True
            if until <= now:
                self._provider_cooldown_until.pop(provider, None)
                return True
            return False

    def _mark_degraded(self, provider: str, code: str) -> None:
        if code not in _SOURCE_FAILURE_CODES:
            return
        with self._health_lock:
            self._provider_cooldown_until[provider] = time.monotonic() + _PROVIDER_COOLDOWN_SECONDS

    def _mark_healthy(self, provider: str) -> None:
        with self._health_lock:
            self._provider_cooldown_until.pop(provider, None)


__all__ = ["GLOBAL_INSTRUMENTS", "GlobalMarketSource"]
