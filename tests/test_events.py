import random
from datetime import date, timedelta

import pytest

from equity_comp import (
    EquityCompService,
    Frequency,
    Grant,
    Leave,
    Store,
    Termination,
)

GRANT_DATE = date(2022, 1, 15)
LEAVE_START = date(2022, 6, 1)
LEAVE_END = date(2022, 8, 15)  # 76 days, crosses several vest dates
LEAVE_DAYS = (LEAVE_END - LEAVE_START).days + 1
TERM_DATE = date(2023, 3, 1)


def make_grant() -> Grant:
    return Grant(
        id=None,
        employee_id="emp-1",
        grant_date=GRANT_DATE,
        total_shares=4800,
        vesting_years=4,
        frequency=Frequency.MONTHLY,
        cliff=False,
        fair_value_cents=1234,
    )


def make_leave() -> Leave:
    return Leave(id=None, employee_id="emp-1", start_date=LEAVE_START, end_date=LEAVE_END)


def make_termination() -> Termination:
    return Termination(employee_id="emp-1", termination_date=TERM_DATE)


def build_service(order: str) -> tuple[EquityCompService, int]:
    store = Store(":memory:")
    service = EquityCompService(store)
    grant_id = None
    for step in order:
        if step == "g":
            grant_id = store.add_grant(make_grant())
        elif step == "l":
            store.add_leave(make_leave())
        elif step == "t":
            store.set_termination(make_termination())
    return service, grant_id


def sample_intervals(seed: int = 7) -> list[tuple[date, date]]:
    rng = random.Random(seed)
    intervals = []
    for _ in range(25):
        start = GRANT_DATE + timedelta(days=rng.randrange(0, 900))
        end = start + timedelta(days=rng.randrange(0, 400))
        intervals.append((start, end))
    return intervals


def test_leave_shifts_vest_dates_by_leave_length():
    service, grant_id = build_service("glt")
    calendar = service.vesting_calendar(grant_id)
    # Period 4 vests 2022-05-15, before the leave start: untouched.
    assert calendar[3].vest_date == date(2022, 5, 15)
    # Period 5 vests 2022-06-15, on/after the leave start: shifted by 76 days.
    assert calendar[4].vest_date == date(2022, 6, 15) + timedelta(days=LEAVE_DAYS)
    assert calendar[5].vest_date == date(2022, 7, 15) + timedelta(days=LEAVE_DAYS)
    assert calendar[6].vest_date == date(2022, 8, 15) + timedelta(days=LEAVE_DAYS)
    assert calendar[7].vest_date == date(2022, 9, 15) + timedelta(days=LEAVE_DAYS)


def test_short_leave_has_no_effect():
    store = Store(":memory:")
    service = EquityCompService(store)
    grant_id = store.add_grant(make_grant())
    store.add_leave(
        Leave(id=None, employee_id="emp-1",
              start_date=date(2022, 6, 1), end_date=date(2022, 6, 30))
    )
    calendar = service.vesting_calendar(grant_id)
    assert calendar[4].vest_date == date(2022, 6, 15)
    assert calendar[5].vest_date == date(2022, 7, 15)


def test_termination_forfeits_later_periods():
    service, grant_id = build_service("glt")
    calendar = service.vesting_calendar(grant_id)
    for event in calendar:
        assert event.forfeited == (event.vest_date > TERM_DATE)
    vested = service.vested_shares("emp-1", TERM_DATE)
    expected = sum(
        event.shares
        for event in calendar
        if not event.forfeited and event.vest_date <= TERM_DATE
    )
    assert vested == expected
    assert vested > 0
    # Nothing further vests after the termination date.
    assert service.vested_shares("emp-1", date(2026, 1, 1)) == vested


@pytest.mark.parametrize("order", ["glt", "gtl", "lgt", "ltg", "tgl", "tlg"])
def test_results_are_identical_for_any_entry_order(order: str):
    reference_service, reference_id = build_service("glt")
    service, grant_id = build_service(order)
    assert service.vesting_calendar(grant_id) == reference_service.vesting_calendar(
        reference_id
    )
    for start, end in sample_intervals():
        assert service.expense_cents(start, end, "emp-1") == (
            reference_service.expense_cents(start, end, "emp-1")
        )


def test_retroactive_leave_entry_converges_to_same_result():
    store = Store(":memory:")
    service = EquityCompService(store)
    grant_id = store.add_grant(make_grant())
    store.set_termination(make_termination())
    before = service.vesting_calendar(grant_id)
    # The leave is recorded long after the fact.
    store.add_leave(make_leave())
    after = service.vesting_calendar(grant_id)
    reference_service, reference_id = build_service("glt")
    assert after == reference_service.vesting_calendar(reference_id)
    assert before != after


def test_termination_reversal_equals_previously_recognized_forfeited_amount():
    service, _ = build_service("glt")
    from equity_comp.expense import _period_curves

    curves = _period_curves(make_grant(), [make_leave()])
    day_before = TERM_DATE - timedelta(days=1)
    forfeited_recognized = sum(
        curve.cents(day_before)
        for curve in curves[1:]
        if curve is not None and curve.vest_date > TERM_DATE
    )
    continuing_delta = sum(
        curve.cents(TERM_DATE) - curve.cents(day_before)
        for curve in curves[1:]
        if curve is not None and curve.vest_date <= TERM_DATE
    )
    assert forfeited_recognized > 0
    # The single-day expense on the termination date is the continuing
    # periods' normal daily recognition minus the forfeiture reversal.
    single_day = service.expense_cents(TERM_DATE, TERM_DATE, "emp-1")
    assert single_day == continuing_delta - forfeited_recognized
    # Lifetime expense equals the full value of the non-forfeited periods.
    calendar = service.vesting_calendar(
        build_service("glt")[1]
    )
    surviving_shares = sum(event.shares for event in calendar if not event.forfeited)
    lifetime = service.expense_cents(GRANT_DATE, date(2027, 1, 1), "emp-1")
    assert lifetime == surviving_shares * 1234
