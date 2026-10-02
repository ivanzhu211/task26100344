"""领域模型：授予、假期、离职等事件的类型定义。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class Frequency(str, Enum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass(frozen=True)
class Grant:
    grant_id: str
    employee_id: str
    grant_date: date
    total_shares: int
    vesting_years: int  # 1..4
    frequency: Frequency
    cliff: bool  # 是否带 12 个月悬崖期
    fair_value: Decimal  # 每股公允价值（美元，精确到分）


@dataclass(frozen=True)
class Leave:
    leave_id: str
    employee_id: str
    start_date: date  # 含
    end_date: date  # 含


@dataclass(frozen=True)
class Termination:
    employee_id: str
    term_date: date


@dataclass(frozen=True)
class VestingEvent:
    """一笔授予某一期的归属结果。"""

    grant_id: str
    period: int  # 第几期，从 1 开始
    vest_date: date  # 顺延后的归属日
    cumulative_shares: int  # 截至该期累计归属股数
    period_shares: int  # 该期归属股数
    forfeited: bool  # 是否因离职作废
