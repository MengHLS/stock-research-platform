"""Shared parsing helpers for provider payloads.

Two failure modes are easy to get wrong and both end up as an HTTP 500 instead of
an explicit source error:

- ``Decimal("nan")`` / ``Decimal("Infinity")`` are *valid* Decimals, so a
  "convert or raise" check lets them through; they then fail in Pydantic and
  surface as ``INTERNAL_ERROR``.
- ``datetime.strptime`` raises ``ValueError``, which is not a ``DomainError``, so
  a provider changing its date format also becomes a 500.

``finite_decimal`` and ``parse_day`` close both gaps and are the only sanctioned
way to accept a number or a date from a provider.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from research_platform.core.errors import DomainError


def finite_decimal(value: object) -> Decimal:
    """Parse a provider number, rejecting NaN/Infinity as a source defect.

    Raises ``MARKET_SOURCE_BAD_RESPONSE`` (502): the peer answered, but the value
    cannot be used as a price/volume. It is *not* ``MARKET_DATA_UNAVAILABLE``,
    which would wrongly suggest the instrument has no data.
    """
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
    if not number.is_finite():
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE")
    return number


def optional_decimal(value: object) -> Decimal | None:
    """Like :func:`finite_decimal`, but an empty/blank field is ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--"}:
        return None
    return finite_decimal(text)


def parse_day(value: object, fmt: str = "%Y%m%d") -> date:
    """Parse a provider trading day; a format change is a source defect."""
    try:
        return datetime.strptime(str(value).strip(), fmt).date()
    except (ValueError, TypeError):
        raise DomainError("MARKET_SOURCE_BAD_RESPONSE") from None
