from __future__ import annotations

from datetime import date, timedelta

from .models import Grant, Leave, Termination
from .schedule import (
    LEAVE_SHIFT_THRESHOLD_DAYS,
    _period_count,
    period_shares,
    raw_vest_date,
)


def _round_half_up_div(numerator: int, denominator: int) -> int:
    """Round ``numerator / denominator`` (both non-negative) half up."""
    return (numerator * 2 + denominator) // (2 * denominator)


class _RecognitionCurve:
    """Piecewise-linear cumulative recognition curve for one vesting period.

    Anchors are (date, cents) points; between anchors the curve is linear by
    day. Before the first anchor and after the last the value is flat.
    """

    def __init__(self, grant_date: date, vest_date: date, value_cents: int) -> None:
        self._anchors: list[tuple[date, int]] = [
            (grant_date, 0),
            (vest_date, value_cents),
        ]

    @property
    def vest_date(self) -> date:
        return self._anchors[-1][0]

    @property
    def start_date(self) -> date:
        return self._anchors[0][0]

    def cents(self, d: date) -> int:
        anchors = self._anchors
        if d <= anchors[0][0]:
            return anchors[0][1]
        for (d0, v0), (d1, v1) in zip(anchors, anchors[1:]):
            if d <= d1:
                span = (d1 - d0).days
                elapsed = (d - d0).days
                return _round_half_up_div(v0 * span + (v1 - v0) * elapsed, span)
        return anchors[-1][1]

    def defer(self, leave_start: date, days: int) -> None:
        """Freeze the rounded cumulative as of the day before the leave and
        re-spread the remainder linearly to the shifted vest date."""
        if self.vest_date < leave_start:
            return
        freeze_date = leave_start - timedelta(days=1)
        frozen = self.cents(freeze_date)
        value = self._anchors[-1][1]
        kept = [anchor for anchor in self._anchors if anchor[0] < freeze_date]
        kept.append((freeze_date, frozen))
        kept.append((self.vest_date + timedelta(days=days), value))
        self._anchors = kept


def _period_curves(
    grant: Grant,
    leaves: list[Leave],
) -> list[_RecognitionCurve | None]:
    shares = period_shares(grant)
    effective = sorted(
        (lv for lv in leaves if lv.days > LEAVE_SHIFT_THRESHOLD_DAYS),
        key=lambda lv: (lv.start_date, lv.end_date),
    )
    curves: list[_RecognitionCurve | None] = [None]
    for k in range(1, _period_count(grant) + 1):
        if shares[k] == 0:
            curves.append(None)
            continue
        curve = _RecognitionCurve(
            grant.grant_date,
            raw_vest_date(grant, k),
            shares[k] * grant.fair_value_cents,
        )
        for leave in effective:
            curve.defer(leave.start_date, leave.days)
        curves.append(curve)
    return curves


def grant_expense_cents(
    grant: Grant,
    leaves: list[Leave],
    termination: Termination | None,
    start: date,
    end: date,
) -> int:
    """Expense in cents recognized over the inclusive range [start, end]."""
    if end < start:
        return 0
    prev = start - timedelta(days=1)
    term_date = termination.termination_date if termination is not None else None
    effective = sorted(
        (lv for lv in leaves if lv.days > LEAVE_SHIFT_THRESHOLD_DAYS),
        key=lambda lv: (lv.start_date, lv.end_date),
    )
    shares = period_shares(grant)
    grant_date = grant.grant_date
    total = 0
    for k in range(1, _period_count(grant) + 1):
        period_shares_k = shares[k]
        if period_shares_k == 0:
            continue
        value = period_shares_k * grant.fair_value_cents
        if not effective:
            vest = raw_vest_date(grant, k)
            forfeited = term_date is not None and vest > term_date
            if forfeited and prev >= term_date:
                continue
            if not forfeited and vest <= prev:
                continue
            if grant_date > end:
                continue
            total += _simple_cents(grant_date, vest, value, term_date, forfeited, end)
            total -= _simple_cents(grant_date, vest, value, term_date, forfeited, prev)
        else:
            curve = _RecognitionCurve(grant_date, raw_vest_date(grant, k), value)
            for leave in effective:
                curve.defer(leave.start_date, leave.days)
            vest = curve.vest_date
            forfeited = term_date is not None and vest > term_date
            if forfeited and prev >= term_date:
                continue
            if not forfeited and vest <= prev:
                continue
            if curve.start_date > end:
                continue
            total += _curve_cents(curve, term_date, forfeited, end)
            total -= _curve_cents(curve, term_date, forfeited, prev)
    return total


def _simple_cents(
    grant_date: date,
    vest_date: date,
    value: int,
    term_date: date | None,
    forfeited: bool,
    d: date,
) -> int:
    if forfeited and d >= term_date:
        return 0
    if d <= grant_date:
        return 0
    if d >= vest_date:
        return value
    span = (vest_date - grant_date).days
    elapsed = (d - grant_date).days
    return _round_half_up_div(value * elapsed, span)


def _curve_cents(
    curve: _RecognitionCurve,
    term_date: date | None,
    forfeited: bool,
    d: date,
) -> int:
    if forfeited and d >= term_date:
        return 0
    return curve.cents(d)
