from __future__ import annotations

from datetime import date


_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _month_length(year: int, month: int) -> int:
    if month == 2 and _is_leap(year):
        return 29
    return _DAYS_IN_MONTH[month - 1]


def add_months(d: date, months: int) -> date:
    """Shift ``d`` by ``months`` months, clamping the day to the month end."""
    total = d.year * 12 + (d.month - 1) + months
    year, month = total // 12, total % 12 + 1
    day = min(d.day, _month_length(year, month))
    return date(year, month, day)
