"""JSON (de)serialization primitives and money formatting.

Every model's to_dict/from_dict routes dates, times and enums through here so
the rules live in one place instead of being re-derived in a dozen files.
"""

from datetime import date, time
from enum import Enum

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "INR": "₹",
    "CAD": "C$",
    "AUD": "A$",
    "JPY": "¥",
}


def iso_date(value: date | None) -> str | None:
    """Serialize a date as 'YYYY-MM-DD'; None stays None."""
    return value.isoformat() if value is not None else None


def parse_date(value) -> date | None:
    """Parse 'YYYY-MM-DD' back to a date; None/blank/garbage become None."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def iso_time(value: time | None) -> str | None:
    """Serialize a time as 'HH:MM'; None stays None."""
    return value.strftime("%H:%M") if value is not None else None


def parse_time(value) -> time | None:
    """Parse 'HH:MM' back to a time; None/blank/garbage become None."""
    if isinstance(value, time):
        return value
    if not value:
        return None
    try:
        hours, minutes = str(value).split(":")[:2]
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        return None


def enum_value(member):
    """Unwrap an Enum to its raw value so json.dump can handle it."""
    return member.value if isinstance(member, Enum) else member


def parse_enum(enum_cls, value, default=None):
    """Rebuild an enum member, falling back to `default` on an unknown value."""
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except (ValueError, TypeError):
        return default if default is not None else list(enum_cls)[0]


def format_money(amount: float, currency: str = "USD") -> str:
    """Render an amount with its symbol, e.g. '$240.00' or '1,200.00 SEK'."""
    symbol = CURRENCY_SYMBOLS.get(currency, "")
    if symbol:
        return f"{symbol}{amount:,.2f}"
    return f"{amount:,.2f} {currency}"
