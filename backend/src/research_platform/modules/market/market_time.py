"""Exchange time handling for market data.

A-share timestamps are exchange-local (Asia/Shanghai, no DST). The public
contract exposes UTC ISO 8601 timestamps and a separate ``trading_day`` date, so
the conversion happens once here instead of in every provider or caller.

A fixed ``+08:00`` offset is deliberate: China has observed no DST since 1991 and
Windows Python installations often lack the IANA tz database, which would turn a
timezone-aware conversion into a crash depending on the host.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

MARKET_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")

# Continuous trading plus both call auctions; used to label a snapshot phase.
OPEN_AUCTION_START = "09:15"
OPEN_AUCTION_END = "09:25"
CONTINUOUS_START = "09:30"
MORNING_END = "11:30"
AFTERNOON_START = "13:00"
CONTINUOUS_END = "15:00"


def exchange_now() -> datetime:
    return datetime.now(UTC).astimezone(MARKET_TZ)


def to_utc(local: datetime) -> datetime:
    """Convert an exchange-local naive datetime to UTC."""
    return local.replace(tzinfo=MARKET_TZ).astimezone(UTC)


def parse_minute_timestamp(value: str) -> datetime:
    """Parse Tencent's ``YYYYMMDDHHMM`` (exchange local) into a UTC datetime."""
    if len(value) != 12 or not value.isdigit():
        raise ValueError("intraday timestamp must be YYYYMMDDHHMM")
    local = datetime.strptime(value, "%Y%m%d%H%M")
    return to_utc(local)


def parse_quote_timestamp(value: str) -> datetime:
    """Parse ``YYYY-MM-DD HH:MM`` (Eastmoney trends) into a UTC datetime."""
    local = datetime.strptime(value, "%Y-%m-%d %H:%M")
    return to_utc(local)


def at_market_clock(trading_day: date, clock: str) -> datetime:
    """A UTC datetime for ``HH:MM:SS`` on a trading day, in exchange-local terms.

    Building the local time first and converting it is what keeps the contract
    ("all timestamps are UTC") true: attaching ``tzinfo`` without converting would
    serialize ``+08:00`` and silently disagree with every other timestamp in the
    same response.
    """
    moment = datetime.combine(
        trading_day, datetime.strptime(clock, "%H:%M:%S").time(), tzinfo=MARKET_TZ
    )
    return moment.astimezone(UTC)


def session_phase(moment: datetime | None = None) -> str:
    """Coarse session label for the exchange-local clock.

    ``closed`` also covers weekends and holidays: the label describes the clock,
    not the trading calendar, and callers must use ``trading_day`` for the day
    the data actually belongs to.
    """
    now = (moment or exchange_now()).astimezone(MARKET_TZ)
    clock = now.strftime("%H:%M")
    if now.weekday() >= 5:
        return "closed"
    if OPEN_AUCTION_START <= clock < OPEN_AUCTION_END:
        return "opening_auction"
    if OPEN_AUCTION_END <= clock < CONTINUOUS_START:
        return "pre_open"
    if CONTINUOUS_START <= clock <= MORNING_END:
        return "continuous"
    if MORNING_END < clock < AFTERNOON_START:
        return "lunch_break"
    if AFTERNOON_START <= clock <= CONTINUOUS_END:
        return "continuous"
    return "closed"
