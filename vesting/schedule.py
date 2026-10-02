"""归属日历计算：归属日、股数、假期顺延、离职作废。"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from .models import Grant, Leave, Termination, VestingEvent

LEAVE_THRESHOLD_DAYS = 30  # 超过 30 天的假期才触发顺延
CLIFF_MONTHS = 12


def _add_months(d: date, months: int) -> date:
    """加若干月，日不存在时取当月最后一天（各期独立从授予日起算）。"""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def leave_days(leave: Leave) -> int:
    """假期天数（含首尾）。"""
    return (leave.end_date - leave.start_date).days + 1


def total_periods(grant: Grant) -> int:
    per_year = 12 if grant.frequency.value == "monthly" else 4
    return grant.vesting_years * per_year


def _base_vest_date(grant: Grant, period: int) -> date:
    step = 1 if grant.frequency.value == "monthly" else 3
    return _add_months(grant.grant_date, step * period)


def _first_period(grant: Grant) -> int:
    """带悬崖期时，前 12 个月的各期并入第 12 个月那一期。"""
    if not grant.cliff:
        return 1
    step = 1 if grant.frequency.value == "monthly" else 3
    return CLIFF_MONTHS // step


def apply_leaves(base: date, leaves: list[Leave]) -> tuple[date, list[Leave]]:
    """对一个归属日依次应用假期顺延。

    返回 (顺延后的日期, 实际触发顺延的假期（按应用顺序）)。
    判断用的是已经顺延过的日期。
    """
    qualifying = [l for l in leaves if leave_days(l) > LEAVE_THRESHOLD_DAYS]
    qualifying.sort(key=lambda l: (l.start_date, l.leave_id))
    applied: list[Leave] = []
    current = base
    for leave in qualifying:
        if current >= leave.start_date:
            applied.append(leave)
            current = current + timedelta(days=leave_days(leave))
    return current, applied


def vesting_events(
    grant: Grant,
    leaves: list[Leave],
    termination: Termination | None,
) -> list[VestingEvent]:
    """计算一笔授予的全部归属期（含顺延与作废标记）。"""
    n = total_periods(grant)
    first = _first_period(grant)
    periods = list(range(first, n + 1))

    events: list[VestingEvent] = []
    prev_cum = 0
    for k in periods:
        vest_date, _ = apply_leaves(_base_vest_date(grant, k), leaves)
        cum = grant.total_shares * k // n
        forfeited = termination is not None and vest_date > termination.term_date
        events.append(
            VestingEvent(
                grant_id=grant.grant_id,
                period=k,
                vest_date=vest_date,
                cumulative_shares=cum,
                period_shares=cum - prev_cum,
                forfeited=forfeited,
            )
        )
        prev_cum = cum
    return events
