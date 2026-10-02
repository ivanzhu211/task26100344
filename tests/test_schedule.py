from datetime import date

from equity_comp.models import Frequency, Grant
from equity_comp.schedule import period_shares, vesting_events


def make_grant(
    grant_date: date,
    total_shares: int,
    vesting_years: int,
    frequency: Frequency,
    cliff: bool,
) -> Grant:
    return Grant(
        id=1,
        employee_id="emp",
        grant_date=grant_date,
        total_shares=total_shares,
        vesting_years=vesting_years,
        frequency=frequency,
        cliff=cliff,
        fair_value_cents=500,
    )


def test_jan31_monthly_dates_clamp_and_recover():
    grant = make_grant(date(2021, 1, 31), 4800, 4, Frequency.MONTHLY, cliff=False)
    events = vesting_events(grant, [], None)
    assert len(events) == 48
    dates = [event.vest_date for event in events]
    assert dates[0] == date(2021, 2, 28)
    assert dates[1] == date(2021, 3, 31)
    assert dates[2] == date(2021, 4, 30)
    assert dates[3] == date(2021, 5, 31)
    # February of the leap year inside the schedule clamps to the 29th.
    assert dates[35] == date(2024, 1, 31)
    assert dates[36] == date(2024, 2, 29)
    assert dates[37] == date(2024, 3, 31)
    assert dates[-1] == date(2025, 1, 31)


def test_feb29_leap_day_grant_monthly_dates():
    grant = make_grant(date(2020, 2, 29), 4800, 4, Frequency.MONTHLY, cliff=False)
    events = vesting_events(grant, [], None)
    dates = [event.vest_date for event in events]
    assert dates[0] == date(2020, 3, 29)
    assert dates[1] == date(2020, 4, 29)
    assert dates[10] == date(2021, 1, 29)
    assert dates[11] == date(2021, 2, 28)
    assert dates[22] == date(2022, 1, 29)
    assert dates[23] == date(2022, 2, 28)
    assert dates[34] == date(2023, 1, 29)
    assert dates[35] == date(2023, 2, 28)
    assert dates[47] == date(2024, 2, 29)


def test_cliff_merges_first_year_periods():
    grant = make_grant(date(2021, 1, 31), 4800, 4, Frequency.MONTHLY, cliff=True)
    events = vesting_events(grant, [], None)
    assert len(events) == 48
    for event in events[:11]:
        assert event.shares == 0
        assert event.cumulative_shares == 0
    assert events[11].vest_date == date(2022, 1, 31)
    assert events[11].shares == 1200
    assert events[11].cumulative_shares == 1200
    for event in events[12:]:
        assert event.shares == 100
    assert events[-1].cumulative_shares == 4800


def test_cliff_quarterly_merges_into_month_12():
    grant = make_grant(date(2021, 1, 31), 4000, 4, Frequency.QUARTERLY, cliff=True)
    events = vesting_events(grant, [], None)
    assert len(events) == 16
    assert [event.shares for event in events[:4]] == [0, 0, 0, 1000]
    assert events[3].vest_date == date(2022, 1, 31)
    assert all(event.shares == 250 for event in events[4:])
    assert events[-1].cumulative_shares == 4000


def test_rounding_floor_and_exact_total():
    grant = make_grant(date(2023, 6, 10), 100, 4, Frequency.MONTHLY, cliff=False)
    events = vesting_events(grant, [], None)
    cumulative = 0
    for k, event in enumerate(events, start=1):
        expected_cumulative = 100 * k // 48
        assert event.cumulative_shares == expected_cumulative
        assert event.shares == expected_cumulative - cumulative
        cumulative = expected_cumulative
    assert events[-1].cumulative_shares == 100


def test_rounding_floor_with_cliff():
    grant = make_grant(date(2023, 6, 10), 100, 4, Frequency.MONTHLY, cliff=True)
    events = vesting_events(grant, [], None)
    assert events[11].shares == 100 * 12 // 48
    assert events[-1].cumulative_shares == 100
    assert sum(event.shares for event in events) == 100


def test_period_shares_sum_matches_total_for_all_shapes():
    for frequency in (Frequency.MONTHLY, Frequency.QUARTERLY):
        for years in range(1, 5):
            for cliff in (False, True):
                for total in (1, 7, 100, 999, 4800):
                    grant = make_grant(date(2022, 3, 15), total, years, frequency, cliff)
                    shares = period_shares(grant)
                    assert sum(shares) == total
                    assert all(s >= 0 for s in shares)
