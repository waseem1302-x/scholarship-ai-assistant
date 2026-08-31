"""Utility functions for resilient dates, currencies, and timezone normalization."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone

_TIMEZONE_OFFSETS: dict[str, int] = {
    "UTC": 0,
    "GMT": 0,
    "Z": 0,
    "WET": 0,
    "CET": 1,
    "CEST": 2,
    "EET": 2,
    "EEST": 3,
    "JST": 9,
    "KST": 9,
    "CST": 8,  # China Standard Time / Central
    "SGT": 8,
    "HKT": 8,
    "MYT": 8,
    "IST": 5,  # +5:30 handled specially
    "PKT": 5,
    "AEST": 10,
    "AEDT": 11,
    "EST": -5,
    "EDT": -4,
    "CDT": -5,
    "MST": -7,
    "MDT": -6,
    "PST": -8,
    "PDT": -7,
}

_MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_COUNTRY_CURRENCY_MAP: dict[str, str] = {
    "US": "USD",
    "USA": "USD",
    "GB": "GBP",
    "UK": "GBP",
    "AU": "AUD",
    "CA": "CAD",
    "SG": "SGD",
    "NZ": "NZD",
    "HK": "HKD",
    "JP": "JPY",
    "DE": "EUR",
    "FR": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "NL": "EUR",
    "BE": "EUR",
    "AT": "EUR",
    "FI": "EUR",
    "IE": "EUR",
    "CN": "CNY",
    "TR": "TRY",
    "KR": "KRW",
    "SE": "SEK",
    "CH": "CHF",
    "PK": "PKR",
    "IN": "INR",
}


def resolve_timezone_offset(tz_name: str | None) -> timezone | None:
    """Resolve named timezone abbreviation or numeric offset to datetime.timezone."""
    if not tz_name:
        return None
    cleaned = tz_name.strip().upper()
    if cleaned in ("UTC", "GMT", "Z"):
        return UTC
    if cleaned == "IST":
        return timezone(timedelta(hours=5, minutes=30))
    if cleaned in _TIMEZONE_OFFSETS:
        return timezone(timedelta(hours=_TIMEZONE_OFFSETS[cleaned]))
    # Numeric offset format like +09:00, -0500, +08
    match = re.fullmatch(r"([+-])(\d{1,2})(?::?(\d{2}))?", cleaned)
    if match:
        sign = 1 if match.group(1) == "+" else -1
        hours = int(match.group(2))
        minutes = int(match.group(3) or 0)
        return timezone(sign * timedelta(hours=hours, minutes=minutes))
    return None


def parse_flexible_datetime(raw: str | None, *, default_tz: str | None = None) -> datetime | None:
    """Parse ISO, slash, dash, written, and human date strings into UTC datetimes."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None

    tz = resolve_timezone_offset(default_tz) or UTC

    # 1. Standard ISO YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        parts = [int(p) for p in text.split("-")]
        return datetime(parts[0], parts[1], parts[2], tzinfo=UTC)

    # 2. Slashes or Dots: YYYY/MM/DD or YYYY.MM.DD
    match = re.fullmatch(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})", text)
    if match:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=UTC)

    # 3. European D/M/YYYY or DD-MM-YYYY
    match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", text)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        if month <= 12 and day <= 31:
            return datetime(year, month, day, tzinfo=UTC)

    # 4. Standard ISO with Time: YYYY-MM-DDTHH:MM:SS
    try:
        iso_parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if iso_parsed.tzinfo is None:
            iso_parsed = iso_parsed.replace(tzinfo=tz)
        return iso_parsed.astimezone(UTC)
    except ValueError:
        pass

    # 5. Written dates
    text_lower = text.lower()
    # 5a. Day Month Year: e.g. "5 Nov 2027" or "5th November 2027"
    day_month_match = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:,)?\s+(\d{4})",
        text_lower,
    )
    if day_month_match:
        day = int(day_month_match.group(1))
        month_str = day_month_match.group(2)
        year = int(day_month_match.group(3))
        if month_str in _MONTH_NAMES:
            month = _MONTH_NAMES[month_str]
            return datetime(year, month, day, tzinfo=UTC)

    # 5b. Month Day Year: e.g. "November 5, 2027" or "Nov 5th, 2027"
    month_day_match = re.search(
        r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(\d{4})",
        text_lower,
    )
    if month_day_match:
        month_str = month_day_match.group(1)
        day = int(month_day_match.group(2))
        year = int(month_day_match.group(3))
        if month_str in _MONTH_NAMES:
            month = _MONTH_NAMES[month_str]
            return datetime(year, month, day, tzinfo=UTC)

    # 5c. Month Year: e.g. "November 2027" (default to 1st of month)
    month_year_match = re.search(r"([a-z]+)\s+(\d{4})", text_lower)
    if month_year_match and month_year_match.group(1) in _MONTH_NAMES:
        month = _MONTH_NAMES[month_year_match.group(1)]
        year = int(month_year_match.group(2))
        return datetime(year, month, 1, tzinfo=UTC)

    return None


def disambiguate_currency(currency_symbol: str | None, country_code: str | None) -> str:
    """Disambiguate generic $, £, €, or raw text into standard ISO 3-letter currency code."""
    if not currency_symbol:
        if country_code and country_code.upper() in _COUNTRY_CURRENCY_MAP:
            return _COUNTRY_CURRENCY_MAP[country_code.upper()]
        return "USD"

    raw = currency_symbol.strip().upper()
    if raw in ("$", "DOLLAR", "DOLLARS", "USD"):
        if country_code and country_code.upper() in _COUNTRY_CURRENCY_MAP:
            return _COUNTRY_CURRENCY_MAP[country_code.upper()]
        return "USD"

    if raw in ("£", "GBP", "POUND", "POUNDS"):
        return "GBP"

    if raw in ("€", "EUR", "EURO", "EUROS"):
        return "EUR"

    if raw in ("¥", "JPY", "YEN", "円"):
        return "JPY"

    if raw in ("CNY", "RMB", "YUAN", "元"):
        return "CNY"

    if raw in ("AUD", "CAD", "SGD", "NZD", "HKD", "SEK", "CHF", "TRY", "KRW", "INR", "PKR"):
        return raw

    return raw[:10]
