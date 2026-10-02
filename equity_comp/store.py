from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from .models import Frequency, Grant, Leave, Termination

_SCHEMA = """
CREATE TABLE IF NOT EXISTS grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT NOT NULL,
    grant_date TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    vesting_years INTEGER NOT NULL CHECK (vesting_years BETWEEN 1 AND 4),
    frequency TEXT NOT NULL CHECK (frequency IN ('monthly', 'quarterly')),
    cliff INTEGER NOT NULL CHECK (cliff IN (0, 1)),
    fair_value_cents INTEGER NOT NULL CHECK (fair_value_cents >= 0)
);
CREATE INDEX IF NOT EXISTS idx_grants_employee ON grants(employee_id);

CREATE TABLE IF NOT EXISTS leaves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leaves_employee ON leaves(employee_id);

CREATE TABLE IF NOT EXISTS terminations (
    employee_id TEXT PRIMARY KEY,
    termination_date TEXT NOT NULL
);
"""


def _to_date(value: str) -> date:
    return date.fromisoformat(value)


class Store:
    """SQLite-backed persistence for grants, leaves and terminations."""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def add_grant(self, grant: Grant) -> int:
        if not 1 <= grant.vesting_years <= 4:
            raise ValueError("vesting_years must be between 1 and 4")
        if grant.total_shares < 0 or grant.fair_value_cents < 0:
            raise ValueError("shares and fair value must be non-negative")
        cur = self._conn.execute(
            "INSERT INTO grants (employee_id, grant_date, total_shares,"
            " vesting_years, frequency, cliff, fair_value_cents)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                grant.employee_id,
                grant.grant_date.isoformat(),
                grant.total_shares,
                grant.vesting_years,
                grant.frequency.value,
                int(grant.cliff),
                grant.fair_value_cents,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def add_leave(self, leave: Leave) -> int:
        if leave.end_date < leave.start_date:
            raise ValueError("leave end_date must not precede start_date")
        overlap = self._conn.execute(
            "SELECT 1 FROM leaves WHERE employee_id = ?"
            " AND start_date <= ? AND end_date >= ?",
            (
                leave.employee_id,
                leave.end_date.isoformat(),
                leave.start_date.isoformat(),
            ),
        ).fetchone()
        if overlap:
            raise ValueError("leave overlaps an existing leave for this employee")
        cur = self._conn.execute(
            "INSERT INTO leaves (employee_id, start_date, end_date) VALUES (?, ?, ?)",
            (leave.employee_id, leave.start_date.isoformat(), leave.end_date.isoformat()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def set_termination(self, termination: Termination) -> None:
        self._conn.execute(
            "INSERT INTO terminations (employee_id, termination_date) VALUES (?, ?)"
            " ON CONFLICT(employee_id) DO UPDATE SET"
            " termination_date = excluded.termination_date",
            (termination.employee_id, termination.termination_date.isoformat()),
        )
        self._conn.commit()

    def get_grant(self, grant_id: int) -> Grant:
        row = self._conn.execute(
            "SELECT * FROM grants WHERE id = ?", (grant_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"grant {grant_id} not found")
        return self._row_to_grant(row)

    def list_grants(self, employee_id: str | None = None) -> list[Grant]:
        if employee_id is None:
            rows = self._conn.execute("SELECT * FROM grants ORDER BY id").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM grants WHERE employee_id = ? ORDER BY id",
                (employee_id,),
            ).fetchall()
        return [self._row_to_grant(row) for row in rows]

    def list_leaves(self, employee_id: str) -> list[Leave]:
        rows = self._conn.execute(
            "SELECT * FROM leaves WHERE employee_id = ? ORDER BY start_date, id",
            (employee_id,),
        ).fetchall()
        return [
            Leave(
                id=row["id"],
                employee_id=row["employee_id"],
                start_date=_to_date(row["start_date"]),
                end_date=_to_date(row["end_date"]),
            )
            for row in rows
        ]

    def get_termination(self, employee_id: str) -> Termination | None:
        row = self._conn.execute(
            "SELECT * FROM terminations WHERE employee_id = ?", (employee_id,)
        ).fetchone()
        if row is None:
            return None
        return Termination(
            employee_id=row["employee_id"],
            termination_date=_to_date(row["termination_date"]),
        )

    @staticmethod
    def _row_to_grant(row: sqlite3.Row) -> Grant:
        return Grant(
            id=row["id"],
            employee_id=row["employee_id"],
            grant_date=_to_date(row["grant_date"]),
            total_shares=row["total_shares"],
            vesting_years=row["vesting_years"],
            frequency=Frequency(row["frequency"]),
            cliff=bool(row["cliff"]),
            fair_value_cents=row["fair_value_cents"],
        )
