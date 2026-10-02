import random
import time
from datetime import date, timedelta

from equity_comp import (
    EquityCompService,
    Frequency,
    Grant,
    Leave,
    Store,
    Termination,
)


def make_grant(employee_id: str, grant_date: date, total_shares: int,
               years: int, frequency: Frequency, cliff: bool,
               fair_value_cents: int) -> Grant:
    return Grant(
        id=None,
        employee_id=employee_id,
        grant_date=grant_date,
        total_shares=total_shares,
        vesting_years=years,
        frequency=frequency,
        cliff=cliff,
        fair_value_cents=fair_value_cents,
    )


def build_population(store: Store, employees: int, grants_per_employee: int,
                     seed: int = 42) -> None:
    rng = random.Random(seed)
    for emp in range(employees):
        employee_id = f"emp-{emp}"
        for _ in range(grants_per_employee):
            store.add_grant(
                make_grant(
                    employee_id=employee_id,
                    grant_date=date(2021, 1, 1) + timedelta(days=rng.randrange(0, 700)),
                    total_shares=rng.randrange(1, 5000),
                    years=rng.randrange(1, 5),
                    frequency=rng.choice([Frequency.MONTHLY, Frequency.QUARTERLY]),
                    cliff=rng.random() < 0.5,
                    fair_value_cents=rng.randrange(1, 10000),
                )
            )
        if rng.random() < 0.3:
            start = date(2021, 6, 1) + timedelta(days=rng.randrange(0, 500))
            store.add_leave(
                Leave(id=None, employee_id=employee_id, start_date=start,
                      end_date=start + timedelta(days=rng.randrange(31, 120)))
            )
        if rng.random() < 0.2:
            store.set_termination(
                Termination(employee_id=employee_id,
                            termination_date=date(2022, 1, 1)
                            + timedelta(days=rng.randrange(0, 900)))
            )


def test_interval_splits_sum_to_whole_to_the_cent():
    store = Store(":memory:")
    build_population(store, employees=40, grants_per_employee=3)
    service = EquityCompService(store)
    rng = random.Random(11)
    full_start, full_end = date(2021, 1, 1), date(2026, 12, 31)
    whole = service.expense_cents(full_start, full_end)
    for _ in range(20):
        cuts = sorted(
            rng.sample(range((full_end - full_start).days + 1), rng.randrange(1, 12))
        )
        boundaries = [full_start + timedelta(days=c) for c in cuts]
        segments = []
        cursor = full_start
        for boundary in boundaries:
            if boundary > cursor:
                segments.append((cursor, boundary - timedelta(days=1)))
            cursor = boundary
        if cursor <= full_end:
            segments.append((cursor, full_end))
        total = sum(service.expense_cents(a, b) for a, b in segments)
        assert total == whole


def test_fully_vested_grant_lifetime_expense_equals_total_value():
    store = Store(":memory:")
    service = EquityCompService(store)
    cases = [
        (date(2021, 1, 31), 4800, 4, Frequency.MONTHLY, True, 1234),
        (date(2020, 2, 29), 999, 3, Frequency.QUARTERLY, False, 77),
        (date(2022, 7, 1), 1, 1, Frequency.MONTHLY, False, 1),
        (date(2021, 12, 15), 2500, 2, Frequency.QUARTERLY, True, 9999),
    ]
    for index, (grant_date, shares, years, frequency, cliff, fv) in enumerate(cases):
        employee_id = f"solo-{index}"
        grant_id = store.add_grant(
            make_grant(employee_id, grant_date, shares, years, frequency, cliff, fv)
        )
        end = date(grant_date.year + years + 1, grant_date.month, grant_date.day)
        total = service.expense_cents(grant_date, end, employee_id)
        assert total == shares * fv


def test_leave_freezes_recognition_before_leave_start():
    store = Store(":memory:")
    service = EquityCompService(store)
    store.add_grant(
        make_grant("emp", date(2022, 1, 15), 4800, 4, Frequency.MONTHLY, False, 1000)
    )
    leave_start = date(2022, 6, 1)
    before_leave = service.expense_cents(date(2022, 1, 15), leave_start - timedelta(days=1), "emp")
    store.add_leave(
        Leave(id=None, employee_id="emp", start_date=leave_start,
              end_date=date(2022, 8, 15))
    )
    after_leave = service.expense_cents(date(2022, 1, 15), leave_start - timedelta(days=1), "emp")
    # Recognition up to the day before the leave is frozen by the deferral.
    assert after_leave == before_leave
    # The full value is still recognized over the (extended) lifetime.
    lifetime = service.expense_cents(date(2022, 1, 15), date(2027, 6, 1), "emp")
    assert lifetime == 4800 * 1000


def test_company_wide_one_year_expense_performance():
    store = Store(":memory:")
    build_population(store, employees=5000, grants_per_employee=2, seed=1)
    service = EquityCompService(store)
    started = time.perf_counter()
    total = service.expense_cents(date(2022, 1, 1), date(2022, 12, 31))
    elapsed = time.perf_counter() - started
    assert isinstance(total, int)
    assert elapsed < 10, f"company-wide yearly expense took {elapsed:.2f}s"
