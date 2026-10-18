"""Tencent snapshot parsing: units, missing codes and provider-quirk handling."""

import json
from decimal import Decimal

import httpx2 as httpx
import pytest
from pydantic import ValidationError

from research_platform.core.config import Settings
from research_platform.core.errors import DomainError
from research_platform.core.upstream import UpstreamClient
from research_platform.modules.market.schemas import QuoteRead
from research_platform.modules.market.service import MarketService
from research_platform.modules.market.symbols import parse_symbol
from research_platform.modules.market.tencent_quote import TencentQuoteSource


def quote_fields(**overrides):
    """A realistic 88-field Tencent record with named positions overridden."""
    fields = [""] * 88
    fields[0] = "1"
    fields[1] = "贵州茅台"
    fields[2] = "600519"
    fields[3] = "1329.00"
    fields[4] = "1312.97"
    fields[5] = "1311.57"
    fields[6] = "38502"
    fields[30] = "20261016161447"
    fields[32] = "1.22"
    fields[33] = "1329.88"
    fields[34] = "1301.68"
    fields[35] = "1329.00/38502/5075528306"
    fields[37] = "507553"
    fields[38] = "0.31"
    fields[47] = "1444.27"
    fields[48] = "1181.67"
    for position, value in overrides.items():
        fields[int(position.lstrip("f"))] = value
    return "~".join(fields)


def quote_text(symbol="sh600519", fields=None):
    return f'v_{symbol}="{quote_fields() if fields is None else fields}";'


def quote_service(text):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=text.encode("gbk"))

    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0},
    )
    client = UpstreamClient(settings, transport=httpx.MockTransport(handler))
    return MarketService(settings, client)


def test_quote_parses_prices_limits_and_provider_clock():
    quote = quote_service(quote_text()).quote("600519")
    assert quote.symbol == "600519.SH"
    assert quote.name == "贵州茅台"
    assert quote.price == Decimal("1329.00")
    assert quote.previous_close == Decimal("1312.97")
    assert quote.open == Decimal("1311.57")
    assert quote.change_pct == Decimal("1.22")
    assert quote.amount == Decimal("5075528306")
    assert quote.volume_lots == Decimal("38502")
    assert quote.turnover_pct == Decimal("0.31")
    assert quote.limit_up == Decimal("1444.27")
    assert quote.limit_down == Decimal("1181.67")
    assert quote.quote_time.isoformat() == "2026-10-16T08:14:47+00:00"


def test_index_has_no_limit_prices_and_still_parses():
    text = quote_text(
        "sh000001",
        quote_fields(f1="上证指数", f2="000001", f3="3716.28", f47="-1", f48="-1"),
    )
    quote = quote_service(text).quote("sh000001")
    assert quote.limit_up is None and quote.limit_down is None


def test_non_finite_quote_price_is_a_source_error():
    """A nan/inf price must not reach Pydantic as a 500."""
    text = quote_text(fields=quote_fields(f3="nan"))
    with pytest.raises(DomainError) as failure:
        quote_service(text).quote("600519")
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_non_finite_optional_quote_field_is_a_source_error():
    text = quote_text(fields=quote_fields(f38="Infinity"))
    with pytest.raises(DomainError) as failure:
        quote_service(text).quote("600519")
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_non_finite_limit_price_is_a_source_error():
    text = quote_text(fields=quote_fields(f47="nan"))
    with pytest.raises(DomainError) as failure:
        quote_service(text).quote("600519")
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_unknown_symbol_is_reported_as_no_data():
    with pytest.raises(DomainError) as failure:
        quote_service("").quote("600519")
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"


def test_malformed_record_is_a_bad_response_not_a_zero_quote():
    with pytest.raises(DomainError) as failure:
        quote_service('v_sh600519="1~x~600519~abc";').quote("600519")
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_quote_time_must_be_a_full_provider_timestamp():
    text = quote_text(fields=quote_fields(f30="20261016"))
    with pytest.raises(DomainError) as failure:
        quote_service(text).quote("600519")
    assert failure.value.code == "MARKET_SOURCE_BAD_RESPONSE"


def test_quote_is_cached_within_its_ttl():
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, content=quote_text().encode("gbk"))

    settings = Settings(
        environment="test",
        database_url="sqlite://",
        _env_file=None,
        upstream={"min_interval_ms": 0, "quote_cache_seconds": 30},
    )
    service = MarketService(
        settings, UpstreamClient(settings, transport=httpx.MockTransport(handler))
    )
    service.quote("600519")
    service.quote("600519")
    assert len(calls) == 1


def test_quote_source_rejects_a_record_for_another_symbol():
    client = UpstreamClient(
        Settings(environment="test", database_url="sqlite://", _env_file=None),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=quote_text("sh600519").encode("gbk"))
        ),
    )
    with pytest.raises(DomainError) as failure:
        TencentQuoteSource(client).quote(parse_symbol("000001.SZ"))
    assert failure.value.code == "MARKET_DATA_UNAVAILABLE"


def test_quote_schema_forbids_extra_fields():
    with pytest.raises(ValidationError):
        QuoteRead.model_validate(
            {
                "symbol": "sh600519",
                "name": "x",
                "price": "1",
                "previous_close": "1",
                "quote_time": "2026-10-16T08:14:47+00:00",
                "volume_lots": "1",
                "amount": "1",
                "phase": "closed",
                "unexpected": 1,
            }
        )


def test_quote_route_exposes_the_snapshot(database_url):
    from fastapi.testclient import TestClient

    from research_platform.main import create_app

    settings = Settings(environment="test", database_url=database_url, _env_file=None)

    def handler(request):
        assert request.url.path == "/q=sh600519" or "qt.gtimg.cn" in str(request.url)
        return httpx.Response(200, content=quote_text().encode("gbk"))

    app = create_app(settings)
    app.state.market = MarketService(
        settings, UpstreamClient(settings, transport=httpx.MockTransport(handler))
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/market/quote", params={"symbol": "600519"})
    assert response.status_code == 200
    body = response.json()
    assert body["price"] == "1329.00"
    assert body["quote_time"].startswith("2026-10-16T08:14:47")
    assert body["phase"] in {"opening_auction", "pre_open", "continuous", "lunch_break", "closed"}
    assert json.loads(json.dumps(body))["volume_lots"] == "38502"
