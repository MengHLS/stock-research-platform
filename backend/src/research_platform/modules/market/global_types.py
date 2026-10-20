"""Reviewed cross-market instruments and provider-neutral value objects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

GlobalMarketGroup = Literal["us", "asia", "cn", "commodity"]


@dataclass(frozen=True)
class GlobalInstrument:
    key: str
    name: str
    symbol: str
    secid: str
    group: GlobalMarketGroup
    market: str
    currency: str
    unit: str
    precision: int
    sina_symbol: str
    history_sources: tuple[str, ...]
    yahoo_symbol: str | None = None
    tencent_symbol: str | None = None
    quote_timezone_hours: int = 8


@dataclass(frozen=True)
class GlobalQuote:
    price: Decimal
    previous_close: Decimal | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    change: Decimal | None
    change_pct: Decimal | None
    quote_time: datetime | None
    provider: str = "unknown"


@dataclass(frozen=True)
class GlobalBar:
    trading_day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    change_pct: Decimal | None


# The list is deliberately explicit. Search endpoints would make the displayed
# universe depend on vendor ranking, and the China-Korea ETF is named as a proxy
# rather than presented as the underlying CSI index.
GLOBAL_INSTRUMENTS: tuple[GlobalInstrument, ...] = (
    GlobalInstrument(
        key="nasdaq",
        name="纳斯达克综合",
        symbol="IXIC",
        secid="100.IXIC",
        group="us",
        market="NASDAQ",
        currency="USD",
        unit="点",
        precision=2,
        sina_symbol="gb_ixic",
        history_sources=("sina", "yahoo", "eastmoney"),
        yahoo_symbol="^IXIC",
        tencent_symbol="usIXIC",
    ),
    GlobalInstrument(
        key="dow",
        name="道琼斯工业",
        symbol="DJIA",
        secid="100.DJIA",
        group="us",
        market="NYSE",
        currency="USD",
        unit="点",
        precision=2,
        sina_symbol="gb_dji",
        history_sources=("sina", "yahoo", "eastmoney"),
        yahoo_symbol="^DJI",
        tencent_symbol="usDJI",
    ),
    GlobalInstrument(
        key="kospi",
        name="韩国 KOSPI",
        symbol="KS11",
        secid="100.KS11",
        group="asia",
        market="KRX",
        currency="KRW",
        unit="点",
        precision=2,
        sina_symbol="b_KOSPI",
        history_sources=("naver", "yahoo", "eastmoney"),
        yahoo_symbol="^KS11",
    ),
    GlobalInstrument(
        key="nikkei",
        name="日经 225",
        symbol="N225",
        secid="100.N225",
        group="asia",
        market="TSE",
        currency="JPY",
        unit="点",
        precision=2,
        sina_symbol="b_NKY",
        history_sources=("yahoo_japan", "yahoo", "eastmoney"),
        yahoo_symbol="^N225",
    ),
    GlobalInstrument(
        key="china_korea_semiconductor",
        name="中韩半导体 ETF",
        symbol="513310",
        secid="1.513310",
        group="asia",
        market="SSE ETF",
        currency="CNY",
        unit="元",
        precision=3,
        sina_symbol="sh513310",
        history_sources=("tencent", "yahoo", "eastmoney"),
        tencent_symbol="sh513310",
    ),
    GlobalInstrument(
        key="phlx_semiconductor",
        name="费城半导体",
        symbol="SOX",
        secid="251.SOX",
        group="us",
        market="PHLX",
        currency="USD",
        unit="点",
        precision=2,
        sina_symbol="gb_sox",
        history_sources=("sina", "yahoo", "eastmoney"),
        yahoo_symbol="^SOX",
        tencent_symbol="usSOX",
    ),
    GlobalInstrument(
        key="chinext",
        name="创业板指",
        symbol="399006",
        secid="0.399006",
        group="cn",
        market="SZSE",
        currency="CNY",
        unit="点",
        precision=2,
        sina_symbol="sz399006",
        history_sources=("tencent", "yahoo", "eastmoney"),
        yahoo_symbol="399006.SZ",
        tencent_symbol="sz399006",
    ),
    GlobalInstrument(
        key="star50",
        name="科创 50",
        symbol="000688",
        secid="1.000688",
        group="cn",
        market="SSE",
        currency="CNY",
        unit="点",
        precision=2,
        sina_symbol="sh000688",
        history_sources=("tencent", "yahoo", "eastmoney"),
        yahoo_symbol="000688.SS",
        tencent_symbol="sh000688",
    ),
    GlobalInstrument(
        key="gold",
        name="COMEX 黄金",
        symbol="GC",
        secid="101.GC00Y",
        group="commodity",
        market="COMEX",
        currency="USD",
        unit="美元/盎司",
        precision=2,
        sina_symbol="hf_GC",
        history_sources=("sina", "yahoo", "eastmoney"),
        yahoo_symbol="GC=F",
    ),
    GlobalInstrument(
        key="wti",
        name="NYMEX 原油",
        symbol="CL",
        secid="102.CL00Y",
        group="commodity",
        market="NYMEX",
        currency="USD",
        unit="美元/桶",
        precision=2,
        sina_symbol="hf_CL",
        history_sources=("sina", "yahoo", "eastmoney"),
        yahoo_symbol="CL=F",
    ),
)


def change_percent(current: Decimal, previous: Decimal | None) -> Decimal | None:
    if previous is None or previous == 0:
        return None
    return (current / previous - 1) * 100
