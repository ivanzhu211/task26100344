"""SQLite 持久化层：授予与人事事件的存取。"""
from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from .models import Frequency, Grant, Leave, Termination

_SCHEMA = """
CREATE TABLE IF NOT EXISTS grants (
    grant_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    grant_date TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    vesting_years INTEGER NOT NULL,
    frequency TEXT NOT NULL,
    cliff INTEGER NOT NULL,
    fair_value_cents INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grants_employee ON grants(employee_id);

CREATE TABLE IF NOT EXISTS leaves (
    leave_id TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leaves_employee ON leaves(employee_id);

CREATE TABLE IF NOT EXISTS terminations (
    employee_id TEXT PRIMARY KEY,
    term_date TEXT NOT NULL
);
"""


def _to_date(text: str) -> date:
    return date.fromisoformat(text)


class Store:
    """事件存取。查询结果与录入顺序无关（读取时统一排序）。"""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(path)
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def add_grant(self, grant: Grant) -> None:
        fair_value_cents = int((grant.fair_value * 100).to_integral_value())
        if Decimal(fair_value_cents) != grant.fair_value * 100:
            raise ValueError("fair_value 必须精确到分")
        self._conn.execute(
            "INSERT OR REPLACE INTO grants VALUES (?,?,?,?,?,?,?,?)",
            (
                grant.grant_id,
                grant.employee_id,
                grant.grant_date.isoformat(),
                grant.total_shares,
                grant.vesting_years,
                grant.frequency.value,
                1 if grant.cliff else 0,
                fair_value_cents,
            ),
        )
        self._conn.commit()

    def add_leave(self, leave: Leave) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO leaves VALUES (?,?,?,?)",
            (
                leave.leave_id,
                leave.employee_id,
                leave.start_date.isoformat(),
                leave.end_date.isoformat(),
            ),
        )
        self._conn.commit()

    def add_termination(self, term: Termination) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO terminations VALUES (?,?)",
            (term.employee_id, term.term_date.isoformat()),
        )
        self._conn.commit()

    def _row_to_grant(self, row: tuple) -> Grant:
        return Grant(
            grant_id=row[0],
            employee_id=row[1],
            grant_date=_to_date(row[2]),
            total_shares=row[3],
            vesting_years=row[4],
            frequency=Frequency(row[5]),
            cliff=bool(row[6]),
            fair_value=Decimal(row[7]) / 100,
        )

    def grants(self, employee_id: str | None = None) -> list[Grant]:
        if employee_id is None:
            rows = self._conn.execute(
                "SELECT * FROM grants ORDER BY grant_id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM grants WHERE employee_id=? ORDER BY grant_id",
                (employee_id,),
            ).fetchall()
        return [self._row_to_grant(r) for r in rows]

    def grant(self, grant_id: str) -> Grant:
        row = self._conn.execute(
            "SELECT * FROM grants WHERE grant_id=?", (grant_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"grant not found: {grant_id}")
        return self._row_to_grant(row)

    def leaves(self, employee_id: str) -> list[Leave]:
        rows = self._conn.execute(
            "SELECT * FROM leaves WHERE employee_id=? ORDER BY start_date, leave_id",
            (employee_id,),
        ).fetchall()
        return [
            Leave(
                leave_id=r[0],
                employee_id=r[1],
                start_date=_to_date(r[2]),
                end_date=_to_date(r[3]),
            )
            for r in rows
        ]

    def termination(self, employee_id: str) -> Termination | None:
        row = self._conn.execute(
            "SELECT * FROM terminations WHERE employee_id=?", (employee_id,)
        ).fetchone()
        if row is None:
            return None
        return Termination(employee_id=row[0], term_date=_to_date(row[1]))

    def employee_ids(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT employee_id FROM grants ORDER BY employee_id"
        ).fetchall()
        return [r[0] for r in rows]
