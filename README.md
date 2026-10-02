# task26100344

股票授予归属与股权激励费用计算库（纯 Python + SQLite，无接口层），
供上层薪酬测算与报表模块直接调用。

## 组成

- `equity_comp/models.py` — 授予（Grant）、无薪假（Leave）、离职（Termination）、归属事件（VestingEvent）类型。
- `equity_comp/dates.py` — 按月平移日期，日不存在时钳到月末，后续月份回到原日。
- `equity_comp/schedule.py` — 归属日历：期数、零头股向下取整、12 个月悬崖期合并、超 30 天假期顺延、离职作废。
- `equity_comp/expense.py` — 逐期累计确认曲线：授予日 0、归属日满额、按天线性；顺延冻结假期前一天的已确认额；作废期离职日冲回；按分半分进位。
- `equity_comp/store.py` — SQLite 持久化（grants / leaves / terminations 三张表）。
- `equity_comp/service.py` — 查询门面 `EquityCompService`：归属日历、截至某日已归属股数、任意区间费用（分）。

## 用法

```python
from datetime import date
from equity_comp import EquityCompService, Frequency, Grant, Leave, Store, Termination

store = Store("grants.db")          # 或 ":memory:"
service = EquityCompService(store)

grant_id = store.add_grant(Grant(
    id=None, employee_id="E1001", grant_date=date(2024, 1, 31),
    total_shares=4800, vesting_years=4, frequency=Frequency.MONTHLY,
    cliff=True, fair_value_cents=1234,   # 每股 $12.34
))
store.add_leave(Leave(id=None, employee_id="E1001",
                      start_date=date(2024, 6, 1), end_date=date(2024, 8, 15)))
store.set_termination(Termination(employee_id="E1001",
                                  termination_date=date(2026, 3, 1)))

calendar = service.vesting_calendar(grant_id)          # 每笔授予的归属日历
vested = service.vested_shares("E1001", date(2026, 4, 1))
q1 = service.expense_cents(date(2026, 1, 1), date(2026, 3, 31))            # 全公司
q1e = service.expense_cents(date(2026, 1, 1), date(2026, 3, 31), "E1001")  # 单人
```

结果只取决于事件本身，与录入顺序无关；区间费用可任意拆分求和，逐分相等。

## 测试

```bash
python3 -m pytest tests/ -q
```
