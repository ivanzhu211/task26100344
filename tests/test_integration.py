"""集成：事后补录长假 + 离职，录入顺序不变性，冲回额校验。"""
import unittest
from datetime import date, timedelta
from decimal import Decimal

from vesting.db import Store
from vesting.expense import _period_cumulative
from vesting.models import Frequency, Grant, Leave, Termination
from vesting.schedule import vesting_events
from vesting.service import VestingService

GRANT = Grant("g1", "e1", date(2024, 1, 31), 48, 4, Frequency.MONTHLY, False, Decimal("10.00"))
LEAVE = Leave("l1", "e1", date(2024, 3, 1), date(2024, 4, 15))  # 46天，事后补录
TERM = Termination("e1", date(2025, 6, 30))


def build_service(order):
    svc = VestingService(Store())
    for item in order:
        if isinstance(item, Grant):
            svc.record_grant(item)
        elif isinstance(item, Leave):
            svc.record_leave(item)
        else:
            svc.record_termination(item)
    return svc


class TestRecordingOrderInvariance(unittest.TestCase):
    ORDERS = [
        [GRANT, LEAVE, TERM],
        [TERM, GRANT, LEAVE],
        [LEAVE, TERM, GRANT],
        [TERM, LEAVE, GRANT],
    ]
    INTERVALS = [
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2024, 3, 1), date(2024, 5, 31)),
        (date(2025, 6, 30), date(2025, 6, 30)),
        (date(2025, 7, 1), date(2025, 12, 31)),
        (date(2024, 1, 31), date(2028, 1, 31)),
    ]

    def test_schedule_and_expense_identical_across_orders(self):
        reference = build_service(self.ORDERS[0])
        ref_schedule = reference.vesting_schedule("g1")
        for order in self.ORDERS[1:]:
            svc = build_service(order)
            self.assertEqual(svc.vesting_schedule("g1"), ref_schedule)
            for start, end in self.INTERVALS:
                self.assertEqual(
                    svc.grant_expense("g1", start, end),
                    reference.grant_expense("g1", start, end),
                    f"order={order}, interval=({start},{end})",
                )

    def test_leave_defers_schedule(self):
        svc = build_service([GRANT, LEAVE, TERM])
        schedule = svc.vesting_schedule("g1")
        # 第2期原归属日 2024-03-31，在假期开始后 → 顺延46天至 2024-05-16
        self.assertEqual(schedule[1].vest_date, date(2024, 5, 16))
        # 第1期 2024-02-29 在假期开始前 → 不动
        self.assertEqual(schedule[0].vest_date, date(2024, 2, 29))

    def test_termination_forfeits_later_periods(self):
        svc = build_service([GRANT, LEAVE, TERM])
        schedule = svc.vesting_schedule("g1")
        vested = [e for e in schedule if not e.forfeited]
        forfeited = [e for e in schedule if e.forfeited]
        self.assertTrue(all(e.vest_date <= TERM.term_date for e in vested))
        self.assertTrue(all(e.vest_date > TERM.term_date for e in forfeited))
        self.assertTrue(len(forfeited) > 0)


class TestReversalAmount(unittest.TestCase):
    def test_reversal_equals_previously_recognized(self):
        """离职日的冲回额 = 作废各期此前已确认的合计。"""
        leaves, term = [LEAVE], TERM
        forfeited = [
            e.period
            for e in vesting_events(GRANT, leaves, term)
            if e.forfeited
        ]
        active = [
            e.period
            for e in vesting_events(GRANT, leaves, term)
            if not e.forfeited
        ]
        day_before = TERM.term_date - timedelta(days=1)
        reversal = sum(
            _period_cumulative(GRANT, p, leaves, term, day_before) for p in forfeited
        )
        accrual_that_day = sum(
            _period_cumulative(GRANT, p, leaves, term, TERM.term_date)
            - _period_cumulative(GRANT, p, leaves, term, day_before)
            for p in active
        )
        self.assertGreater(reversal, Decimal("0.00"))
        svc = build_service([GRANT, LEAVE, TERM])
        single_day = svc.grant_expense("g1", TERM.term_date, TERM.term_date)
        self.assertEqual(single_day, accrual_that_day - reversal)


if __name__ == "__main__":
    unittest.main()
