"""Market routes: real HTTP shapes, error codes and the no-database-write rule."""

import json

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from research_platform.core.config import Settings
from research_platform.core.upstream import UpstreamClient
from research_platform.main import create_app
from research_platform.modules.market.service import MarketService

KLINE = json.dumps(
    {
        "code": 0,
        "msg": "",
        "data": {
            "sh600519": {
                "m1": [
                    [
                        "202610160930",
                        "1311.57",
                        "1311.57",
                        "1311.57",
                        "1311.57",
                        "335.00",
                        {},
                        "0.27",
                    ]
                ]
            }
        },
    }
)

AUCTION = json.dumps(
    {
        "data": {
            "preClose": 1312.97,
            "trends": [
                "2026-10-16 09:15,1312.97,1312.97,1312.97,1312.97,0,0.00,1312.970",
                "2026-10-16 09:20,1311.00,1310.30,1311.00,1310.30,0,0.00,1312.970",
                "2026-10-16 09:26,1311.57,1311.57,1311.57,1311.57,335,43937595.00,1311.570",
            ],
        }
    }
)


@pytest.fixture
def market_client(database_url):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/appstock/app/kline/mkline":
            return httpx.Response(200, text=KLINE)
        if request.url.path == "/api/qt/stock/trends2/get":
            return httpx.Response(200, text=AUCTION)
        raise AssertionError(f"unexpected upstream call: {request.url}")

    settings = Settings(
        environment="test",
        database_url=database_url,
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    app = create_app(settings)
    app.state.market = MarketService(
        settings, UpstreamClient(settings, transport=httpx.MockTransport(handler))
    )
    client = TestClient(app)
    client.__enter__()
    try:
        yield client
    finally:
        client.__exit__(None, None, None)


def test_intraday_route_returns_decimal_strings_and_utc(market_client):
    response = market_client.get(
        "/api/v1/market/intraday", params={"symbol": "600519", "period": "m1", "limit": 1}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "600519.SH"
    assert body["provider"] == "tencent"
    assert body["total"] == 1
    bar = body["bars"][0]
    assert bar["start"].startswith("2026-10-16T01:30:00")
    assert bar["trading_day"] == "2026-10-16"
    assert bar["volume_shares"] == "33500"


def test_auction_route_exposes_curve_and_match(market_client):
    body = market_client.get("/api/v1/market/auction", params={"symbol": "600519"}).json()
    assert body["provider"] == "eastmoney"
    assert body["matched_price"] == "1311.57"
    assert body["matched_volume_shares"] == "33500"
    assert [snapshot["price"] for snapshot in body["snapshots"]] == ["1312.97", "1310.30"]


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"symbol": "000001"}, "MARKET_SYMBOL_INVALID"),
        ({"symbol": "600519", "period": "m7"}, "VALIDATION_FAILED"),
        ({"symbol": "600519", "limit": 5000}, "VALIDATION_FAILED"),
        ({"symbol": "600519", "period": "d1"}, "VALIDATION_FAILED"),
    ],
)
def test_invalid_market_requests_keep_the_shared_error_body(market_client, params, code):
    response = market_client.get("/api/v1/market/intraday", params=params)
    assert response.status_code in (400, 422)
    assert response.json()["detail"]["code"] == code
    assert response.headers["X-Request-ID"] == response.json()["detail"]["request_id"]


def test_unknown_query_parameter_is_rejected_instead_of_ignored(market_client):
    """A typo must not silently return the default instrument with HTTP 200."""
    response = market_client.get("/api/v1/market/quote", params={"smybol": "600519.SH"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "REQUEST_INVALID"
    assert detail["fields"] == [{"path": "query.smybol", "code": "unknown_parameter"}]


def test_known_query_parameters_still_work(market_client):
    response = market_client.get(
        "/api/v1/market/intraday",
        params={"symbol": "600519.SH", "period": "m1", "limit": 1},
    )
    assert response.status_code == 200


def test_sources_report_unconfigured_tushare_without_contacting_it(market_client):
    body = market_client.get("/api/v1/market/sources").json()
    names = {item["name"]: item for item in body["items"]}
    assert names["tencent"]["configured"] is True
    assert names["eastmoney"]["configured"] is True
    assert names["tushare"]["configured"] is False
    assert body["upstream_enabled"] is True


def test_session_route_reports_a_known_phase(market_client):
    body = market_client.get("/api/v1/market/session").json()
    assert body["phase"] in {"opening_auction", "pre_open", "continuous", "lunch_break", "closed"}


def test_market_reads_do_not_write_to_the_database(market_client, database_url):
    from sqlalchemy import text

    from research_platform.core.database import make_engine

    market_client.get("/api/v1/market/intraday", params={"symbol": "600519"})
    market_client.get("/api/v1/market/auction", params={"symbol": "600519"})
    engine = make_engine(database_url)
    try:
        with engine.connect() as connection:
            jobs = connection.execute(text("SELECT COUNT(*) FROM execution_job")).scalar()
            entries = connection.execute(text("SELECT COUNT(*) FROM catalog_entry")).scalar()
    finally:
        engine.dispose()
    assert jobs == 0
    assert entries == 0


def test_unconfigured_tushare_returns_a_mapped_error_not_a_crash(database_url):
    settings = Settings(environment="test", database_url=database_url, _env_file=None)
    app = create_app(settings)
    client = TestClient(app)
    with client:
        response = client.get("/api/v1/market/daily", params={"symbol": "600519"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MARKET_SOURCE_NOT_CONFIGURED"
