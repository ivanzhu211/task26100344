from __future__ import annotations

from datetime import date, timedelta

from .dates import add_months
from .models import Grant, Leave, Termination, VestingEvent


CLIFF_MONTHS = 12
LEAVE_SHIFT_THRESHOLD_DAYS = 30


def _period_count(grant: Grant) -> int:
    return grant.vesting_years * (12 if grant.frequency.value == "monthly" else 4)


def _period_month_offset(grant: Grant, period: int) -> int:
    step = 1 if grant.frequency.value == "monthly" else 3
    return step * period


def raw_vest_date(grant: Grant, period: int) -> date:
    return add_months(grant.grant_date, _period_month_offset(grant, period))


def period_shares(grant: Grant) -> list[int]:
    """Shares vesting at each period (1-indexed list, index 0 unused)."""
    periods = _period_count(grant)
    cumulative = [
        grant.total_shares * k // periods for k in range(periods + 1)
    ]
    shares = [0] * (periods + 1)
    for k in range(1, periods + 1):
        if grant.cliff and _period_month_offset(grant, k) < CLIFF_MONTHS:
            shares[k] = 0
        elif grant.cliff and _period_month_offset(grant, k) == CLIFF_MONTHS:
            shares[k] = cumulative[k]
        else:
            shares[k] = cumulative[k] - cumulative[k - 1]
    return shares


def shifted_vest_dates(
    grant: Grant,
    leaves: list[Leave],
) -> list[date]:
    """Vest dates per period after applying qualifying leaves in start order."""
    periods = _period_count(grant)
    dates = [None] + [raw_vest_date(grant, k) for k in range(1, periods + 1)]
    effective = sorted(
        (lv for lv in leaves if lv.days > LEAVE_SHIFT_THRESHOLD_DAYS),
        key=lambda lv: (lv.start_date, lv.end_date),
    )
    for leave in effective:
        shift = timedelta(days=leave.days)
        for k in range(1, periods + 1):
            if dates[k] >= leave.start_date:
                dates[k] = dates[k] + shift
    return dates


def vesting_events(
    grant: Grant,
    leaves: list[Leave],
    termination: Termination | None,
) -> list[VestingEvent]:
    """Full vesting calendar for one grant after leave shifts and forfeiture."""
    shares = period_shares(grant)
    dates = shifted_vest_dates(grant, leaves)
    events = []
    cumulative = 0
    for k in range(1, _period_count(grant) + 1):
        forfeited = (
            termination is not None and dates[k] > termination.termination_date
        )
        if not forfeited:
            cumulative += shares[k]
        events.append(
            VestingEvent(
                grant_id=grant.id,
                period=k,
                vest_date=dates[k],
                shares=shares[k],
                cumulative_shares=cumulative,
                forfeited=forfeited,
            )
        )
    return events


def vested_shares_as_of(
    grant: Grant,
    leaves: list[Leave],
    termination: Termination | None,
    as_of: date,
) -> int:
    """Cumulative vested shares for one grant as of ``as_of`` (inclusive)."""
    total = 0
    for event in vesting_events(grant, leaves, termination):
        if not event.forfeited and event.vest_date <= as_of:
            total += event.shares
    return total
