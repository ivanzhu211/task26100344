# vesting — 股票授予归属与费用计算库

供上层薪酬测算与报表模块直接调用的 Python 库，无接口层。
授予、无薪假、离职事件持久化在 SQLite。

## 快速开始

```python
from datetime import date
from decimal import Decimal
from vesting import (
    Frequency, Grant, Leave, Store, Termination, VestingService,
)

svc = VestingService(Store("vesting.db"))  # 或 Store() 内存库

svc.record_grant(Grant(
    grant_id="g1", employee_id="e1",
    grant_date=date(2024, 1, 31), total_shares=48,
    vesting_years=4, frequency=Frequency.MONTHLY,
    cliff=False, fair_value=Decimal("10.00"),
))
svc.record_leave(Leave("l1", "e1", date(2024, 3, 1), date(2024, 4, 15)))
svc.record_termination(Termination("e1", date(2025, 6, 30)))

svc.vesting_schedule("g1")                       # 完整归属日历
svc.vested_shares("g1", date(2024, 6, 1))        # 截至某日已归属股数
svc.grant_expense("g1", date(2024, 1, 1), date(2024, 12, 31))  # 单笔区间费用
svc.company_expense(date(2025, 1, 1), date(2025, 12, 31))      # 全公司区间费用
```

## 业务规则实现要点

- **归属日**：第 k 期为授予日往后第 k 个月（按季为第 3k 个月）同一日，
  不存在则取当月最后一天，各期独立从授予日起算（1月31日 → 2月28/29日 → 3月31日）。
- **股数**：截至第 k 期累计 `floor(总股数 × k / 总期数)`，末期恰好等于总股数；
  悬崖期把前 12 个月并入第 12 个月那一期。
- **假期**：超过 30 天的无薪假把开始日当天及以后的归属日顺延假期天数；
  多段假期按开始日先后依次顺延，判断用已顺延过的日期；30 天及以内无影响。
- **离职**：离职日后到达的归属期全部作废；当天及以前的照常归属。
- **费用**：每期价值 = 该期股数 × 每股公允价值，授予日到归属日按天线性；
  顺延时冻结假期前一天（按分取整后）的累计额，剩余部分到新的归属日重新线性；
  作废期从离职日起累计归零（离职日冲回）；每日累计按分四舍五入（半分进位）。
- **区间费用**：各期在末日的累计减去开始日前一天的累计再求和，
  因此任意切分区间后各段之和与整段逐分相等。
- **顺序无关**：查询结果只取决于事件本身，与录入顺序、录入时间无关。

## 模块结构

- `vesting/models.py` — 事件与结果的数据类型
- `vesting/db.py` — SQLite 存取（读取统一排序，保证顺序无关）
- `vesting/schedule.py` — 归属日历（归属日、股数、顺延、作废）
- `vesting/expense.py` — 逐期确认曲线与区间费用
- `vesting/service.py` — 上层门面 `VestingService`

## 测试

```bash
python3 -m unittest discover -s tests
```

覆盖：月末/闰年归属日、悬崖期、股数取整与总额一致、假期顺延冻结、
离职冲回额、录入顺序不变性、区间任意拆分逐分相等，
以及 5000 员工 / 1 万笔授予全年汇总 10 秒内返回的性能要求。
