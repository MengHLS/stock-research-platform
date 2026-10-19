"""Cross-market overview: vendor parsing, partial failures and the HTTP contract."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from research_platform.core.config import Settings
from research_platform.core.database import make_engine
from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient
from research_platform.main import create_app
from research_platform.modules.identity.dependencies import Actor, require_actor
from research_platform.modules.market.eastmoney_global import (
    GLOBAL_INSTRUMENTS,
    EastmoneyGlobalSource,
    GlobalBar,
    GlobalQuote,
)
from research_platform.modules.market.global_source import GlobalMarketSource
from research_platform.modules.market.naver_global import NaverGlobalSource
from research_platform.modules.market.service import MarketService
from research_platform.modules.market.sina_global import SinaGlobalSource
from research_platform.modules.market.tencent_global import TencentGlobalSource
from research_platform.modules.market.yahoo_global import YahooGlobalSource
from research_platform.modules.market.yahoo_japan_global import YahooJapanGlobalSource


def quote_row(instrument, price: float) -> dict:
    market, code = instrument.secid.split(".", 1)
    return {
        "f2": price,
        "f3": 1.76,
        "f4": 99.96,
        "f12": code,
        "f13": int(market),
        "f14": instrument.name,
        "f15": price + 20,
        "f16": price - 30,
        "f17": price - 10,
        "f18": price - 50,
        "f124": 1792424694,
    }


def kline_row(day: str, close: str) -> str:
    return f"{day},{close},{close},{close},{close},1000,1000000,0,1.00,0.00,0"


def test_global_instrument_metadata_keeps_vendor_identity():
    by_key = {instrument.key: instrument for instrument in GLOBAL_INSTRUMENTS}

    assert by_key["nasdaq"].name == "纳斯达克综合"
    assert by_key["nasdaq"].symbol == "IXIC"
    assert by_key["nasdaq"].group == "us"
    assert by_key["phlx_semiconductor"].group == "us"
    assert by_key["china_korea_semiconductor"].symbol == "513310"


def test_global_source_parses_quotes_and_daily_bars():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/qt/ulist.np/get":
            secids = request.url.params["secids"].split(",")
            rows = [
                quote_row(item, 100 + index)
                for index, item in enumerate(
                    instrument for instrument in GLOBAL_INSTRUMENTS if instrument.secid in secids
                )
            ]
            return httpx.Response(200, json={"rc": 0, "data": {"diff": rows}})
        if request.url.path == "/api/qt/stock/kline/get":
            return httpx.Response(
                200,
                json={
                    "rc": 0,
                    "data": {
                        "klines": [
                            kline_row("2026-10-16", "101.25"),
                            kline_row("2026-10-19", "102.50"),
                        ]
                    },
                },
            )
        raise AssertionError(f"unexpected upstream call: {request.url}")

    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    client = UpstreamClient(settings, transport=httpx.MockTransport(handler))
    source = EastmoneyGlobalSource(client)

    quotes = source.quotes()
    assert quotes["nasdaq"].price == Decimal("100")
    assert quotes["nasdaq"].change_pct == Decimal("1.76")
    assert quotes["nasdaq"].quote_time == datetime(2026, 10, 19, 15, 44, 54, tzinfo=UTC)

    bars = source.history(GLOBAL_INSTRUMENTS[0], 2)
    assert [bar.trading_day for bar in bars] == [date(2026, 10, 16), date(2026, 10, 19)]
    assert bars[-1].close == Decimal("102.50")
    assert bars[-1].change_pct == Decimal("1.00")
    client.close()


def test_sina_global_source_parses_batch_quotes_across_venues():
    us_fields = [""] * 30
    us_fields[0] = "Nasdaq"
    us_fields[1] = "26543.6447"
    us_fields[2] = "1.54"
    us_fields[3] = "2026-10-20 00:19:33"
    us_fields[4] = "403.6107"
    us_fields[5] = "26395.2867"
    us_fields[6] = "26613.1465"
    us_fields[7] = "26344.6663"
    us_fields[26] = "26140.0340"
    kospi_fields = [
        "KOSPI",
        "5768.0100",
        "99.96",
        "1.76",
        "2:27 AM",
        "14:27:00",
        "2026-10-19",
        "14:32:40",
        "5488.4100",
        "5668.0500",
        "5768.0100",
        "5488.4100",
        "0",
    ]
    china_fields = [""] * 32
    china_fields[0] = "ChiNext"
    china_fields[1] = "2770.079"
    china_fields[2] = "2772.384"
    china_fields[3] = "2760.352"
    china_fields[4] = "2772.384"
    china_fields[5] = "2708.919"
    china_fields[30] = "2026-10-19"
    china_fields[31] = "15:00:03"
    futures_fields = [
        "4162.739",
        "",
        "4163.100",
        "4163.300",
        "4211.200",
        "4158.200",
        "00:19:32",
        "4181.100",
        "4185.000",
        "0",
        "1",
        "2",
        "2026-10-20",
        "Gold",
        "0",
    ]
    records = {
        "gb_ixic": ",".join(us_fields),
        "b_KOSPI": ",".join(kospi_fields),
        "sz399006": ",".join(china_fields),
        "hf_GC": ",".join(futures_fields),
    }
    body = "".join(f'var hq_str_{key}="{value}";\n' for key, value in records.items())

    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    client = UpstreamClient(
        settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=body.encode("gbk"))
        ),
    )
    source = SinaGlobalSource(client)
    quotes = source.quotes()

    assert quotes["nasdaq"].price == Decimal("26543.6447")
    assert quotes["nasdaq"].previous_close == Decimal("26140.0340")
    assert quotes["nasdaq"].quote_time == datetime(2026, 10, 19, 16, 19, 33, tzinfo=UTC)
    assert quotes["kospi"].change_pct == Decimal("1.76")
    assert quotes["kospi"].quote_time == datetime(2026, 10, 19, 5, 27, tzinfo=UTC)
    assert quotes["chinext"].change_pct < 0
    assert quotes["gold"].open == Decimal("4185.000")
    client.close()


def test_yahoo_history_skips_incomplete_daily_rows():
    payload = {
        "chart": {
            "result": [
                {
                    "meta": {"gmtoffset": 0},
                    "timestamp": [
                        int(datetime(2026, 10, 15, tzinfo=UTC).timestamp()),
                        int(datetime(2026, 10, 16, tzinfo=UTC).timestamp()),
                        int(datetime(2026, 10, 19, tzinfo=UTC).timestamp()),
                    ],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, 101.0, 102.0],
                                "high": [102.0, 103.0, 104.0],
                                "low": [99.0, 100.0, 101.0],
                                "close": [101.0, 102.0, None],
                            }
                        ]
                    },
                }
            ]
        }
    }
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    client = UpstreamClient(
        settings,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    bars = YahooGlobalSource(client).history(GLOBAL_INSTRUMENTS[0], 2)

    assert [bar.trading_day for bar in bars] == [date(2026, 10, 15), date(2026, 10, 16)]
    assert bars[-1].change_pct.quantize(Decimal("0.0001")) == Decimal("0.9901")
    client.close()


def test_tencent_history_parses_etf_proxy_daily_bars():
    payload = {
        "code": 0,
        "data": {
            "sh513310": {
                "day": [
                    ["2026-10-15", "3.900", "3.856", "3.939", "3.852", "26950252.000"],
                    ["2026-10-16", "3.958", "3.880", "3.980", "3.857", "26050134.000"],
                    ["2026-10-19", "3.882", "3.872", "3.912", "3.814", "25041899.000"],
                ]
            }
        },
    }
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    client = UpstreamClient(
        settings,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
    )
    instrument = next(
        item for item in GLOBAL_INSTRUMENTS if item.key == "china_korea_semiconductor"
    )
    bars = TencentGlobalSource(client).history(instrument, 2)

    assert len(bars) == 2
    assert bars[-1].trading_day == date(2026, 10, 19)
    assert bars[-1].close == Decimal("3.872")
    client.close()


def test_naver_history_parses_korea_index_rows():
    body = repr(
        [
            ["date", "open", "high", "low", "close", "volume", "foreign"],
            ["20261015", 5673.01, 5751.45, 5450.81, 5554.22, 385805, 0.0],
            ["20261016", 5653.99, 5809.94, 5590.33, 5668.05, 298850, 0.0],
            ["20261019", 5488.41, 5768.01, 5488.41, 5768.01, 292781, 0.0],
        ]
    )
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    client = UpstreamClient(
        settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=(body + "\n").encode("euc-kr"))
        ),
    )
    instrument = next(item for item in GLOBAL_INSTRUMENTS if item.key == "kospi")
    bars = NaverGlobalSource(client).history(instrument, 2)

    assert len(bars) == 2
    assert bars[-1].trading_day == date(2026, 10, 19)
    assert bars[-1].close == Decimal("5768.01")
    client.close()


def test_yahoo_japan_history_parses_embedded_nikkei_rows():
    rows = [
        {
            "date": "2026/10/16",
            "openPrice": "64,925.29",
            "highPrice": "65,712.30",
            "lowPrice": "64,800.90",
            "closePrice": "65,324.29",
        },
        {
            "date": "2026/10/19",
            "openPrice": "64,819.56",
            "highPrice": "65,067.80",
            "lowPrice": "63,831.78",
            "closePrice": "64,916.70",
        },
    ]
    escaped_rows = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).replace('"', '\\"')
    body = (
        'self.__next_f.push([1,"\\"historyTable\\":{\\"items\\":' + escaped_rows + ',\\"page\\":1}'
    )
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    client = UpstreamClient(
        settings,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)),
    )
    instrument = next(item for item in GLOBAL_INSTRUMENTS if item.key == "nikkei")
    bars = YahooJapanGlobalSource(client).history(instrument, 2)

    assert [bar.trading_day for bar in bars] == [date(2026, 10, 16), date(2026, 10, 19)]
    assert bars[-1].close == Decimal("64916.70")
    client.close()


def test_global_source_falls_back_when_first_quote_provider_fails():
    class FailingSource:
        provider = "eastmoney"

        def quotes(self):
            raise DomainError("MARKET_SOURCE_UNAVAILABLE")

    class WorkingSource:
        provider = "sina"

        def quotes(self):
            return {
                "nasdaq": GlobalQuote(
                    price=Decimal("100"),
                    previous_close=Decimal("99"),
                    open=None,
                    high=None,
                    low=None,
                    change=Decimal("1"),
                    change_pct=Decimal("1.01"),
                    quote_time=None,
                    provider="sina",
                )
            }

    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    client = UpstreamClient(
        settings,
        transport=httpx.MockTransport(lambda request: None),
    )
    source = GlobalMarketSource(
        client,
        quote_sources=(FailingSource(), WorkingSource()),
        history_sources={},
    )
    quotes = source.quotes()

    assert quotes["nasdaq"].price == Decimal("100")
    assert source.last_quote_provider == "sina"
    client.close()


class FakeGlobalSource:
    def __init__(self, fail_history_keys: set[str] | None = None) -> None:
        self.quote_calls = 0
        self.fail_quotes = False
        self.fail_history_keys = fail_history_keys or set()

    def quotes(self) -> dict[str, GlobalQuote]:
        self.quote_calls += 1
        if self.fail_quotes:
            raise DomainError("MARKET_SOURCE_UNAVAILABLE")
        quote = GlobalQuote(
            price=Decimal("100.00"),
            previous_close=Decimal("98.00"),
            open=Decimal("99.00"),
            high=Decimal("101.00"),
            low=Decimal("97.50"),
            change=Decimal("2.00"),
            change_pct=Decimal("2.04"),
            quote_time=datetime(2026, 10, 19, 8, 0, tzinfo=UTC),
            provider="sina",
        )
        return {instrument.key: quote for instrument in GLOBAL_INSTRUMENTS}

    def history(self, instrument, window: int) -> list[GlobalBar]:
        if instrument.key in self.fail_history_keys:
            raise DomainError("MARKET_SOURCE_UNAVAILABLE")
        return [
            GlobalBar(
                trading_day=date(2026, 10, 19),
                open=Decimal("99.00"),
                high=Decimal("101.00"),
                low=Decimal("98.00"),
                close=Decimal("100.00"),
                change_pct=Decimal("1.00"),
            )
        ]


def test_global_overview_marks_partial_history_without_hiding_quotes(database_url):
    settings = Settings(
        environment="test",
        database_url=database_url,
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    app = create_app(settings)
    source = FakeGlobalSource({"dow"})
    app.state.market = MarketService(
        settings,
        UpstreamClient(settings, transport=httpx.MockTransport(lambda request: None)),
        global_source=source,
    )
    app.dependency_overrides[require_actor] = lambda: Actor(user_id=1)
    client = TestClient(app)
    with client:
        responses = [
            client.get("/api/v1/market/global/overview", params={"window": window})
            for window in (20, 60, 120)
        ]

    assert all(response.status_code == 200 for response in responses)
    bodies = [response.json() for response in responses]
    assert [body["window_requested"] for body in bodies] == [20, 60, 120]
    body = bodies[1]
    assert body["provider"] == "sina"
    assert body["window_requested"] == 60
    assert len(body["items"]) == 10
    assert {item["group"] for item in body["items"]} == {"us", "asia", "cn", "commodity"}
    by_key = {item["key"]: item for item in body["items"]}
    assert by_key["nasdaq"]["assessment"] == "available"
    assert by_key["dow"]["assessment"] == "partial"
    assert by_key["dow"]["quote"]["price"] == "100.00"
    assert by_key["dow"]["issues"] == [
        {
            "code": "history_missing",
            "scope": "dow",
            "message": "数据库中尚无该标的的日线快照。",
        }
    ]


def test_global_overview_persists_and_falls_back_to_the_last_successful_snapshot(database_url):
    settings = Settings(
        environment="test",
        database_url=database_url,
        _env_file=None,
        upstream={
            "min_interval_ms": 0,
            "global_overview_refresh_seconds": 0,
            "global_history_refresh_seconds": 0,
        },
    )
    source = FakeGlobalSource()
    app = create_app(settings)
    app.state.market = MarketService(
        settings,
        UpstreamClient(settings, transport=httpx.MockTransport(lambda request: None)),
        global_source=source,
    )
    app.dependency_overrides[require_actor] = lambda: Actor(user_id=1)
    client = TestClient(app)
    with client:
        first = client.get("/api/v1/market/global/overview", params={"window": 20})
        source.fail_quotes = True
        second = client.get("/api/v1/market/global/overview", params={"window": 20})

    assert first.status_code == 200
    assert first.json()["stale"] is False
    assert first.json()["last_synced_at"] is not None
    assert second.status_code == 200
    assert second.json()["stale"] is True
    assert second.json()["items"][0]["quote"]["price"] == "100.00"
    assert source.quote_calls == 2

    engine = make_engine(database_url)
    try:
        with engine.connect() as connection:
            snapshots = connection.execute(
                text("SELECT COUNT(*) FROM market_global_quote_snapshot")
            ).scalar()
            bars = connection.execute(text("SELECT COUNT(*) FROM market_global_daily_bar")).scalar()
    finally:
        engine.dispose()
    assert snapshots == 10
    assert bars == 10


def test_global_overview_marks_history_stale_when_refresh_lags_quotes(database_url):
    settings = Settings(
        environment="test",
        database_url=database_url,
        _env_file=None,
        upstream={
            "min_interval_ms": 0,
            "global_overview_refresh_seconds": 0,
            "global_history_refresh_seconds": 0,
        },
    )
    source = FakeGlobalSource()
    app = create_app(settings)
    app.state.market = MarketService(
        settings,
        UpstreamClient(settings, transport=httpx.MockTransport(lambda request: None)),
        global_source=source,
    )
    app.dependency_overrides[require_actor] = lambda: Actor(user_id=1)
    client = TestClient(app)
    with client:
        first = client.get("/api/v1/market/global/overview", params={"window": 20})
        source.fail_history_keys.add("dow")
        second = client.get("/api/v1/market/global/overview", params={"window": 20})

    assert first.status_code == 200
    assert first.json()["stale"] is False
    assert second.status_code == 200
    body = second.json()
    by_key = {item["key"]: item for item in body["items"]}
    assert body["stale"] is True
    assert by_key["dow"]["assessment"] == "partial"
    assert {issue["code"] for issue in by_key["dow"]["issues"]} == {"history_stale"}
    assert by_key["nasdaq"]["assessment"] == "available"

    read_settings = Settings(
        environment="test",
        database_url=database_url,
        _env_file=None,
        upstream={
            "min_interval_ms": 0,
            "global_overview_refresh_seconds": 3600,
            "global_history_refresh_seconds": 3600,
        },
    )
    read_app = create_app(read_settings)
    read_app.state.market = MarketService(
        read_settings,
        UpstreamClient(read_settings, transport=httpx.MockTransport(lambda request: None)),
        global_source=source,
    )
    read_app.dependency_overrides[require_actor] = lambda: Actor(user_id=1)
    with TestClient(read_app) as read_client:
        fast = read_client.get("/api/v1/market/global/overview", params={"window": 20})

    assert fast.status_code == 200
    assert fast.json()["stale"] is True
    fast_by_key = {item["key"]: item for item in fast.json()["items"]}
    assert fast_by_key["dow"]["assessment"] == "partial"
    assert {issue["code"] for issue in fast_by_key["dow"]["issues"]} == {"history_stale"}
    assert source.quote_calls == 2


@pytest.mark.parametrize(
    ("window", "status_code", "error_code"),
    [(19, 422, "VALIDATION_FAILED"), (40, 400, "REQUEST_INVALID"), (121, 422, "VALIDATION_FAILED")],
)
def test_global_overview_rejects_unsupported_windows(
    database_url,
    window,
    status_code,
    error_code,
):
    settings = Settings(environment="test", database_url=database_url, _env_file=None)
    app = create_app(settings)
    app.dependency_overrides[require_actor] = lambda: Actor(user_id=1)
    client = TestClient(app)
    with client:
        response = client.get("/api/v1/market/global/overview", params={"window": window})

    assert response.status_code == status_code
    assert response.json()["detail"]["code"] == error_code
