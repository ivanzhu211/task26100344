from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Frequency(Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass(frozen=True)
class Grant:
    id: int | None
    employee_id: str
    grant_date: date
    total_shares: int
    vesting_years: int
    frequency: Frequency
    cliff: bool
    fair_value_cents: int


@dataclass(frozen=True)
class Leave:
    id: int | None
    employee_id: str
    start_date: date
    end_date: date

    @property
    def days(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass(frozen=True)
class Termination:
    employee_id: str
    termination_date: date


@dataclass(frozen=True)
class VestingEvent:
    grant_id: int | None
    period: int
    vest_date: date
    shares: int
    cumulative_shares: int
    forfeited: bool

