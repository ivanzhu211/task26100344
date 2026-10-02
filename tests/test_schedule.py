"""归属日历：月末授予、闰年、悬崖期、股数取整。"""
import unittest
from datetime import date
from decimal import Decimal

from vesting.models import Frequency, Grant
from vesting.schedule import vesting_events


def make_grant(grant_date, shares, years, freq, cliff=False):
    return Grant("g", "e", grant_date, shares, years, freq, cliff, Decimal("10.00"))


class TestMonthEndVesting(unittest.TestCase):
    def test_jan31_monthly_dates(self):
        """1月31日授予：2月取月末，之后回到31日。"""
        g = make_grant(date(2024, 1, 31), 48, 4, Frequency.MONTHLY)
        events = vesting_events(g, [], None)
        self.assertEqual(len(events), 48)
        dates = [e.vest_date for e in events]
        self.assertEqual(dates[0], date(2024, 2, 29))  # 闰年2月
        self.assertEqual(dates[1], date(2024, 3, 31))
        self.assertEqual(dates[2], date(2024, 4, 30))
        self.assertEqual(dates[3], date(2024, 5, 31))
        self.assertEqual(dates[11], date(2025, 1, 31))
        self.assertEqual(dates[12], date(2025, 2, 28))  # 平年2月
        self.assertEqual(dates[13], date(2025, 3, 31))
        self.assertEqual(dates[-1], date(2028, 1, 31))

    def test_feb29_leap_grant(self):
        """闰年2月29日授予：平年2月取28日，之后回到29日。"""
        g = make_grant(date(2024, 2, 29), 48, 4, Frequency.MONTHLY)
        dates = [e.vest_date for e in vesting_events(g, [], None)]
        self.assertEqual(dates[0], date(2024, 3, 29))
        self.assertEqual(dates[10], date(2025, 1, 29))
        self.assertEqual(dates[11], date(2025, 2, 28))  # 平年
        self.assertEqual(dates[12], date(2025, 3, 29))  # 回到29日
        self.assertEqual(dates[-1], date(2028, 2, 29))  # 又是闰年

    def test_shares_floor_and_total(self):
        """累计股数向下取整，末期恰好等于总股数。"""
        g = make_grant(date(2024, 1, 15), 100, 1, Frequency.MONTHLY)
        events = vesting_events(g, [], None)
        expected_cum = [8, 16, 25, 33, 41, 50, 58, 66, 75, 83, 91, 100]
        self.assertEqual([e.cumulative_shares for e in events], expected_cum)
        self.assertEqual(sum(e.period_shares for e in events), 100)
        self.assertEqual(events[-1].cumulative_shares, 100)

    def test_every_period_shares(self):
        """48股4年按月：每期1股。"""
        g = make_grant(date(2024, 1, 31), 48, 4, Frequency.MONTHLY)
        events = vesting_events(g, [], None)
        self.assertTrue(all(e.period_shares == 1 for e in events))
        self.assertEqual(events[-1].cumulative_shares, 48)


class TestCliff(unittest.TestCase):
    def test_cliff_merges_first_12_months(self):
        """悬崖期：前12个月并入第12个月那一期。"""
        g = make_grant(date(2024, 1, 31), 48, 4, Frequency.MONTHLY, cliff=True)
        events = vesting_events(g, [], None)
        self.assertEqual(len(events), 48 - 11)
        self.assertEqual(events[0].period, 12)
        self.assertEqual(events[0].vest_date, date(2025, 1, 31))
        self.assertEqual(events[0].period_shares, 12)
        self.assertEqual(events[0].cumulative_shares, 12)
        self.assertEqual(events[1].period, 13)
        self.assertEqual(events[1].period_shares, 1)
        self.assertEqual(events[-1].cumulative_shares, 48)

    def test_cliff_quarterly(self):
        """按季归属的悬崖期并入第4期（第12个月）。"""
        g = make_grant(date(2024, 1, 31), 48, 4, Frequency.QUARTERLY, cliff=True)
        events = vesting_events(g, [], None)
        self.assertEqual(len(events), 16 - 3)
        self.assertEqual(events[0].period, 4)
        self.assertEqual(events[0].vest_date, date(2025, 1, 31))
        self.assertEqual(events[0].period_shares, 12)


class TestQuarterly(unittest.TestCase):
    def test_quarterly_dates(self):
        g = make_grant(date(2024, 1, 31), 16, 4, Frequency.QUARTERLY)
        events = vesting_events(g, [], None)
        self.assertEqual(len(events), 16)
        self.assertEqual(events[0].vest_date, date(2024, 4, 30))
        self.assertEqual(events[1].vest_date, date(2024, 7, 31))
        self.assertEqual(events[2].vest_date, date(2024, 10, 31))
        self.assertEqual(events[-1].vest_date, date(2028, 1, 31))
        self.assertEqual(events[-1].cumulative_shares, 16)


if __name__ == "__main__":
    unittest.main()
