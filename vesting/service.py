"""上层门面：供薪酬测算与报表调用。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .db import Store
from .expense import period_expense
from .models import Grant, Leave, Termination, VestingEvent
from .schedule import vesting_events


class VestingService:
    def __init__(self, store: Store) -> None:
        self._store = store

    # 事件录入
    def record_grant(self, grant: Grant) -> None:
        self._store.add_grant(grant)

    def record_leave(self, leave: Leave) -> None:
        self._store.add_leave(leave)

    def record_termination(self, term: Termination) -> None:
        self._store.add_termination(term)

    # 查询
    def _context(self, employee_id: str) -> tuple[list[Leave], Termination | None]:
        return self._store.leaves(employee_id), self._store.termination(employee_id)

    def vesting_schedule(self, grant_id: str) -> list[VestingEvent]:
        """一笔授予的完整归属日历。"""
        grant = self._store.grant(grant_id)
        leaves, termination = self._context(grant.employee_id)
        return vesting_events(grant, leaves, termination)

    def vested_shares(self, grant_id: str, as_of: date) -> int:
        """截至某日（含）的已归属股数。"""
        return sum(
            e.period_shares
            for e in self.vesting_schedule(grant_id)
            if not e.forfeited and e.vest_date <= as_of
        )

    def grant_expense(self, grant_id: str, start: date, end: date) -> Decimal:
        """一笔授予在区间（含首尾）内的费用。"""
        grant = self._store.grant(grant_id)
        leaves, termination = self._context(grant.employee_id)
        return period_expense(grant, leaves, termination, start, end)

    def company_expense(self, start: date, end: date) -> Decimal:
        """全公司在区间（含首尾）内的费用汇总。"""
        total = Decimal("0.00")
        for employee_id in self._store.employee_ids():
            leaves, termination = self._context(employee_id)
            for grant in self._store.grants(employee_id):
                total += period_expense(grant, leaves, termination, start, end)
        return total
