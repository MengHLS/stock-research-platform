"""Market data orchestration: provider selection, caching and response shaping.

No database write happens here: intraday bars and auction snapshots are public,
point-in-time data and are deliberately not persisted yet (docs/decisions.md
D13). They live in a bounded TTL cache so repeated page views do not hammer the
public endpoints. A research run that needs reproducible inputs must freeze them
into the dataset pipeline when that module exists, not treat this cache as a
record.

Validation and error mapping belong to the providers; this layer decides which
provider serves a request, what is cached and how the result is presented.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from research_platform.core.cache import TTLCache
from research_platform.core.config import Settings
from research_platform.core.errors import DomainError
from research_platform.core.logging import log_event
from research_platform.core.upstream import UpstreamClient

from .eastmoney import AuctionResult, EastmoneySource
from .global_source import GlobalMarketSource
from .global_types import GLOBAL_INSTRUMENTS
from .market_time import CONTINUOUS_END, MARKET_TZ, at_market_clock, exchange_now, session_phase
from .models import GlobalMarketDailyBar, GlobalMarketQuoteSnapshot, utc_now
from .parsing import parse_day
from .schemas import (
    AuctionRead,
    AuctionSnapshotRead,
    BarRead,
    DailyBarRead,
    DailySeries,
    GlobalMarketBarRead,
    GlobalMarketIssueRead,
    GlobalMarketItemRead,
    GlobalMarketOverviewRead,
    GlobalMarketQuoteRead,
    IntradaySeries,
    KlinePeriod,
    MarketKlineBarRead,
    MarketKlineSeriesRead,
    QuoteRead,
    SourceStatus,
    SourceStatusList,
    StockProfileRead,
)
from .sina import SinaSource
from .symbols import parse_symbol, tencent_volume_unit
from .tencent import PERIOD_MINUTES, TencentSource
from .tencent_quote import TencentQuoteSource
from .tushare import TushareSource

SOURCE_NOTES = {
    "tencent": "分钟K线单次最多约800根；无北交所覆盖；09:30 分钟线只含开盘集合竞价。",
    "sina": (
        "新浪分钟线首行为 09:25 集合竞价成交，成交量在沪深北/科创/ETF/指数上均为精确股数；"
        "无 09:15–09:25 虚拟撮合曲线。"
    ),
    "sina_auction": (
        "降级结果：东方财富竞价曲线不可用时，仅用新浪分钟线取 09:25 集合竞价成交（股数为精确值），"
        "无 09:15–09:25 虚拟撮合曲线。"
    ),
    "tencent_auction": (
        "最后降级：新浪也不可用时才用腾讯分笔取 09:25 集合竞价成交，"
        "科创板股数按整手换算或取 09:30 分钟线，pre_close 缺失。"
    ),
    "eastmoney": (
        "竞价快照为 09:15–09:25 虚拟撮合曲线；09:25 后给出实际成交结果。"
        "成交量为整手口径，科创板(688/689)股数与 09:30 分钟线可能相差不足 100 股，金额为准。"
        "该源有反爬，连续请求可能被拒，届时接口降级为新浪单笔竞价成交。"
    ),
    "tushare": "日线用于对账与历史；权限与频率限制由 Tushare 账号决定。",
}

# A full A-share session is 241 one-minute bars; scan a whole day (the endpoint
# caps at ~800) so the 09:30 auction bar is inside any returned window.
_OPENING_BAR_SCAN = 800

# Sources that only degrade the auction response instead of failing it.
#
# ``MARKET_SOURCE_BAD_RESPONSE`` is included on purpose: Eastmoney is a
# best-effort curve source and its parser breaking must not take down the whole
# auction endpoint while Sina can still return the matched trade. The trade-off
# is that a silent format change would otherwise look like success, so a
# BAD_RESPONSE degradation is logged at ERROR (a code/format problem) and a
# transport failure at WARNING (a network problem), and both stay visible in
# the response ``limits`` field.
_DEGRADABLE_CODES = frozenset({"MARKET_SOURCE_UNAVAILABLE", "MARKET_SOURCE_BAD_RESPONSE"})
# Degradation causes that indicate a broken parser rather than a flaky network.
_FORMAT_BREAKAGE_CODES = frozenset({"MARKET_SOURCE_BAD_RESPONSE"})
_GLOBAL_HISTORY_WINDOW = 120


class MarketService:
    def __init__(
        self,
        settings: Settings,
        client: UpstreamClient,
        *,
        cache: TTLCache | None = None,
        global_source: GlobalMarketSource | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache if cache is not None else TTLCache()
        self._tencent = TencentSource(client)
        self._quotes = TencentQuoteSource(client)
        self._eastmoney = EastmoneySource(client)
        self._global = global_source or GlobalMarketSource(client)
        self._global_refresh_lock = threading.Lock()
        self._sina = SinaSource(client)
        self._tushare = TushareSource(client, settings.tushare)

    @property
    def cache(self) -> TTLCache:
        return self._cache

    def intraday(self, raw_symbol: str, period: str, limit: int) -> IntradaySeries:
        symbol = parse_symbol(raw_symbol)
        if period not in PERIOD_MINUTES:
            raise DomainError("MARKET_SYMBOL_INVALID", "不支持的分钟周期。")
        key = ("intraday", symbol.display, period, limit)

        def load() -> IntradaySeries:
            bars = self._tencent.intraday(symbol, period, limit)
            return IntradaySeries(
                symbol=symbol.display,
                period=period,
                bars=[
                    BarRead(
                        start=bar.start,
                        trading_day=bar.trading_day,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume_shares=bar.volume_shares,
                    )
                    for bar in bars
                ],
                total=len(bars),
                limits=[SOURCE_NOTES["tencent"]],
            )

        return self._cache.get_or_create(key, self._settings.upstream.intraday_cache_seconds, load)

    def kline(self, raw_symbol: str, period: KlinePeriod, limit: int) -> MarketKlineSeriesRead:
        symbol = parse_symbol(raw_symbol)
        key = ("kline", symbol.display, period, limit)

        def load() -> MarketKlineSeriesRead:
            bars = self._tencent.kline(symbol, period, limit)
            latest = bars[-1].trading_day if bars else None
            current_time = exchange_now()
            current = current_time.date()
            week_in_progress = bool(
                period == "week"
                and latest is not None
                and latest.isocalendar()[:2] == current.isocalendar()[:2]
                and (
                    current_time.isoweekday() < 5
                    or (
                        current_time.isoweekday() == 5
                        and current_time.strftime("%H:%M") < CONTINUOUS_END
                    )
                )
            )
            limits = ["腾讯日/周 K 为不复权价格。"]
            if week_in_progress:
                limits.append("最后一周尚未收周，周 bar 会随交易日更新。")
            return MarketKlineSeriesRead(
                symbol=symbol.display,
                period=period,
                bars=[
                    MarketKlineBarRead(
                        trading_day=bar.trading_day,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume_shares=bar.volume_shares,
                    )
                    for bar in bars
                ],
                total=len(bars),
                week_in_progress=week_in_progress,
                limits=limits,
            )

        return self._cache.get_or_create(key, self._settings.upstream.kline_cache_seconds, load)

    def auction(self, raw_symbol: str) -> AuctionRead:
        """Opening auction: the 09:15–09:25 curve when Eastmoney answers, else the match.

        Eastmoney is behind an anti-scraping filter and refuses bursts of requests.
        Falling back to the Tencent 09:25 trade keeps the matched result available
        while explicitly marking the response degraded: an empty curve is never
        presented as "no auction".
        """
        symbol = parse_symbol(raw_symbol)
        key = ("auction", symbol.display)

        def load() -> AuctionRead:
            try:
                return self._complete_auction(symbol)
            except DomainError as error:
                if error.code not in _DEGRADABLE_CODES:
                    raise
                # A degraded response must not look like a normal one in the
                # logs: a parser/format break is a defect signal, a transport
                # failure is routine. Both remain visible in ``limits``.
                log_event(
                    "market.auction_degraded",
                    level=logging.ERROR
                    if error.code in _FORMAT_BREAKAGE_CODES
                    else logging.WARNING,
                    provider="eastmoney",
                    symbol=symbol.display,
                    reason=error.code,
                )
                return self._degraded_auction(symbol, error.code)

        return self._cache.get_or_create(key, self._settings.upstream.quote_cache_seconds, load)

    def _complete_auction(self, symbol) -> AuctionRead:
        """Eastmoney curve plus the matched result.

        The curve and the match both come from Eastmoney when it answers. The
        matched *volume* is taken from Sina when Eastmoney is reachable only for
        part of the request, because Sina reports exact shares on every board.
        """
        result = self._eastmoney.opening_auction(symbol)
        return AuctionRead(
            symbol=symbol.display,
            trading_day=_trading_day(result),
            provider="eastmoney",
            phase=session_phase(),
            pre_close=result.pre_close,
            snapshots=[
                AuctionSnapshotRead(time=item.time, price=item.price) for item in result.snapshots
            ],
            matched_time=result.matched_time,
            matched_price=result.matched_price,
            matched_volume_shares=result.volume_shares,
            matched_amount=result.amount,
            limits=self._stale_note(_trading_day(result)) + [SOURCE_NOTES["eastmoney"]],
        )

    def _degraded_auction(self, symbol, reason: str) -> AuctionRead:
        """No virtual curve available: report the matched trade from Sina.

        Sina reports the 09:25 matched trade with exact shares on every board,
        so the degradation still answers "what matched" and only loses the
        09:15–09:25 curve. The Tencent per-trade detail is the last fallback for
        symbols Sina does not serve. Both paths mark ``degraded`` explicitly.
        """
        notes = [SOURCE_NOTES["sina_auction"], f"降级原因：{reason}"]
        try:
            match = self._sina.opening_auction(symbol)
        except DomainError as error:
            if error.code not in _DEGRADABLE_CODES:
                raise
            return self._tencent_auction_fallback(symbol, reason, error.code)
        return AuctionRead(
            symbol=symbol.display,
            trading_day=match.trading_day,
            provider="sina",
            degraded=True,
            phase=session_phase(),
            pre_close=match.pre_close,
            snapshots=[],
            matched_time=match.matched_time,
            matched_price=match.price,
            matched_volume_shares=match.volume_shares,
            matched_amount=match.amount,
            limits=self._stale_note(match.trading_day) + notes,
        )

    def _tencent_auction_fallback(self, symbol, reason: str, sina_reason: str) -> AuctionRead:
        trading_day = self._latest_trading_day(symbol)
        trade = self._tencent.opening_auction(symbol, trading_day)
        if trade is None:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        volume_shares = trade.volume_shares
        notes = [
            SOURCE_NOTES["tencent_auction"],
            f"降级原因：{reason}",
            f"新浪不可用：{sina_reason}",
        ]
        if tencent_volume_unit(symbol) == "shares":
            # STAR trades are quoted in whole 手 in the detail list, so the exact
            # share count is the 09:30 minute bar (which holds only the auction).
            exact = self._opening_bar_volume(symbol, trading_day)
            if exact is not None:
                volume_shares = exact
                notes.append("科创板成交股数取自 09:30 分钟线（仅含集合竞价），比整手换算精确。")
        matched_time = at_market_clock(trading_day, trade.clock)
        return AuctionRead(
            symbol=symbol.display,
            trading_day=trading_day,
            provider="tencent",
            degraded=True,
            phase=session_phase(),
            pre_close=None,
            snapshots=[],
            matched_time=matched_time,
            matched_price=trade.price,
            matched_volume_shares=volume_shares,
            matched_amount=trade.amount,
            limits=self._stale_note(trading_day) + notes,
        )

    @staticmethod
    def _stale_note(trading_day: date) -> list[str]:
        """Flag a result that belongs to an earlier session than the exchange clock.

        Both auction sources name the last *traded* session, which on a trading
        morning before 09:25 is the previous day. Returning that row as if it were
        today's auction would be wrong; dropping it would claim "no auction" for a
        day that has not opened yet. The honest answer is to keep the data and say
        so, so a client can label it instead of misreading it.
        """
        today = exchange_now().date()
        if trading_day < today:
            return [
                f"该竞价属于 {trading_day.isoformat()} 交易日，早于当前交易所日期 "
                f"{today.isoformat()}（盘前或非交易日）；不是今日竞价。"
            ]
        return []

    def _latest_trading_day(self, symbol) -> date:
        bars = self._tencent.intraday(symbol, "m1", 1)
        return bars[-1].trading_day

    def _opening_bar_volume(self, symbol, trading_day) -> str | None:
        """Exact auction volume from the 09:30 one-minute bar, when it applies.

        Only the STAR boards need this (the Tencent detail list rounds to whole
        手); for other boards the detail list and the bar already agree, so no
        extra request is made. A missing bar leaves the caller on the rounded value.

        The window must cover a whole session: the endpoint returns the *latest*
        bars, so asking for two returns the closing minutes after 15:00 and the
        09:30 bar is never found. ``_OPENING_BAR_SCAN`` is a full trading day.
        """
        try:
            bars = self._tencent.intraday(symbol, "m1", _OPENING_BAR_SCAN)
        except DomainError:
            return None
        for bar in reversed(bars):
            if (
                bar.trading_day == trading_day
                and bar.start.astimezone(MARKET_TZ).strftime("%H:%M") == "09:30"
            ):
                return bar.volume_shares
        return None

    def daily(self, raw_symbol: str, start: date | None, end: date | None) -> DailySeries:
        symbol = parse_symbol(raw_symbol)
        today = datetime.now(MARKET_TZ).date()
        end_date = end or today
        start_date = start or (end_date - timedelta(days=30))
        if start_date > end_date:
            raise DomainError("MARKET_SYMBOL_INVALID", "开始日期不能晚于结束日期。")
        if (end_date - start_date).days > 3660:
            raise DomainError("MARKET_SYMBOL_INVALID", "日线一次最多查询十年。")
        bars = self._tushare.daily(
            symbol,
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
        )
        return DailySeries(
            symbol=symbol.display,
            bars=[
                DailyBarRead(
                    trading_day=parse_day(bar.trading_day, "%Y%m%d"),
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume_shares=bar.volume_shares,
                    amount=bar.amount,
                )
                for bar in bars
            ],
            total=len(bars),
        )

    def quote(self, raw_symbol: str) -> QuoteRead:
        """Real-time snapshot (Tencent): prices, limits and the provider clock.

        The quote is the only source that works for every board including BSE and
        for indices, so it is also the reliable way to read the market during the
        09:15–09:25 auction window when Eastmoney's curve source refuses requests.
        """
        symbol = parse_symbol(raw_symbol)
        key = ("quote", symbol.display)

        def load() -> QuoteRead:
            snapshot = self._quotes.quote(symbol)
            return QuoteRead(
                symbol=snapshot.symbol,
                name=snapshot.name,
                price=snapshot.price,
                previous_close=snapshot.previous_close,
                open=snapshot.open,
                high=snapshot.high,
                low=snapshot.low,
                quote_time=snapshot.quote_time,
                change_pct=snapshot.change_pct,
                volume_lots=snapshot.volume_lots,
                amount=snapshot.amount,
                turnover_pct=snapshot.turnover_pct,
                limit_up=snapshot.limit_up,
                limit_down=snapshot.limit_down,
                phase=session_phase(),
            )

        return self._cache.get_or_create(key, self._settings.upstream.quote_cache_seconds, load)

    def stock_profile(self, raw_symbol: str) -> StockProfileRead:
        """Static identity and industry classification for a stock detail view."""
        symbol = parse_symbol(raw_symbol)
        key = ("stock-profile", symbol.display)

        def load() -> StockProfileRead:
            profile = self._eastmoney.stock_profile(symbol)
            return StockProfileRead(
                symbol=symbol.display,
                name=profile.name,
                industry=profile.industry,
            )

        return self._cache.get_or_create(key, self._settings.upstream.profile_cache_seconds, load)

    def global_overview(self, session: Session, window: int) -> GlobalMarketOverviewRead:
        """Read the application snapshot, refreshing it when it is stale.

        The database is the availability boundary: a provider outage can only
        leave the page on a marked older snapshot, not erase previously saved
        quotes and daily bars.
        """
        if window not in {20, 60, 120}:
            raise DomainError("REQUEST_INVALID")

        last_synced = self._global_last_synced(session)
        if self._global_is_fresh(last_synced):
            return self._read_global_snapshot(session, window, stale=False)

        if not self._global_refresh_lock.acquire(blocking=False):
            session.rollback()
            last_synced = self._global_last_synced(session)
            if last_synced is None:
                raise DomainError("MARKET_SOURCE_UNAVAILABLE")
            return self._read_global_snapshot(
                session,
                window,
                stale=not self._global_is_fresh(last_synced),
            )
        try:
            last_synced = self._global_last_synced(session)
            if self._global_is_fresh(last_synced):
                return self._read_global_snapshot(session, window, stale=False)
            try:
                history_failures = self._refresh_global_snapshot(session)
            except DomainError as error:
                session.rollback()
                if last_synced is None:
                    raise
                log_event(
                    "market.global_snapshot_fallback",
                    level=(
                        logging.ERROR if error.code in _FORMAT_BREAKAGE_CODES else logging.WARNING
                    ),
                    provider=getattr(self._global, "last_quote_provider", "global"),
                    reason=error.code,
                )
                return self._read_global_snapshot(session, window, stale=True)
            return self._read_global_snapshot(
                session,
                window,
                stale=False,
                history_failures=history_failures,
            )
        finally:
            self._global_refresh_lock.release()

    def _refresh_global_snapshot(self, session: Session) -> set[str]:
        quotes = self._global.quotes()
        if not quotes:
            raise DomainError("MARKET_DATA_UNAVAILABLE")
        fetched_at = utc_now()

        for instrument in GLOBAL_INSTRUMENTS:
            quote = quotes.get(instrument.key)
            if quote is not None:
                row = session.get(GlobalMarketQuoteSnapshot, instrument.key)
                if row is None:
                    row = GlobalMarketQuoteSnapshot(
                        instrument_key=instrument.key,
                        price=quote.price,
                        provider=quote.provider,
                        fetched_at=fetched_at,
                    )
                    session.add(row)
                row.price = quote.price
                row.previous_close = quote.previous_close
                row.open = quote.open
                row.high = quote.high
                row.low = quote.low
                row.change = quote.change
                row.change_pct = quote.change_pct
                row.quote_time = _naive_utc(quote.quote_time)
                row.provider = quote.provider
                row.fetched_at = fetched_at
        # Persist quotes before the slower history fan-out. Concurrent readers can
        # use a fresh quote snapshot even if some history providers time out.
        session.commit()

        refresh_instruments = [
            instrument
            for instrument in GLOBAL_INSTRUMENTS
            if self._global_history_needs_refresh(session, instrument.key)
        ]
        if not refresh_instruments:
            return set()

        history_failures: set[str] = set()
        workers = min(
            self._settings.upstream.global_history_workers,
            len(refresh_instruments),
        )
        executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="global-history",
        )
        futures = {
            executor.submit(self._load_global_history, instrument): instrument
            for instrument in refresh_instruments
        }
        try:
            try:
                for future in as_completed(
                    futures,
                    timeout=self._settings.upstream.global_history_sync_timeout_seconds,
                ):
                    instrument = futures[future]
                    try:
                        bars = future.result()
                    except DomainError as error:
                        self._log_global_history_failure(instrument, error.code)
                        history_failures.add(instrument.key)
                        continue
                    self._store_global_bars(session, instrument.key, bars, fetched_at)
            except FuturesTimeoutError:
                for future, instrument in futures.items():
                    if future.done():
                        continue
                    history_failures.add(instrument.key)
                    self._log_global_history_failure(
                        instrument,
                        "GLOBAL_HISTORY_SYNC_BUDGET_EXCEEDED",
                    )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            session.commit()
        return history_failures

    def _load_global_history(self, instrument):
        return self._global.history(instrument, _GLOBAL_HISTORY_WINDOW)

    def _store_global_bars(
        self,
        session: Session,
        instrument_key: str,
        bars,
        fetched_at: datetime,
    ) -> None:
        for bar in bars:
            row = session.get(GlobalMarketDailyBar, (instrument_key, bar.trading_day))
            if row is None:
                row = GlobalMarketDailyBar(
                    instrument_key=instrument_key,
                    trading_day=bar.trading_day,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    fetched_at=fetched_at,
                )
                session.add(row)
            row.open = bar.open
            row.high = bar.high
            row.low = bar.low
            row.close = bar.close
            row.change_pct = bar.change_pct
            row.fetched_at = fetched_at

    def _log_global_history_failure(self, instrument, reason: str) -> None:
        log_event(
            "market.global_history_degraded",
            level=logging.ERROR if reason in _FORMAT_BREAKAGE_CODES else logging.WARNING,
            provider=getattr(self._global, "last_history_providers", {}).get(
                instrument.key, "global"
            ),
            instrument=instrument.key,
            reason=reason,
        )

    def _read_global_snapshot(
        self,
        session: Session,
        window: int,
        *,
        stale: bool,
        history_failures: set[str] | frozenset[str] = frozenset(),
    ) -> GlobalMarketOverviewRead:
        snapshots = {
            row.instrument_key: row
            for row in session.scalars(select(GlobalMarketQuoteSnapshot)).all()
        }
        bars_by_key: dict[str, list[GlobalMarketDailyBar]] = {}
        for row in session.scalars(
            select(GlobalMarketDailyBar).order_by(
                GlobalMarketDailyBar.instrument_key,
                GlobalMarketDailyBar.trading_day,
            )
        ).all():
            bars_by_key.setdefault(row.instrument_key, []).append(row)

        items: list[GlobalMarketItemRead] = []
        latest_fetched = max(
            (row.fetched_at for row in snapshots.values()),
            default=None,
        )
        for instrument in GLOBAL_INSTRUMENTS:
            snapshot = snapshots.get(instrument.key)
            issues: list[GlobalMarketIssueRead] = []
            if snapshot is None:
                issues.append(
                    GlobalMarketIssueRead(
                        code="quote_missing",
                        scope=instrument.key,
                        message="数据库中尚无该标的的报价快照。",
                    )
                )
            saved_bars = bars_by_key.get(instrument.key, [])[-window:]
            if not saved_bars:
                issues.append(
                    GlobalMarketIssueRead(
                        code="history_missing",
                        scope=instrument.key,
                        message="数据库中尚无该标的的日线快照。",
                    )
                )
            quote_is_stale = (
                snapshot is not None
                and latest_fetched is not None
                and snapshot.fetched_at < latest_fetched
            )
            if quote_is_stale:
                issues.append(
                    GlobalMarketIssueRead(
                        code="quote_stale",
                        scope=instrument.key,
                        message="本次刷新未返回该标的，当前价格来自较早快照。",
                    )
                )
            history_is_stale = instrument.key in history_failures
            if snapshot is not None and saved_bars and history_is_stale:
                issues.append(
                    GlobalMarketIssueRead(
                        code="history_stale",
                        scope=instrument.key,
                        message="报价已更新，但日线仍为较早快照。",
                    )
                )
            if snapshot is not None and saved_bars and not (quote_is_stale or history_is_stale):
                assessment = "available"
            elif snapshot is not None or saved_bars:
                assessment = "partial"
            else:
                assessment = "missing"
            items.append(
                GlobalMarketItemRead(
                    key=instrument.key,
                    name=instrument.name,
                    symbol=instrument.symbol,
                    group=instrument.group,
                    market=instrument.market,
                    currency=instrument.currency,
                    unit=instrument.unit,
                    precision=instrument.precision,
                    provider=snapshot.provider if snapshot is not None else None,
                    assessment=assessment,
                    quote=(
                        GlobalMarketQuoteRead(
                            price=_quantize(snapshot.price, instrument.precision),
                            previous_close=_quantize(snapshot.previous_close, instrument.precision),
                            open=_quantize(snapshot.open, instrument.precision),
                            high=_quantize(snapshot.high, instrument.precision),
                            low=_quantize(snapshot.low, instrument.precision),
                            change=_quantize(snapshot.change, instrument.precision),
                            change_pct=_quantize(snapshot.change_pct, 2),
                            quote_time=_aware_utc(snapshot.quote_time),
                        )
                        if snapshot is not None
                        else None
                    ),
                    bars=[
                        GlobalMarketBarRead(
                            date=bar.trading_day,
                            open=_quantize(bar.open, instrument.precision),
                            high=_quantize(bar.high, instrument.precision),
                            low=_quantize(bar.low, instrument.precision),
                            close=_quantize(bar.close, instrument.precision),
                            change_pct=_quantize(bar.change_pct, 2),
                        )
                        for bar in saved_bars
                    ],
                    issues=issues,
                )
            )

        quote_times = [
            item.quote.quote_time
            for item in items
            if item.quote is not None and item.quote.quote_time is not None
        ]
        fetched_times = [row.fetched_at for row in snapshots.values()]
        quote_providers = {row.provider for row in snapshots.values()}
        provider = (
            next(iter(quote_providers))
            if len(quote_providers) == 1 and quote_providers <= {"sina", "yahoo", "eastmoney"}
            else "mixed"
        )
        return GlobalMarketOverviewRead(
            provider=provider,
            as_of=max(quote_times) if quote_times else None,
            last_synced_at=_aware_utc(max(fetched_times) if fetched_times else None),
            stale=stale,
            window_requested=window,
            items=items,
            methodology=(
                "报价与日线为供应商原始数据，不复权、不补缺失日；"
                "中韩半导体使用 513310 ETF 作为可交易代理。"
            ),
        )

    def _global_last_synced(self, session: Session) -> datetime | None:
        return session.scalar(select(func.max(GlobalMarketQuoteSnapshot.fetched_at)))

    def _global_is_fresh(self, last_synced: datetime | None) -> bool:
        if last_synced is None:
            return False
        cutoff = utc_now() - timedelta(
            seconds=self._settings.upstream.global_overview_refresh_seconds
        )
        return last_synced >= cutoff

    def _global_history_needs_refresh(self, session: Session, instrument_key: str) -> bool:
        last_synced = session.scalar(
            select(func.max(GlobalMarketDailyBar.fetched_at)).where(
                GlobalMarketDailyBar.instrument_key == instrument_key
            )
        )
        if last_synced is None:
            return True
        cutoff = utc_now() - timedelta(
            seconds=self._settings.upstream.global_history_refresh_seconds
        )
        return last_synced < cutoff

    def sources(self) -> SourceStatusList:
        return SourceStatusList(
            items=[
                SourceStatus(
                    name="tencent",
                    configured=True,
                    capabilities=[
                        "quote",
                        "intraday_kline",
                        "daily_weekly_kline",
                        "opening_auction_fallback",
                    ],
                    note=SOURCE_NOTES["tencent"],
                ),
                SourceStatus(
                    name="sina",
                    configured=True,
                    capabilities=["opening_auction_match"],
                    note=SOURCE_NOTES["sina"],
                ),
                SourceStatus(
                    name="eastmoney",
                    configured=True,
                    capabilities=["opening_auction"],
                    note=SOURCE_NOTES["eastmoney"],
                ),
                SourceStatus(
                    name="tushare",
                    configured=self._tushare.configured,
                    capabilities=["daily_kline"],
                    note=SOURCE_NOTES["tushare"],
                ),
            ],
            upstream_enabled=self._settings.upstream.enabled,
        )


def _trading_day(result: AuctionResult) -> date:
    moments = [item.time for item in result.snapshots]
    if result.matched_time is not None:
        moments.append(result.matched_time)
    if not moments:
        raise DomainError("MARKET_DATA_UNAVAILABLE")
    return max(moments).astimezone(MARKET_TZ).date()


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _quantize(value: Decimal | None, precision: int) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(1).scaleb(-precision))
