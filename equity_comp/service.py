from __future__ import annotations

from datetime import date
from itertools import groupby

from .expense import grant_expense_cents
from .models import VestingEvent
from .schedule import vested_shares_as_of, vesting_events
from .store import Store


class EquityCompService:
    """Query facade used by compensation modelling and reporting callers."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def vesting_calendar(self, grant_id: int) -> list[VestingEvent]:
        grant = self._store.get_grant(grant_id)
        leaves = self._store.list_leaves(grant.employee_id)
        termination = self._store.get_termination(grant.employee_id)
        return vesting_events(grant, leaves, termination)

    def vested_shares(self, employee_id: str, as_of: date) -> int:
        leaves = self._store.list_leaves(employee_id)
        termination = self._store.get_termination(employee_id)
        return sum(
            vested_shares_as_of(grant, leaves, termination, as_of)
            for grant in self._store.list_grants(employee_id)
        )

    def expense_cents(
        self,
        start: date,
        end: date,
        employee_id: str | None = None,
    ) -> int:
        grants = self._store.list_grants(employee_id)
        grants.sort(key=lambda grant: grant.employee_id)
        total = 0
        for emp_id, group in groupby(grants, key=lambda grant: grant.employee_id):
            leaves = self._store.list_leaves(emp_id)
            termination = self._store.get_termination(emp_id)
            for grant in group:
                total += grant_expense_cents(grant, leaves, termination, start, end)
        return total
