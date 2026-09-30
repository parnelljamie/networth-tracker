"""The only place "now" is read from. The engine never calls this; callers pass dates in."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
UTC = ZoneInfo("UTC")


def today() -> date:
    return datetime.now(LONDON).date()


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_utc_naive() -> datetime:
    """`now_utc()` with tzinfo stripped, for arithmetic against SQLite DateTime columns —
    SQLite has no real timezone-aware storage, so values always round-trip naive."""
    return now_utc().replace(tzinfo=None)
