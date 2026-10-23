"""Post-close refresh of derived daily limit counts.

The refresh is idempotent: it recomputes the most recent closed trading days from
the read-only source and upserts them into the application table. A scheduler
thread inside the API process keeps catching up on missing or incomplete days;
the same service powers the manual backfill command.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from research_platform.core.config import ReviewCountsConfig
from research_platform.core.errors import DomainError
from research_platform.core.logging import log_event

from .market_time import exchange_now
from .review_counts import COVERAGE_DERIVED, LimitCounts, MarketCountsSource, compute_daily_counts
from .review_counts_store import ReviewCountsStore, ReviewCountsStoreError


@dataclass(frozen=True)
class RefreshResult:
    trading_days: tuple[date, ...]
    latest_trading_day: date | None
    skipped_days: tuple[date, ...]
    empty: bool


class ReviewCountsService:
    def __init__(
        self,
        source: MarketCountsSource | None,
        store: ReviewCountsStore,
        config: ReviewCountsConfig,
        *,
        lookback_days: int = 400,
    ) -> None:
        self._source = source
        self._store = store
        self._config = config
        self._lookback_days = lookback_days

    @property
    def store(self) -> ReviewCountsStore:
        return self._store

    def closed_cutoff(self, now: datetime) -> date:
        """Last calendar date whose session is already closed at ``now``."""

        close = (self._config.after_close_hour, self._config.after_close_minute)
        if (now.hour, now.minute) >= close:
            return now.date()
        return now.date() - timedelta(days=1)

    def latest_eligible_day(self, now: datetime) -> date | None:
        """Latest source trading day that may be derived at ``now``."""

        source = self._source_or_fail()
        cutoff = self.closed_cutoff(now)
        days = source.trading_days(cutoff - timedelta(days=self._lookback_days), cutoff)
        return days[-1] if days else None

    def refresh(
        self,
        *,
        as_of: date | None = None,
        days: int | None = None,
        now: datetime | None = None,
    ) -> RefreshResult:
        source = self._source_or_fail()
        current = now or exchange_now()
        # Never derive today's incomplete session. An explicit past date stays
        # authoritative for manual backfill; otherwise advance to the last close.
        if as_of is not None and as_of < current.date():
            cutoff = as_of
        else:
            cutoff = self.closed_cutoff(current)
        target_days = days or self._config.backfill_days
        calendar = source.trading_days(
            cutoff - timedelta(days=self._lookback_days),
            cutoff,
        )
        if not calendar:
            return RefreshResult((), None, (), True)
        effective_as_of = calendar[-1]
        targets = calendar[-target_days:]
        metadata = source.security_metadata()
        existing = self._store.counts(targets[0], targets[-1])
        computed: list[LimitCounts] = []
        skipped: list[date] = []
        for trading_day in targets:
            bars = source.daily_bars(trading_day)
            if not bars:
                skipped.append(trading_day)
                continue
            item = compute_daily_counts(trading_day, bars, metadata, calendar)
            previous = existing.get(trading_day)
            if previous is not None and (
                item.rule_known_bar_count < previous.rule_known_bar_count
                or (
                    previous.coverage_status == COVERAGE_DERIVED
                    and item.coverage_status != COVERAGE_DERIVED
                )
            ):
                skipped.append(trading_day)
                continue
            computed.append(item)
        stored = self._store.upsert(computed)
        latest_stored = self._store.latest_trading_day()
        log_event(
            "market.review_counts_refreshed",
            source="source_db",
            as_of=effective_as_of.isoformat(),
            refreshed=stored,
            skipped=len(skipped),
            latest_trading_day=latest_stored.isoformat() if latest_stored else None,
        )
        return RefreshResult(
            trading_days=tuple(item.trading_day for item in computed),
            latest_trading_day=effective_as_of,
            skipped_days=tuple(skipped),
            empty=not computed,
        )

    def status(self) -> dict[str, object]:
        latest = self._store.latest_trading_day()
        return {
            "latest_trading_day": latest.isoformat() if latest else None,
            "backfill_days": self._config.backfill_days,
            "enabled": self._config.enabled,
        }

    def _source_or_fail(self) -> MarketCountsSource:
        if self._source is None:
            raise DomainError("SOURCE_NOT_CONFIGURED")
        return self._source


class ReviewCountsScheduler:
    """Catch up missing days, then keep retrying late or incomplete source data.

    A day is eligible only after its session closed. Weekends and holidays do not
    block catch-up: the scheduler compares the stored latest day with the latest
    *closed* source day, not with today's date.
    """

    def __init__(
        self,
        service: ReviewCountsService,
        config: ReviewCountsConfig,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._config = config
        self._now = now or exchange_now
        self._last_partial_attempt: datetime | None = None

    def due(self) -> bool:
        if not self._config.enabled:
            return False
        now = self._now()
        try:
            eligible = self._service.latest_eligible_day(now)
            if eligible is None:
                return False
        except (DomainError, ReviewCountsStoreError):
            return False
        # Source row presence cannot establish ingestion completion. Recompute
        # the correction window every interval, including weekends and restarts.
        if self._last_partial_attempt is not None:
            interval = timedelta(seconds=self._config.refresh_interval_seconds)
            if now - self._last_partial_attempt < interval:
                return False
        return True

    def run_if_due(self) -> bool:
        if not self.due():
            return False
        now = self._now()
        try:
            self._service.refresh(now=now)
        except (DomainError, ReviewCountsStoreError) as error:
            log_event(
                "market.review_counts_refresh_failed",
                level=logging.WARNING,
                source="source_db",
                reason=getattr(error, "code", type(error).__name__),
            )
            self._last_partial_attempt = now
            return False
        latest = self._service.store.latest_trading_day()
        if latest is not None and latest <= now.date():
            self._last_partial_attempt = now
        return True


def start_scheduler_thread(
    scheduler: ReviewCountsScheduler,
    stop_event: threading.Event,
    *,
    interval_seconds: int,
) -> threading.Thread:
    """Daemon thread for the composition root; waiting is interruptible."""

    def loop() -> None:
        while not stop_event.is_set():
            try:
                scheduler.run_if_due()
            except Exception as error:  # noqa: BLE001 - scheduler must survive one bad run
                log_event(
                    "market.review_counts_scheduler_failed",
                    level=logging.WARNING,
                    error_type=type(error).__name__,
                )
            if stop_event.wait(interval_seconds):
                return

    thread = threading.Thread(target=loop, name="market-review-counts", daemon=True)
    thread.start()
    return thread
