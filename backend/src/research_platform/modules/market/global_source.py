"""Provider failover for the cross-market overview."""

from __future__ import annotations

import logging

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

_DEGRADABLE_CODES = frozenset({"MARKET_SOURCE_UNAVAILABLE", "MARKET_SOURCE_BAD_RESPONSE"})


class GlobalMarketSource:
    """Use a batch quote source first and venue-specific history fallbacks."""

    def __init__(
        self,
        client: UpstreamClient,
        *,
        quote_sources=None,
        history_sources=None,
    ) -> None:
        self._quote_sources = quote_sources or (
            SinaGlobalSource(client),
            YahooGlobalSource(client),
            EastmoneyGlobalSource(client),
        )
        self._history_sources = history_sources or {
            "sina": SinaGlobalSource(client),
            "yahoo": YahooGlobalSource(client),
            "tencent": TencentGlobalSource(client),
            "naver": NaverGlobalSource(client),
            "yahoo_japan": YahooJapanGlobalSource(client),
            "eastmoney": EastmoneyGlobalSource(client),
        }
        self.last_quote_provider = "unknown"
        self.last_history_providers: dict[str, str] = {}

    def quotes(self) -> dict[str, GlobalQuote]:
        last_error: DomainError | None = None
        for source in self._quote_sources:
            try:
                quotes = source.quotes()
            except DomainError as error:
                if error.code not in _DEGRADABLE_CODES:
                    raise
                last_error = error
                log_event(
                    "market.global_quote_degraded",
                    level=logging.ERROR
                    if error.code == "MARKET_SOURCE_BAD_RESPONSE"
                    else logging.WARNING,
                    provider=source.provider,
                    reason=error.code,
                )
                continue
            if not quotes:
                continue
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
            try:
                bars = source.history(instrument, window)
            except DomainError as error:
                if error.code not in _DEGRADABLE_CODES:
                    raise
                last_error = error
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
            self.last_history_providers[instrument.key] = source.provider
            return bars
        if last_error is not None:
            raise DomainError(last_error.code)
        raise DomainError("MARKET_DATA_UNAVAILABLE")


__all__ = ["GLOBAL_INSTRUMENTS", "GlobalMarketSource"]
