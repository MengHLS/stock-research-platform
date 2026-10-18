"""Stock symbol normalization across public providers.

A symbol is accepted in any of the spellings used by the legacy project and by
the providers (``600519``, ``600519.SH``, ``sh600519``, ``SH600519``); it is
normalized once here and every provider receives derived, validated forms.

Rules (see docs/architecture.md "基础数据与接口约定"):

- codes stay strings and keep leading zeros; the exchange is always explicit;
- a bare 6-digit code is resolved by the reviewed prefix table below, which is
  the same convention Tushare uses for ``ts_code`` suffixes;
- an ambiguous code (``000001`` is both the SSE index and SZSE 平安银行) must be
  written with an explicit prefix/suffix: guessing silently returns another
  instrument, which is worse than a clear error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from research_platform.core.errors import DomainError

Exchange = Literal["SSE", "SZSE", "BSE"]

_TS_SUFFIX = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}
_QQ_PREFIX = {"SSE": "sh", "SZSE": "sz", "BSE": "bj"}
_EASTMONEY_MARKET = {"SSE": "1", "SZSE": "0", "BSE": "0"}
_MARKETS = {"sh": "SSE", "sz": "SZSE", "bj": "BSE", "xshg": "SSE", "xshe": "SZSE"}

_PREFIXED = re.compile(r"^(?P<market>sh|sz|bj)[.\-]?(?P<digits>\d{6})$", re.IGNORECASE)
_SUFFIXED = re.compile(r"^(?P<digits>\d{6})[.\-]?(?P<market>sh|sz|bj|xshg|xshe)$", re.IGNORECASE)
_DIGITS = re.compile(r"^\d{6}$")


_PREFIX_TABLE: tuple[tuple[str, Exchange], ...] = (
    ("6", "SSE"),  # 60x main board, 688/689 STAR
    ("5", "SSE"),  # SSE funds and ETFs
    ("43", "BSE"),
    ("83", "BSE"),
    ("87", "BSE"),
    ("88", "BSE"),
    ("92", "BSE"),
    ("000", "SZSE"),
    ("001", "SZSE"),
    ("002", "SZSE"),
    ("003", "SZSE"),
    ("30", "SZSE"),  # ChiNext
    ("159", "SZSE"),
    ("15", "SZSE"),
    ("16", "SZSE"),
    ("18", "SZSE"),
    ("39", "SZSE"),  # SZSE indices
)

# SSE publishes its indices under 000xxx (000001 上证指数, 000300 沪深300,
# 000016 上证50, 000905 中证500, 000852 中证1000, 000010 上证180, 000688 科创50)
# while SZSE uses 000xxx for stocks — the same digits identify different
# instruments on the two exchanges. These are the SSE index codes this project
# may be asked for; a bare code from this set is still ambiguous with a SZSE
# stock in general, so the *exchange* must come from an explicit prefix/suffix.
# Only 000001/399001/399106 were ambiguous before; every other 000xxx SSE index
# was silently routed to SZSE and returned another instrument (or nothing).
_SSE_INDEX_CODES = frozenset(
    {
        "000001",  # 上证指数 (also 平安银行 on SZSE)
        "000010",  # 上证180
        "000016",  # 上证50
        "000300",  # 沪深300
        "000688",  # 科创50
        "000852",  # 中证1000
        "000905",  # 中证500
    }
)

# SZSE indices are published under 399xxx, a range SSE does not use, so they are
# unambiguous and must NOT be refused: 399001 (深证成指) and 399106 (深证综指)
# previously sat in the ambiguity set and forced callers to write sz399001.
_SZSE_INDEX_PREFIX = "399"


@dataclass(frozen=True)
class Symbol:
    exchange: Exchange
    code: str

    @property
    def suffix_code(self) -> str:
        """Canonical public form: ``600519.SH`` (Tushare-compatible)."""
        return f"{self.code}.{_TS_SUFFIX[self.exchange]}"

    @property
    def ts_code(self) -> str:
        return self.suffix_code

    @property
    def qq_code(self) -> str:
        """Tencent/Eastmoney form: ``sh600519``."""
        return f"{_QQ_PREFIX[self.exchange]}{self.code}"

    @property
    def eastmoney_secid(self) -> str:
        return f"{_EASTMONEY_MARKET[self.exchange]}.{self.code}"

    @property
    def display(self) -> str:
        return self.suffix_code

    @property
    def is_tencent_supported(self) -> bool:
        """Tencent intraday K lines do not cover BSE instruments (empty payload)."""
        return self.exchange != "BSE"


def infer_exchange(code: str) -> Exchange:
    """Reviewed prefix table for a bare 6-digit A-share/ETF/index code.

    Coverage is exactly this table plus :data:`_SSE_INDEX_CODES`. Anything else is
    rejected rather than assumed to be Shenzhen: "not listed" must not silently
    become "SZSE", which is how 000300 used to resolve to a non-existent
    ``sz000300``.
    """
    if code.startswith(_SZSE_INDEX_PREFIX):
        return "SZSE"
    for prefix, exchange in _PREFIX_TABLE:
        if code.startswith(prefix):
            return exchange
    raise DomainError("MARKET_SYMBOL_INVALID")


def parse_symbol(value: str) -> Symbol:
    raw = value.strip()
    if not raw or len(raw) > 16:
        raise DomainError("MARKET_SYMBOL_INVALID")
    match = _PREFIXED.match(raw)
    if match:
        return Symbol(_MARKETS[match.group("market").lower()], match.group("digits"))
    match = _SUFFIXED.match(raw)
    if match:
        return Symbol(_MARKETS[match.group("market").lower()], match.group("digits"))
    if not _DIGITS.match(raw):
        raise DomainError("MARKET_SYMBOL_INVALID")
    if raw in _SSE_INDEX_CODES:
        raise DomainError(
            "MARKET_SYMBOL_INVALID", "该代码在多个市场存在同名标的，请附带交易所前缀。"
        )
    return Symbol(infer_exchange(raw), raw)


# Tencent quotes intraday volume in 手 (100 shares) for every board except STAR
# (688/689), which it quotes in shares. Verified on 2026-10-16 against the daily
# snapshot amount and Tushare's 手-denominated daily volume for 600519, 000001,
# 688017, 510300 and the two main indices.
def tencent_volume_unit(symbol: Symbol) -> Literal["shares", "lots"]:
    if symbol.exchange == "SSE" and symbol.code.startswith(("688", "689")):
        return "shares"
    return "lots"


def shares(value: str, unit: Literal["shares", "lots"]) -> str:
    """Convert a provider volume to shares as a decimal string (no floats).

    Goes through ``finite_decimal`` so a provider that sends ``nan``/``Infinity``
    for a volume becomes an explicit source error instead of a Pydantic
    ``ValidationError`` surfacing as HTTP 500.
    """
    from .parsing import finite_decimal

    amount = finite_decimal(value)
    if unit == "lots":
        amount *= 100
    return format(amount.normalize(), "f")
