"""Market module: symbol rules, provider parsing, units, cache and failure mapping.

No test reaches the public internet: every provider call goes through an
``httpx2.MockTransport`` wired into the shared UpstreamClient, so the assertions
are about our contract, not about a vendor being reachable.
"""

import json
from datetime import date, timedelta

import httpx2 as httpx
import pytest

from research_platform.core.cache import TTLCache
from research_platform.core.config import Settings
from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient
from research_platform.modules.market.eastmoney import EastmoneySource
from research_platform.modules.market.service import MarketService
from research_platform.modules.market.symbols import parse_symbol, tencent_volume_unit
from research_platform.modules.market.tencent import TencentSource
from research_platform.modules.market.tushare import TushareSource


def settings(**overrides):
    values = {
        "environment": "test",
        "database_url": "sqlite://",
        "_env_file": None,
        "upstream": {"min_interval_ms": 0, "max_retries": 1},
    }
    values.update(overrides)
    return Settings(**values)


def make_service(routes, **overrides):
    """Build a MarketService whose HTTP calls are served by ``routes``.

    ``routes`` maps a URL path to either a body (str/bytes) or a callable
    ``(request) -> response`` so a test can inspect the outgoing query.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        target = routes.get(request.url.path)
        if target is None:
            raise AssertionError(f"unexpected upstream call: {request.url.path}")
        return target(request) if callable(target) else httpx.Response(200, text=target)

    client = UpstreamClient(settings(**overrides), transport=httpx.MockTransport(handler))
    return MarketService(settings(**overrides), client)


def kline_payload(symbol="sh600519", period="m1", bars=None):
    if bars is None:
        bars = [
            ["202610160930", "1311.57", "1311.57", "1311.57", "1311.57", "335.00", {}, "0.27"],
            ["202610160931", "1308.25", "1303.18", "1309.60", "1303.01", "1217.00", {}, "0.97"],
        ]
    return json.dumps({"code": 0, "msg": "", "data": {symbol: {period: bars, "prec": "1312.97"}}})


def trends_payload(rows, pre_close="1312.97"):
    return json.dumps({"data": {"preClose": pre_close, "trends": rows}})


def profile_payload(*, code="600519", name="贵州茅台", industry="白酒Ⅱ"):
    return json.dumps({"data": {"f57": code, "f58": name, "f127": industry}})


def auction_rows(*, with_match=True, star=False):
    virtual = [
        f"2026-10-16 09:{minute:02d},1312.97,1312.97,1312.97,1312.97,0,0.00,1312.970"
        for minute in (15, 16, 20, 25)
    ]
    if with_match:
        matched = (
            "2026-10-16 09:26,238.00,238.00,238.00,238.00,151,3599988.00,238.000"
            if star
            else "2026-10-16 09:26,1311.57,1311.57,1311.57,1311.57,335,43937595.00,1311.570"
        )
        return virtual + [matched]
    return virtual


# --- symbols ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "display", "ts_code", "secid"),
    [
        ("600519", "600519.SH", "600519.SH", "1.600519"),
        ("600519.SH", "600519.SH", "600519.SH", "1.600519"),
        ("sh600519", "600519.SH", "600519.SH", "1.600519"),
        ("SH600519", "600519.SH", "600519.SH", "1.600519"),
        ("000001.XSHE", "000001.SZ", "000001.SZ", "0.000001"),
        ("sz000001", "000001.SZ", "000001.SZ", "0.000001"),
        ("920982", "920982.BJ", "920982.BJ", "0.920982"),
        ("510300", "510300.SH", "510300.SH", "1.510300"),
        ("159915", "159915.SZ", "159915.SZ", "0.159915"),
    ],
)
def test_symbol_spellings_normalize_to_one_identity(raw, display, ts_code, secid):
    symbol = parse_symbol(raw)
    assert symbol.display == display
    assert symbol.ts_code == ts_code
    assert symbol.eastmoney_secid == secid


@pytest.mark.parametrize(
    "raw",
    ["", "60051", "6005191", "abcdef", "sh600519x"],
)
def test_malformed_symbols_are_refused(raw):
    with pytest.raises(DomainError) as failure:
        parse_symbol(raw)
    assert failure.value.code == "MARKET_SYMBOL_INVALID"


@pytest.mark.parametrize(
    "raw",
    [
        # SSE indices published under 000xxx collide with SZSE stocks; guessing
        # the exchange silently returned another instrument (000300 resolved to
        # a non-existent sz000300 and came back as "no data").
        "000001",
        "000300",
        "000016",
        "000905",
        "000852",
        "000010",
        "000688",
    ],
)
def test_ambiguous_index_codes_require_an_explicit_exchange(raw):
    with pytest.raises(DomainError) as failure:
        parse_symbol(raw)
    assert failure.value.code == "MARKET_SYMBOL_INVALID"


@pytest.mark.parametrize(
    ("raw", "display"),
    [
        ("sh000300", "000300.SH"),
        ("sh000016", "000016.SH"),
        ("sh000905", "000905.SH"),
        ("sh000001", "000001.SH"),
        ("sz000001", "000001.SZ"),
        ("sz399006", "399006.SZ"),
    ],
)
def test_explicit_exchange_resolves_index_codes(raw, display):
    assert parse_symbol(raw).display == display


@pytest.mark.parametrize("raw", ["399001", "399106", "399006"])
def test_szse_index_range_is_unambiguous_and_inferred(raw):
    """399xxx exists only on SZSE; refusing it forced callers to add a prefix."""
    assert parse_symbol(raw).display == f"{raw}.SZ"


def test_all_000xxx_is_szse_unless_it_is_a_known_sse_index():
    """000xxx is a real SZSE stock range, so "not a known SSE index" means SZSE.

    Only the codes in ``_SSE_INDEX_CODES`` are ambiguous; treating the whole range
    as unreviewed would reject legitimate SZSE stocks (000002 万科A etc.).
    """
    assert parse_symbol("000002").display == "000002.SZ"
    assert parse_symbol("000903").display == "000903.SZ"
    # The documented SSE index codes still require an explicit exchange.
    with pytest.raises(DomainError):
        parse_symbol("000300")


def test_shifted_symbols_do_not_lose_leading_zeros():
    assert parse_symbol("000001.sz").code == "000001"
    assert parse_symbol("002415").display == "002415.SZ"


def test_star_board_volume_unit_differs_from_other_boards():
    assert tencent_volume_unit(parse_symbol("688017")) == "shares"
    assert tencent_volume_unit(parse_symbol("689009")) == "shares"
    assert tencent_volume_unit(parse_symbol("600519")) == "lots"
    assert tencent_volume_unit(parse_symbol("300750")) == "lots"


# --- intraday -------------------------------------------------------------


def test_intraday_converts_lots_to_shares_and_utc(monkeypatch):
    routes = {"/appstock/app/kline/mkline": kline_payload()}
    service = make_service(routes)
    series = service.intraday("600519", "m1", 2)
    assert series.symbol == "600519.SH" and series.total == 2
    assert series.bars[0].start.isoformat() == "2026-10-16T01:30:00+00:00"
    assert series.bars[0].trading_day == date(2026, 10, 16)
    assert str(series.bars[0].open) == "1311.57"
    assert str(series.bars[0].volume_shares) == "33500"
    assert str(series.bars[1].volume_shares) == "121700"


def test_star_intraday_keeps_share_denominated_volume():
    payload = kline_payload(
        symbol="sh688017",
        bars=[["202610160930", "238.00", "238.00", "238.00", "238.00", "15126.00", {}, "0.83"]],
    )
    service = make_service({"/appstock/app/kline/mkline": payload})
    assert str(service.intraday("688017", "m1", 1).bars[0].volume_shares) == "15126"


def test_bse_symbol_reports_missing_coverage_instead_of_empty_success():
    service = make_service({})
    with pytest.raises(DomainError) as failure:
        service.intraday("920982", "m1", 10)
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"


def test_empty_provider_bar_list_is_not_reported_as_success():
    service = make_service({"/appstock/app/kline/mkline": kline_payload(bars=[])})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 10)
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"


def test_garbage_upstream_becomes_bad_response_not_empty_data():
    service = make_service({"/appstock/app/kline/mkline": "not json"})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 10)
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_non_finite_price_is_a_source_error_not_a_500():
    """Decimal accepts "nan"/"Infinity"; they must not reach Pydantic as a 500."""
    payload = kline_payload(
        bars=[["202610160930", "nan", "1311.57", "1311.57", "1311.57", "335", {}, "0"]]
    )
    service = make_service({"/appstock/app/kline/mkline": payload})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 1)
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_infinite_volume_is_rejected():
    payload = kline_payload(
        bars=[["202610160930", "1311.57", "1311.57", "1311.57", "1311.57", "Infinity", {}, "0"]]
    )
    service = make_service({"/appstock/app/kline/mkline": payload})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 1)
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_unsupported_period_is_a_request_error():
    service = make_service({})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m7", 10)
    assert failure.value.code == "MARKET_SYMBOL_INVALID"


def test_intraday_is_cached_and_the_cache_can_count_requests():
    calls = []

    def counting(request):
        calls.append(request.url.params["param"])
        return httpx.Response(200, text=kline_payload())

    service = make_service({"/appstock/app/kline/mkline": counting})
    service.intraday("600519", "m1", 2)
    service.intraday("600519", "m1", 2)
    assert calls == ["sh600519,m1,,2"]


def test_cache_ttl_is_respected():
    now = [1000.0]
    cache = TTLCache(clock=lambda: now[0])
    cache.set("k", "v", 5)
    assert cache.get("k") == "v"
    now[0] += 6
    assert cache.get("k") is None


def test_cache_does_not_store_failures():
    cache = TTLCache()

    def boom():
        raise DomainError("MARKET_SOURCE_UNAVAILABLE")

    with pytest.raises(DomainError):
        cache.get_or_create("k", 30, boom)
    assert len(cache) == 0


def test_concurrent_misses_fetch_upstream_only_once():
    """Two page loads hitting a cold cache must not double the upstream request.

    The public quote sources rate limit; a stampede is a real availability risk,
    so the collapse is asserted on the factory call count, not on timing.
    """
    import threading
    import time

    calls = []
    counter_lock = threading.Lock()
    started = threading.Event()

    def factory():
        with counter_lock:
            calls.append(1)
        started.set()
        time.sleep(0.3)
        return {"bars": []}

    cache = TTLCache()
    threads = [
        threading.Thread(target=lambda: cache.get_or_create("k", 30, factory)) for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    started.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=10)
    assert not any(thread.is_alive() for thread in threads)
    assert len(calls) == 1


def test_owner_rechecks_cache_after_acquiring_the_creation_lock():
    """A thread that lost the race must not refetch a key another thread just filled.

    Interleaving: this thread's first ``get()`` misses, another thread completes
    the fill and unregisters, then this thread becomes owner. Without a second
    check inside the lock it calls ``factory`` again.
    """
    import threading

    from research_platform.core.cache import TTLCache as CacheType

    calls = []
    gate = threading.Event()
    other_done = threading.Event()
    state = {}

    original_get = CacheType.get

    class InterleavingCache(CacheType):
        def get(self, key):
            value = original_get(self, key)
            if value is None and not state.get("hooked"):
                state["hooked"] = True
                gate.set()
                other_done.wait(5)
            return value

    cache = InterleavingCache()

    def factory():
        calls.append(threading.current_thread().name)
        return {"v": 1}

    def other():
        gate.wait(5)
        cache.get_or_create("k", 30, factory)
        other_done.set()

    thread = threading.Thread(target=other, name="other")
    thread.start()
    cache.get_or_create("k", 30, factory)
    thread.join(10)
    assert len(calls) == 1


def test_waiter_takes_over_when_the_owner_fails():
    """A failed fill is not cached: the next caller must be allowed to retry."""
    cache = TTLCache()
    with pytest.raises(DomainError):
        cache.get_or_create("k", 30, lambda: (_ for _ in ()).throw(DomainError("X")))
    assert cache.get_or_create("k", 30, lambda: "ok") == "ok"


def test_zero_ttl_does_not_deadlock_and_does_not_cache():
    cache = TTLCache()
    calls = []
    assert cache.get_or_create("k", 0, lambda: calls.append(1) or "v") == "v"
    assert cache.get_or_create("k", 0, lambda: calls.append(1) or "v") == "v"
    assert len(calls) == 2
    assert len(cache) == 0


def test_injected_cache_is_not_replaced_by_a_new_one():
    """An empty TTLCache is falsy (len 0); ``cache or TTLCache()`` silently dropped it."""
    injected = TTLCache()
    values = settings()
    service = MarketService(
        values,
        UpstreamClient(values, transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        cache=injected,
    )
    assert service.cache is injected


def test_cache_is_bounded():
    cache = TTLCache(max_entries=2)
    cache.set("a", 1, 10)
    cache.set("b", 2, 10)
    cache.set("c", 3, 10)
    assert len(cache) == 2


# --- opening auction ------------------------------------------------------


def test_auction_returns_virtual_curve_and_matched_result():
    payload = trends_payload(auction_rows())
    service = make_service({"/api/qt/stock/trends2/get": payload})
    auction = service.auction("600519")
    assert len(auction.snapshots) == 4
    assert auction.snapshots[0].time.isoformat() == "2026-10-16T01:15:00+00:00"
    assert str(auction.pre_close) == "1312.97"
    assert str(auction.matched_price) == "1311.57"
    assert str(auction.matched_volume_shares) == "33500"
    assert str(auction.matched_amount) == "43937595.00"
    assert auction.trading_day == date(2026, 10, 16)


def test_auction_before_matching_returns_curve_without_inventing_a_result():
    payload = trends_payload(auction_rows(with_match=False))
    service = make_service({"/api/qt/stock/trends2/get": payload})
    auction = service.auction("600519")
    assert len(auction.snapshots) == 4
    assert auction.matched_price is None
    assert auction.matched_volume_shares is None


def test_auction_takes_the_first_traded_row_not_a_later_one():
    """A later continuous-trading print must not overwrite the auction result."""
    rows = [
        "2026-10-16 09:15,1312.97,1312.97,1312.97,1312.97,0,0.00,1312.970",
        "2026-10-16 09:25,1312.97,1312.97,1312.97,1312.97,0,0.00,1312.970",
        "2026-10-16 09:26,1311.57,1311.57,1311.57,1311.57,335,43937595.00,1311.570",
        "2026-10-16 09:29,1320.00,1320.00,1320.00,1320.00,155,20460000.00,1311.570",
    ]
    service = make_service({"/api/qt/stock/trends2/get": trends_payload(rows)})
    auction = service.auction("600519")
    assert str(auction.matched_price) == "1311.57"
    assert str(auction.matched_volume_shares) == "33500"


def test_star_auction_volume_is_converted_from_lots():
    service = make_service({"/api/qt/stock/trends2/get": trends_payload(auction_rows(star=True))})
    auction = service.auction("688017")
    assert str(auction.matched_volume_shares) == "15100"


def test_auction_without_snapshot_rows_is_a_clear_failure():
    service = make_service({"/api/qt/stock/trends2/get": json.dumps({"data": None})})
    with pytest.raises(DomainError) as failure:
        service.auction("600519")
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"


def test_stock_profile_exposes_eastmoney_industry_and_caches_the_result():
    calls = []

    def profile(request):
        calls.append(request)
        assert request.url.params["secid"] == "1.600519"
        assert request.url.params["fields"] == "f57,f58,f127"
        return httpx.Response(200, text=profile_payload())

    service = make_service({"/api/qt/stock/get": profile})
    first = service.stock_profile("600519")
    second = service.stock_profile("600519.SH")

    assert first == second
    assert first.symbol == "600519.SH"
    assert first.name == "贵州茅台"
    assert first.industry == "白酒Ⅱ"
    assert first.provider == "eastmoney"
    assert len(calls) == 1


def test_stock_profile_keeps_a_missing_industry_explicit():
    service = make_service(
        {"/api/qt/stock/get": profile_payload(industry="")},
    )

    profile = service.stock_profile("600519")

    assert profile.industry is None
    assert profile.provider == "eastmoney"


def test_stock_profile_rejects_a_provider_identity_mismatch():
    service = make_service(
        {"/api/qt/stock/get": profile_payload(code="000001", name="平安银行")},
    )

    with pytest.raises(DomainError) as failure:
        service.stock_profile("600519")

    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


# --- auction degradation: Eastmoney curve is unreachable ------------------


def tick_body(symbol="sh600519", first="0/09:25:02/1311.57/1.57/335/43937595/B"):
    return f'v_detail_data_{symbol}=[0,"{first}|1/09:30:03/1308.25/-3.32/160/20945865/S"]'


def sina_body(symbol=("sh600519", "600519"), price="1311.57", volume="33500"):
    qq, code = symbol
    return json.dumps(
        {
            "result": {
                "status": {"code": 0},
                "data": [
                    {"m": "09:25:00", "v": volume, "p": price, "avg_p": price},
                    {"m": "09:30:00", "v": "124620", "p": "1303", "avg_p": "1308.268"},
                ],
            }
        }
    )


def snapshot_body(date="2026-10-16", pre_close="1312.97", qq_code="sh600519"):
    # hq.sinajs.cn payload: field 1 open, 2 previous close, 30 date.
    fields = [
        "贵州茅台",
        "1311.570",
        pre_close,
        "1329.000",
        "1329.880",
        "1301.680",
        "1328.580",
        "1329.000",
        "3850175",
        "5075528306.000",
    ]
    fields += ["100", "1328.580"] * 10
    fields += [date, "15:34:59", "00", "D|2000|2658000.00"]
    return f'var hq_str_{qq_code}="{",".join(fields)}";'


def degraded_service(*, tick=None, kline=None, sina=None, snapshot=None):
    """Eastmoney always fails; Sina answers unless overridden; see the note in each test."""

    def handler(request):
        path = request.url.path
        if path == "/appstock/app/kline/mkline":
            return httpx.Response(200, text=kline or kline_payload())
        if path == "/api/qt/stock/trends2/get":
            return httpx.Response(503, text="blocked")
        if path == "/cn/api/openapi.php/CN_MinlineService.getMinlineData":
            return httpx.Response(200, text=sina if sina is not None else sina_body())
        if path.startswith("/list="):
            return httpx.Response(
                200, content=(snapshot if snapshot is not None else snapshot_body()).encode("gbk")
            )
        if path == "/data/index.php":
            return httpx.Response(200, content=(tick_body() if tick is None else tick).encode())
        raise AssertionError(f"unexpected upstream call: {path}")

    values = settings()
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    return MarketService(values, client)


def test_degraded_matched_time_is_utc_like_every_other_timestamp():
    """A degraded auction must not serialise +08:00 while bars serialise Z."""
    auction = degraded_service().auction("600519")
    assert auction.matched_time is not None
    assert auction.matched_time.utcoffset().total_seconds() == 0
    assert auction.matched_time.isoformat().endswith("+00:00")
    assert auction.matched_time.isoformat() == "2026-10-16T01:25:00+00:00"


def test_eastmoney_failure_degrades_to_the_sina_matched_trade():
    auction = degraded_service().auction("600519")
    assert auction.provider == "sina"
    assert auction.degraded is True
    assert auction.snapshots == []
    assert str(auction.matched_price) == "1311.57"
    assert str(auction.matched_volume_shares) == "33500"
    assert str(auction.matched_amount) == "43937595"
    assert str(auction.pre_close) == "1312.97"
    assert auction.trading_day == date(2026, 10, 16)
    assert any("降级" in note for note in auction.limits)


def test_sina_reports_star_shares_exactly():
    service = degraded_service(
        sina=sina_body(("sh688017", "688017"), price="238", volume="15126"),
        snapshot=snapshot_body(qq_code="sh688017"),
        kline=kline_payload(
            symbol="sh688017",
            bars=[["202610160930", "238.00", "238.00", "238.00", "238.00", "15126", {}, "0"]],
        ),
    )
    auction = service.auction("688017")
    assert auction.provider == "sina"
    assert str(auction.matched_volume_shares) == "15126"


def test_tencent_tick_is_the_last_resort_when_sina_also_fails():
    service = degraded_service(
        sina=json.dumps({"result": {"status": {"code": 1}, "data": []}}),
        kline=kline_payload(
            symbol="sh688017",
            bars=[["202610160930", "238.00", "238.00", "238.00", "238.00", "15126", {}, "0"]],
        ),
        tick=tick_body("sh688017", "0/09:25:02/238.00/0.00/151/3599988/S"),
    )
    auction = service.auction("688017")
    assert auction.provider == "tencent"
    assert str(auction.matched_volume_shares) == "15126"
    assert any("新浪不可用" in note for note in auction.limits)


def _full_day_bars(symbol="sh688017", auction_volume="15126"):
    bars = []
    for hour in range(9, 16):
        for minute in range(60):
            if hour == 9 and minute < 30:
                continue
            if hour == 11 and minute > 30:
                continue
            if hour == 12:
                continue
            volume = auction_volume if (hour == 9 and minute == 30) else "100"
            bars.append(
                [f"20261016{hour:02d}{minute:02d}", "238", "238", "238", "238", volume, {}, "0"]
            )
    return bars[:241]


def test_star_auction_volume_is_read_from_the_0930_bar_of_a_full_day():
    """The window must cover a whole session; two bars return the closing minutes."""
    service = degraded_service(
        sina=json.dumps({"result": {"status": {"code": 1}, "data": []}}),
        kline=kline_payload(symbol="sh688017", bars=_full_day_bars()),
        tick=tick_body("sh688017", "0/09:25:02/238.00/0.00/151/3599988/S"),
    )
    auction = service.auction("688017")
    assert auction.provider == "tencent"
    assert str(auction.matched_volume_shares) == "15126"
    assert any("09:30 分钟线" in note for note in auction.limits)


def test_degradation_does_not_invent_an_auction_when_no_source_has_one():
    service = degraded_service(
        sina=json.dumps({"result": {"status": {"code": 1}, "data": []}}), tick=""
    )
    with pytest.raises(DomainError) as failure:
        service.auction("600519")
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"


def test_sina_rows_without_an_auction_row_report_no_data():
    service = degraded_service(
        sina=json.dumps(
            {"result": {"status": {"code": 0}, "data": [{"m": "09:30:00", "v": "1", "p": "1"}]}}
        ),
        tick="",
    )
    with pytest.raises(DomainError) as failure:
        service.auction("600519")
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"


def test_invalid_symbol_is_not_degraded_into_a_different_question():
    with pytest.raises(DomainError) as failure:
        degraded_service().auction("000001")
    assert failure.value.code == "MARKET_SYMBOL_INVALID"


def test_disabled_source_is_not_masked_by_the_fallback():
    values = settings(upstream={"enabled": False})
    client = UpstreamClient(values, transport=httpx.MockTransport(lambda request: None))
    with pytest.raises(DomainError) as failure:
        MarketService(values, client).auction("600519")
    assert failure.value.code == "MARKET_SOURCE_DISABLED"


def test_older_session_is_flagged_as_stale_in_limits():
    """A pre-market response carries the previous session; it must say so."""
    service = degraded_service(snapshot=snapshot_body(date="2020-01-02", pre_close="1300.00"))
    auction = service.auction("600519")
    assert auction.trading_day == date(2020, 1, 2)
    assert any("不是今日竞价" in note for note in auction.limits)


def test_current_session_is_not_flagged_as_stale():
    today = (
        __import__("research_platform.modules.market.market_time", fromlist=["exchange_now"])
        .exchange_now()
        .date()
    )
    service = degraded_service(snapshot=snapshot_body(date=today.isoformat()))
    auction = service.auction("600519")
    assert not any("不是今日竞价" in note for note in auction.limits)


def test_sina_snapshot_date_drives_the_trading_day():
    service = degraded_service(snapshot=snapshot_body(date="2026-10-15", pre_close="1300.00"))
    auction = service.auction("600519")
    assert auction.trading_day == date(2026, 10, 15)
    assert str(auction.pre_close) == "1300"


# --- outbound client behaviour -------------------------------------------


def test_get_is_retried_once_on_transient_status():
    calls = []

    def flaky(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, text="")
        return httpx.Response(200, text=kline_payload())

    service = make_service({"/appstock/app/kline/mkline": flaky})
    assert service.intraday("600519", "m1", 2).total == 2
    assert len(calls) == 2


def test_client_error_is_not_retried():
    calls = []

    def rejected(request):
        calls.append(1)
        return httpx.Response(404, text="gone")

    service = make_service({"/appstock/app/kline/mkline": rejected})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 2)
    assert failure.value.code == "MARKET_SOURCE_UNAVAILABLE"
    assert len(calls) == 1


def test_redirect_is_not_followed_silently_and_is_a_source_failure():
    """A moved endpoint must not surface as "not JSON" later on HTML.

    Redirects are disabled in the shared client: an endpoint that moved is a
    source problem the operator must see, not a payload defect.
    """

    def moved(request):
        return httpx.Response(
            301, headers={"location": "https://elsewhere.invalid/x"}, text="<html>"
        )

    service = make_service({"/appstock/app/kline/mkline": moved})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 2)
    assert failure.value.code == "MARKET_SOURCE_UNAVAILABLE"


def test_rate_limited_upstream_maps_to_429_not_a_plain_outage():
    """A 429 is actionable (back off); reporting it as 503 hides the difference."""

    def limited(request):
        return httpx.Response(429, text="slow down")

    service = make_service({"/appstock/app/kline/mkline": limited})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 2)
    assert failure.value.code == "MARKET_SOURCE_RATE_LIMITED"


def test_read_timeout_is_not_retried():
    """A timeout may already have been processed; retrying doubles the wait."""
    calls = []

    def timed_out(request):
        calls.append(1)
        raise httpx.ReadTimeout("read timed out", request=request)

    service = make_service({"/appstock/app/kline/mkline": timed_out})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 2)
    assert failure.value.code == "MARKET_SOURCE_UNAVAILABLE"
    assert len(calls) == 1


def test_connect_timeout_is_not_retried():
    """The rule is "timeouts are not retried"; the connect phase is no exception."""
    calls = []

    def timed_out(request):
        calls.append(1)
        raise httpx.ConnectTimeout("connect timeout", request=request)

    service = make_service({"/appstock/app/kline/mkline": timed_out})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 2)
    assert failure.value.code == "MARKET_SOURCE_UNAVAILABLE"
    assert len(calls) == 1


def test_connection_error_is_still_retried():
    calls = []

    def flaky(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, text=kline_payload())

    service = make_service({"/appstock/app/kline/mkline": flaky})
    assert service.intraday("600519", "m1", 2).total == 2
    assert len(calls) == 2


def test_retry_budget_cannot_exceed_one():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        settings(upstream={"max_retries": 2})


def test_oversized_body_is_rejected():
    def huge(request):
        return httpx.Response(200, content=b"x" * (5 * 1024 * 1024))

    service = make_service({"/appstock/app/kline/mkline": huge})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 2)
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_streamed_body_aborts_before_the_whole_payload_arrives():
    """The ceiling must stop the download, not merely reject it afterwards.

    The assertions are on *how much was consumed* and *that the stream was
    closed*: a test that only checks the error code would also pass if the whole
    8 MiB had been buffered first.
    """
    delivered = []
    closed = []

    class Endless(httpx.SyncByteStream):
        def __iter__(self):
            for _ in range(8):
                delivered.append(1)
                yield b"x" * (1024 * 1024)

        def close(self):
            closed.append(1)

    def handler(request):
        return httpx.Response(200, stream=Endless())

    values = settings(upstream={"min_interval_ms": 0, "max_retries": 0})
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    with pytest.raises(DomainError) as failure:
        client.get_json(provider="p", url="https://stream.example.invalid/x")
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"
    # 4 MiB ceiling at 64 KiB chunks: far fewer than the 8 MiB the server offered.
    assert len(delivered) < 8, f"read {len(delivered)} of 8 MiB blocks"
    assert closed, "the stream must be closed once the limit is hit"


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_calls"),
    [
        (httpx.ReadTimeout("read timed out"), "MARKET_SOURCE_UNAVAILABLE", 1),
        (httpx.ReadError("connection reset"), "MARKET_SOURCE_UNAVAILABLE", 2),
    ],
)
def test_body_phase_failures_map_to_domain_errors(error, expected_code, expected_calls):
    """A failure while reading the body must not escape as a raw httpx error."""
    calls = []

    class Failing(httpx.SyncByteStream):
        def __iter__(self):
            yield b"{"
            raise error

    def handler(request):
        calls.append(1)
        return httpx.Response(200, stream=Failing())

    values = settings(upstream={"min_interval_ms": 0, "max_retries": 1})
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    with pytest.raises(DomainError) as failure:
        client.get_json(provider="p", url="https://body.example.invalid/x")
    assert failure.value.code == expected_code
    assert len(calls) == expected_calls


def test_each_attempt_closes_its_stream_exactly_once():
    """Closing must happen once per attempt: no leak and no double close."""
    closes = []
    attempts = []

    class FailFirstAttemptOnly(httpx.SyncByteStream):
        def __iter__(self):
            attempts.append(1)
            if len(attempts) == 1:
                yield b"{"
                raise httpx.ReadError("connection reset")
            yield b'{"ok": true}'

        def close(self):
            closes.append(1)

    def handler(request):
        return httpx.Response(200, stream=FailFirstAttemptOnly())

    values = settings(upstream={"min_interval_ms": 0, "max_retries": 1})
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    assert client.get_json(provider="p", url="https://close.example.invalid/x") == {"ok": True}
    assert len(closes) == 2, f"expected one close per attempt, got {len(closes)}"


def test_broken_compressed_body_is_a_payload_error_and_is_not_retried():
    calls = []

    class BrokenGzip(httpx.SyncByteStream):
        def __iter__(self):
            yield b"\x1f\x8b\x08\x00not-really-gzip"

    def handler(request):
        calls.append(1)
        return httpx.Response(200, stream=BrokenGzip(), headers={"content-encoding": "gzip"})

    values = settings(upstream={"min_interval_ms": 0, "max_retries": 1})
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    with pytest.raises(DomainError) as failure:
        client.get_json(provider="p", url="https://gzip.example.invalid/x")
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"
    assert len(calls) == 1


def test_connection_failure_is_reported_as_unavailable():
    def broken(request):
        raise httpx.ConnectError("refused")

    service = make_service({"/appstock/app/kline/mkline": broken})
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 2)
    assert failure.value.code == "MARKET_SOURCE_UNAVAILABLE"


def test_disabled_upstream_refuses_before_any_request():
    called = []
    service = make_service(
        {"/appstock/app/kline/mkline": lambda request: called.append(1)},
        upstream={"enabled": False},
    )
    with pytest.raises(DomainError) as failure:
        service.intraday("600519", "m1", 2)
    assert failure.value.code == "MARKET_SOURCE_DISABLED"
    assert called == []


def test_host_address_override_rewrites_url_but_keeps_host_and_sni():
    """Pinning an address must not disable certificate identity checks.

    The URL is rewritten to the address while ``Host`` and the TLS SNI stay the
    hostname, so a wrong/forged address still fails TLS verification instead of
    silently receiving traffic.
    """
    import socket as socket_module

    original = socket_module.getaddrinfo
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["host"] = request.headers.get("host")
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, text='{"ok": true}')

    values = settings(
        upstream={"min_interval_ms": 0, "host_addresses": {"pinned.example.invalid": ["127.0.0.1"]}}
    )
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    client.get_json(provider="tencent", url="https://pinned.example.invalid/path")
    assert seen["url"].startswith("https://127.0.0.1/path")
    assert seen["host"] == "pinned.example.invalid"
    assert seen["sni"] == "pinned.example.invalid"
    # The resolver must never be patched globally: a previous version did, and
    # concurrent requests then left every later host resolving through a stale
    # closure in this process.
    assert socket_module.getaddrinfo is original


def test_host_address_override_does_not_leak_into_other_hosts():
    seen = []

    def handler(request):
        seen.append((str(request.url), request.extensions.get("sni_hostname")))
        return httpx.Response(200, text='{"ok": true}')

    values = settings(
        upstream={"min_interval_ms": 0, "host_addresses": {"pinned.example.invalid": ["127.0.0.1"]}}
    )
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    client.get_json(provider="tencent", url="https://pinned.example.invalid/a")
    client.get_json(provider="tencent", url="https://other.example.invalid/b")
    assert seen[0][0].startswith("https://127.0.0.1/a")
    assert seen[1][0] == "https://other.example.invalid/b"
    assert seen[1][1] is None


def test_unpinned_request_is_byte_identical_to_a_plain_request():
    """With no configuration the client must not add headers or extensions."""
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["sni"] = request.extensions.get("sni_hostname")
        seen["host"] = request.headers.get("host")
        return httpx.Response(200, text='{"ok": true}')

    client = UpstreamClient(settings(), transport=httpx.MockTransport(handler))
    client.get_json(provider="tencent", url="https://plain.example.invalid/x")
    assert seen["url"] == "https://plain.example.invalid/x"
    assert seen["sni"] is None
    assert seen["host"] == "plain.example.invalid"


def test_pacing_sleeps_between_same_provider_calls():
    sleeps = []
    client = UpstreamClient(
        settings(upstream={"min_interval_ms": 250, "max_retries": 0}),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=kline_payload())),
        clock=lambda: 0.0,
        sleep=sleeps.append,
    )
    source = TencentSource(client)
    source.intraday(parse_symbol("600519"), "m1", 2)
    source.intraday(parse_symbol("600519"), "m1", 2)
    assert sleeps == [pytest.approx(0.25)]


# --- Tushare --------------------------------------------------------------


def tushare_settings(token="test-token-value"):
    return settings(tushare={"token": token})


def tushare_service(response, **overrides):
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=response)

    values = tushare_settings(**overrides)
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    return TushareSource(client, values.tushare), captured


def test_tushare_daily_converts_lots_and_thousand_yuan():
    response = {
        "code": 0,
        "msg": "",
        "data": {
            "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"],
            "items": [
                ["600519.SH", "20261016", 1311.57, 1329.88, 1301.68, 1329.0, 38501.75, 5075528.306]
            ],
        },
    }
    source, captured = tushare_service(response)
    bars = source.daily(parse_symbol("600519"), "20261016", "20261016")
    assert str(bars[0].volume_shares) == "3850175"
    assert str(bars[0].amount) == "5075528306"
    assert captured["body"]["api_name"] == "daily"
    assert captured["body"]["token"] == "test-token-value"


def test_tushare_empty_items_is_not_reported_as_success():
    """An empty item list means "not answered", not "0 bars"."""
    response = {
        "code": 0,
        "msg": "",
        "data": {
            "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"],
            "items": [],
        },
    }
    source, _ = tushare_service(response)
    with pytest.raises(DomainError) as failure:
        source.daily(parse_symbol("600519"), "20261016", "20261016")
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"


def test_tushare_bad_date_format_is_a_source_error():
    response = {
        "code": 0,
        "msg": "",
        "data": {
            "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"],
            "items": [["600519.SH", "2026-10-16", 1, 1, 1, 1, 1, 1]],
        },
    }
    source, _ = tushare_service(response)
    with pytest.raises(DomainError) as failure:
        source.daily(parse_symbol("600519"), "20261016", "20261016")
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_tushare_permission_denied_is_mapped_and_message_is_not_echoed():
    source, _ = tushare_service({"code": 40203, "msg": "抱歉，您没有接口(stk_auction)访问权限"})
    with pytest.raises(DomainError) as failure:
        source.daily(parse_symbol("600519"), "20261016", "20261016")
    assert failure.value.code == "MARKET_SOURCE_PERMISSION_DENIED"
    assert "stk_auction" not in failure.value.message


def test_tushare_rate_limit_is_mapped_to_429():
    source, _ = tushare_service({"code": 40203, "msg": "抱歉，您每分钟最多访问该接口1次"})
    with pytest.raises(DomainError) as failure:
        source.daily(parse_symbol("600519"), "20261016", "20261016")
    assert failure.value.code == "MARKET_SOURCE_RATE_LIMITED"


def test_unconfigured_tushare_refuses_without_a_request():
    client = UpstreamClient(
        settings(), transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    source = TushareSource(client, None)
    assert source.configured is False
    with pytest.raises(DomainError) as failure:
        source.daily(parse_symbol("600519"), "20261016", "20261016")
    assert failure.value.code == "MARKET_SOURCE_NOT_CONFIGURED"


def test_tushare_token_is_redacted_from_settings_repr():
    values = tushare_settings(token="do-not-print-this-token")
    assert "do-not-print-this-token" not in repr(values)
    assert values.tushare is not None


# --- daily range -----------------------------------------------------------


def test_daily_range_validation_is_a_request_error():
    service = make_service({})
    today = date(2026, 10, 16)
    with pytest.raises(DomainError) as failure:
        service.daily("600519", today, today - timedelta(days=1))
    assert failure.value.code == "MARKET_SYMBOL_INVALID"


def test_daily_range_is_bounded_to_ten_years():
    service = make_service({})
    today = date(2026, 10, 16)
    with pytest.raises(DomainError) as failure:
        service.daily("600519", today - timedelta(days=3661), today)
    assert failure.value.code == "MARKET_SYMBOL_INVALID"


# --- provider parsing helpers ---------------------------------------------


def test_suffix_form_is_canonical_and_both_orders_parse():
    """``600519.SH`` is the public form; ``.SH``/``sh``/``sh.`` variants all fold into it."""
    for raw in ("600519", "600519.SH", "600519.sh", "sh600519", "sh.600519", "SH600519"):
        symbol = parse_symbol(raw)
        assert symbol.display == "600519.SH"
        assert symbol.qq_code == "sh600519"
        assert symbol.eastmoney_secid == "1.600519"


def test_eastmoney_falls_back_to_the_second_host(monkeypatch=None):
    """The curve endpoint is served by more than one host; one dead host must not win."""
    from research_platform.modules.market import eastmoney as module

    calls = []

    def handler(request):
        calls.append(request.url.host)
        if request.url.host == "push2.eastmoney.com":
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, text=trends_payload(auction_rows()))

    values = settings()
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    auction = MarketService(values, client).auction("600519")
    assert auction.provider == "eastmoney"
    assert auction.degraded is False
    assert len(auction.snapshots) == 4
    assert calls[0] == "push2.eastmoney.com"
    assert "push2his.eastmoney.com" in calls
    assert module.TRENDS_HOSTS[1] == "push2his.eastmoney.com"


def test_all_eastmoney_hosts_failing_degrades_to_sina():
    def handler(request):
        if request.url.path == "/cn/api/openapi.php/CN_MinlineService.getMinlineData":
            return httpx.Response(200, text=sina_body())
        if request.url.path.startswith("/list="):
            return httpx.Response(200, content=snapshot_body().encode("gbk"))
        return httpx.Response(502, text="bad gateway")

    values = settings()
    client = UpstreamClient(values, transport=httpx.MockTransport(handler))
    auction = MarketService(values, client).auction("600519")
    assert auction.provider == "sina"
    assert auction.degraded is True


def test_tencent_source_names_its_missing_coverage():
    client = UpstreamClient(
        settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, text="{}"))
    )
    with pytest.raises(DomainError):
        TencentSource(client).intraday(parse_symbol("920982"), "m1", 1)


def test_eastmoney_missing_structure_is_a_source_error_not_empty_data():
    """A changed response shape must not be reported as "no auction".

    Reporting ``{}`` as MARKET_DATA_UNAVAILABLE hides a provider change and also
    stops the degradation chain from trying the next source.
    """
    client = UpstreamClient(
        settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, text="{}"))
    )
    with pytest.raises(DomainError) as failure:
        EastmoneySource(client).opening_auction(parse_symbol("600519"))
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_eastmoney_explicit_empty_data_is_reported_as_no_data():
    payload = json.dumps({"data": None})
    client = UpstreamClient(
        settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, text=payload))
    )
    with pytest.raises(DomainError) as failure:
        EastmoneySource(client).opening_auction(parse_symbol("600519"))
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"
