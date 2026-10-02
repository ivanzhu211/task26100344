"""股权激励费用计算：逐期累计确认曲线与区间费用。

确认曲线（单期）：
- 从授予日（累计 0）到归属日（累计满额）按天线性；
- 每段触发顺延的假期，把假期开始前一天的累计额（按当时曲线按分取整）
  冻结为节点，剩余部分从该节点到新的归属日重新按天线性；
- 作废的期从离职日起累计归零（离职日当天冲回）；
- 任意一天的累计额按分四舍五入（半分进位）。
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from .models import Grant, Leave, Termination
from .schedule import (
    _base_vest_date,
    _first_period,
    apply_leaves,
    leave_days,
    total_periods,
)

_CENT = Decimal("0.01")
_ONE_DAY = timedelta(days=1)


def _round_cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _curve_at(knots: list[tuple[date, Decimal]], day: date) -> Decimal:
    """按节点序列（末节点为归属日满额）计算某天的累计确认额。"""
    if day <= knots[0][0]:
        return knots[0][1]
    for (d0, a0), (d1, a1) in zip(knots, knots[1:]):
        if day <= d1:
            span = (d1 - d0).days
            if span == 0:
                return a1
            ratio = Decimal((day - d0).days) / Decimal(span)
            return _round_cents(a0 + (a1 - a0) * ratio)
    return knots[-1][1]


def _period_knots(
    grant: Grant,
    period: int,
    leaves: list[Leave],
) -> list[tuple[date, Decimal]]:
    """单期确认曲线的节点序列 [(日期, 当日累计额)]，末节点为归属日满额。"""
    n = total_periods(grant)
    cum_shares = grant.total_shares * period // n
    prev_shares = grant.total_shares * (period - 1) // n
    value = _round_cents(grant.fair_value * (cum_shares - prev_shares))

    base = _base_vest_date(grant, period)
    _, applied = apply_leaves(base, leaves)

    knots: list[tuple[date, Decimal]] = [(grant.grant_date, Decimal("0.00"))]
    current_vest = base
    for leave in applied:
        freeze_day = max(leave.start_date - _ONE_DAY, grant.grant_date)
        amount = _curve_at(knots + [(current_vest, value)], freeze_day)
        knots.append((freeze_day, amount))
        current_vest = current_vest + timedelta(days=leave_days(leave))
    knots.append((current_vest, value))
    return knots


def _period_cumulative(
    grant: Grant,
    period: int,
    leaves: list[Leave],
    termination: Termination | None,
    as_of: date,
) -> Decimal:
    knots = _period_knots(grant, period, leaves)
    vest_date = knots[-1][0]
    if termination is not None and vest_date > termination.term_date:
        # 作废的期：离职日起累计归零
        if as_of >= termination.term_date:
            return Decimal("0.00")
    return _curve_at(knots, as_of)


def cumulative_expense(
    grant: Grant,
    leaves: list[Leave],
    termination: Termination | None,
    as_of: date,
) -> Decimal:
    """一笔授予截至某日（含）的累计确认费用（美元，精确到分）。"""
    total = Decimal("0.00")
    for period in range(_first_period(grant), total_periods(grant) + 1):
        total += _period_cumulative(grant, period, leaves, termination, as_of)
    return total


def period_expense(
    grant: Grant,
    leaves: list[Leave],
    termination: Termination | None,
    start: date,
    end: date,
) -> Decimal:
    """一段日期区间（含首尾）的费用。"""
    if end < start:
        return Decimal("0.00")
    return cumulative_expense(grant, leaves, termination, end) - cumulative_expense(
        grant, leaves, termination, start - _ONE_DAY
    )
