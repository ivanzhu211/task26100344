"""费用计算：线性确认、假期顺延冻结、离职冲回、区间拆分一致性。"""
import unittest
from datetime import date, timedelta
from decimal import Decimal

from vesting.expense import (
    _period_cumulative,
    _round_cents,
    cumulative_expense,
    period_expense,
)
from vesting.models import Frequency, Grant, Leave, Termination

ONE_DAY = timedelta(days=1)


def make_grant(shares=12, years=1, freq=Frequency.MONTHLY, fv="10.00"):
    return Grant("g", "e", date(2024, 1, 31), shares, years, freq, False, Decimal(fv))


class TestRounding(unittest.TestCase):
    def test_half_up(self):
        self.assertEqual(_round_cents(Decimal("0.075")), Decimal("0.08"))
        self.assertEqual(_round_cents(Decimal("0.074")), Decimal("0.07"))
        self.assertEqual(_round_cents(Decimal("-0.075")), Decimal("-0.08"))


class TestLinearRecognition(unittest.TestCase):
    def test_grant_day_zero(self):
        g = make_grant()
        self.assertEqual(
            cumulative_expense(g, [], None, date(2024, 1, 31)), Decimal("0.00")
        )

    def test_single_period_linear(self):
        """第1期 \$10，2024-01-31→2024-02-29 共29天，第9天确认 10*9/29=3.10。"""
        g = make_grant()
        self.assertEqual(
            _period_cumulative(g, 1, [], None, date(2024, 2, 9)), Decimal("3.10")
        )
        self.assertEqual(
            _period_cumulative(g, 1, [], None, date(2024, 2, 29)), Decimal("10.00")
        )
        self.assertEqual(
            _period_cumulative(g, 1, [], None, date(2024, 3, 1)), Decimal("10.00")
        )

    def test_full_cycle_total(self):
        """全部归属后，全周期费用 = 总股数 × 每股公允价值。"""
        g = make_grant(shares=100, years=2, fv="3.33")
        last = date(2026, 1, 31)
        total = period_expense(g, [], None, date(2024, 1, 31), last)
        self.assertEqual(total, Decimal("333.00"))


class TestLeaveDeferral(unittest.TestCase):
    def setUp(self):
        self.grant = make_grant()
        # 35 天假期，跨过第1期归属日 2024-02-29
        self.leave = Leave("l", "e", date(2024, 2, 10), date(2024, 3, 15))

    def test_short_leave_no_effect(self):
        """30天及以内的假期不影响结果。"""
        short = Leave("l", "e", date(2024, 2, 10), date(2024, 3, 10))  # 30天
        for d in (date(2024, 2, 9), date(2024, 2, 29), date(2024, 4, 4)):
            self.assertEqual(
                _period_cumulative(self.grant, 1, [short], None, d),
                _period_cumulative(self.grant, 1, [], None, d),
            )

    def test_freeze_and_resume(self):
        """冻结假期前一天的累计额，剩余部分到新的归属日重新线性。"""
        g, lv = self.grant, self.leave
        # 冻结点 2024-02-09：10*9/29 → 3.10
        self.assertEqual(
            _period_cumulative(g, 1, [lv], None, date(2024, 2, 9)), Decimal("3.10")
        )
        # 新归属日 2024-04-04（2月29日+35天），区间55天
        self.assertEqual(
            _period_cumulative(g, 1, [lv], None, date(2024, 2, 10)),
            Decimal("3.23"),  # 3.10 + 6.90/55 → 3.2254 → 3.23
        )
        self.assertEqual(
            _period_cumulative(g, 1, [lv], None, date(2024, 4, 4)), Decimal("10.00")
        )

    def test_multiple_leaves_sequential(self):
        """多段假期按开始日先后依次顺延。"""
        g = make_grant()
        leaves = [
            Leave("l1", "e", date(2024, 2, 10), date(2024, 3, 15)),  # 35天
            Leave("l2", "e", date(2024, 5, 1), date(2024, 6, 15)),  # 46天
        ]
        # 第1期：2月29日 → +35天 = 4月4日；4月4日 < 5月1日，不再顺延
        self.assertEqual(
            _period_cumulative(g, 1, leaves, None, date(2024, 4, 4)), Decimal("10.00")
        )
        # 第2期：3月31日 → +35 = 5月5日；5月5日 >= 5月1日 → 再 +46 = 6月20日
        self.assertEqual(
            _period_cumulative(g, 2, leaves, None, date(2024, 6, 20)), Decimal("10.00")
        )
        self.assertLess(
            _period_cumulative(g, 2, leaves, None, date(2024, 6, 19)), Decimal("10.00")
        )


class TestForfeiture(unittest.TestCase):
    def test_reversal_on_term_date(self):
        """作废的期从离职日起累计归零。"""
        g = make_grant()
        term = Termination("e", date(2024, 2, 20))
        # 第2期归属日 2024-03-31 > 离职日 → 作废
        before = _period_cumulative(g, 2, [], term, date(2024, 2, 19))
        self.assertEqual(before, Decimal("3.17"))  # 10*19/60 → 3.1667
        self.assertEqual(
            _period_cumulative(g, 2, [], term, date(2024, 2, 20)), Decimal("0.00")
        )
        self.assertEqual(
            _period_cumulative(g, 2, [], term, date(2024, 3, 31)), Decimal("0.00")
        )
        # 第1期归属日 2024-02-29 > 离职日 → 同样作废
        self.assertEqual(
            _period_cumulative(g, 1, [], term, date(2024, 2, 20)), Decimal("0.00")
        )

    def test_vested_periods_unaffected(self):
        """离职日当天及以前到达的归属日照常归属。"""
        g = make_grant()
        term = Termination("e", date(2024, 2, 29))
        self.assertEqual(
            _period_cumulative(g, 1, [], term, date(2024, 3, 1)), Decimal("10.00")
        )


class TestSplitConsistency(unittest.TestCase):
    def test_arbitrary_splits_sum_to_whole(self):
        """任意切分区间，各段之和与整段逐分相等。"""
        g = Grant("g", "e", date(2024, 1, 31), 1000, 4, Frequency.MONTHLY, False, Decimal("7.77"))
        leaves = [Leave("l", "e", date(2024, 6, 1), date(2024, 8, 15))]
        term = Termination("e", date(2026, 3, 15))
        start, end = date(2024, 1, 1), date(2027, 12, 31)
        whole = period_expense(g, leaves, term, start, end)
        # 按 7/30/365 天三种粒度切分
        for step in (7, 30, 365):
            parts = Decimal("0.00")
            d = start
            while d <= end:
                e = min(d + timedelta(days=step - 1), end)
                parts += period_expense(g, leaves, term, d, e)
                d = e + ONE_DAY
            self.assertEqual(parts, whole, f"step={step}")


if __name__ == "__main__":
    unittest.main()
