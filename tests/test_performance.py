"""规模：5000 员工 / 1 万笔授予，全年费用汇总 10 秒内返回。"""
import random
import time
import unittest
from datetime import date, timedelta
from decimal import Decimal

from vesting.db import Store
from vesting.models import Frequency, Grant, Leave, Termination
from vesting.service import VestingService


def build_service():
    random.seed(42)
    svc = VestingService(Store())
    for i in range(5000):
        emp = f"e{i}"
        for j in range(2):
            grant_date = date(2020, 1, 1) + timedelta(days=random.randint(0, 2000))
            svc.record_grant(
                Grant(
                    f"g{i}_{j}",
                    emp,
                    grant_date,
                    random.randint(100, 5000),
                    random.randint(1, 4),
                    random.choice([Frequency.MONTHLY, Frequency.QUARTERLY]),
                    random.random() < 0.3,
                    Decimal(random.randint(1, 20000)) / 100,
                )
            )
        if random.random() < 0.2:
            start = date(2023, 1, 1) + timedelta(days=random.randint(0, 700))
            svc.record_leave(
                Leave(f"l{i}", emp, start, start + timedelta(days=random.randint(31, 120)))
            )
        if random.random() < 0.15:
            svc.record_termination(
                Termination(emp, date(2024, 1, 1) + timedelta(days=random.randint(0, 700)))
            )
    return svc


class TestPerformance(unittest.TestCase):
    def test_company_year_expense_under_10s(self):
        svc = build_service()
        t0 = time.time()
        total = svc.company_expense(date(2025, 1, 1), date(2025, 12, 31))
        elapsed = time.time() - t0
        self.assertGreater(total, Decimal("0"))
        self.assertLess(elapsed, 10.0, f"took {elapsed:.2f}s")


if __name__ == "__main__":
    unittest.main()
