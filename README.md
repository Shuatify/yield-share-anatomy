# Yield Share Anatomy

个人投资数据研究项目：基于 **YTSL（Purpose Tesla Yield Shares）**、TSLA 和 USD/CAD，复现历史总回报，审核数据质量，再研究市场环境表现。**研究与复现优先，不是交易信号，也暂不做网站。**

当前固定快照：**2022-12-19 至 2026-11-20**（共 985 条 Purpose NAV 记录）。历史快照已提交到 Git，日常分析**无需联网下载**。

## 快速开始

要求 Python 3.13、[uv](https://docs.astral.sh/uv/)；从项目根目录执行：

```bash
uv sync --locked
uv run --locked pytest -q
```

测试包含合成数据单元测试，以及**基于仓库内真实历史 CSV 的离线回归测试**。输入 SHA-256、官方收益对账、原始回报与市场价补充结果均会校验。

运行研究（顺序为：先主回报，再月度稳健性分析；其余对账可独立运行）：

```bash
uv run --locked python -m yield_share_anatomy.returns
uv run --locked python -m yield_share_anatomy.regimes
uv run --locked python -m yield_share_anatomy.nav
uv run --locked python -m yield_share_anatomy.benchmark
uv run --locked python -m yield_share_anatomy.market
```

所有新计算结果写入**被 Git 忽略的** `outputs/`；不会改写 `data/` 快照或已有研究证据。

## 文件结构

```text
yield_share_anatomy/                   # 可复用 Python 模块
  paths.py                             # 统一输入/输出路径
  fetch.py                             # 按需获取新数据，不参与离线日常研究
  returns.py                           # Phase 1 探索性总回报与 monthly regimes
  nav.py                               # Purpose 官方 NAV Total Return 对账
  benchmark.py                         # TSLA USD/CAD 与交易日日历检查
  market.py                            # Purpose / Yahoo Market Price 数据质量
  regimes.py                           # Market Regime 阈值敏感性
data/
  raw/purpose/                         # 浏览器下载的原始 Purpose CSV（不修改）
  snapshots/2026-11-20/                # 固定的 YTSL / TSLA / FX 标准化输入
  events/                              # 现金分配与 notional 事件
  reference/                           # Yahoo 对异常市场价的核查快照
tests/                                 # 合成数据 + 离线真实快照回归测试
research/
  baselines/2026-11-20/                # 此前已提交的研究产出原样归档
  validation/                          # 数据核验、历史结论与来源记录
docs/
  DATA.md                              # 输入、来源、复现与更新约定
  history/                             # 早期 Phase 0/1 文档，只供追溯
outputs/                               # 新计算结果（不入库）
```

## 已核实的范围与未解问题

- **NAV Total Return**：与 Purpose 截至 2026-10-30 的七组公开回报对账，7/7 符合预设诊断容差；2022-12-21 至 2026-11-20 NAV DRIP 约 **+120.4114%**。
- **TSLA CAD 基准**：同一比较区间约 **+164.5447%**；累计差距 **−44.1333 个百分点**。独立日历检查确认这一端点差值没有被旧共同日历过滤改变。
- **Market Price**：Purpose 原始文件有若干异常/缺失。Yahoo 证据支持五条衍生价格补充，两条暂不使用；原始 CSV 保持不变。旧 Market DRIP 仍为探索性结果，**不能与已对账的 NAV 路径等同**。
- **分配数据**：47 条现金分配记录仍需逐项与发行方公告核对，尤其 2023 年 notional 与 tax-factor 分类。市场环境（月度 regime）结果尚未单独完成研究级别的验证。

详情参见 [数据与复现说明](docs/DATA.md) 和 [2026-11-20 日历对账](research/validation/2026-11-20-calendar-audit.md)。

## 如何更新数据

**不要**直接覆盖 `data/snapshots/2026-11-20/`。如需下载最新行情，运行：

```bash
uv run --locked python -m yield_share_anatomy.fetch \
  --purpose-file data/raw/purpose/ytsl_2026-11-20.csv \
  --out outputs/fetch
```

这只更新临时工作区；想形成新的可审计快照，请按 [docs/DATA.md](docs/DATA.md) 的步骤另建日期目录并核验。Purpose 的 HTTP 429 可继续通过浏览器手动下载解决，避免自动密集重试。

### 验证 Market Regime 的每月收益

```bash
uv run --locked python -m yield_share_anatomy.monthly_validation
```

以独立 NAV / TSLA CAD 日历，逐月核对原有 46 个月的回报、月末日期和市场环境分类。结果保存于 `outputs/regime_validation/`；详情参见 [Market Regime Validation](docs/MARKET_REGIME_VALIDATION.md)。

### 历史收益敏感度 / Effective Beta

```bash
uv run --locked python -m yield_share_anatomy.exposure
```

计算 YTSL NAV DRIP 对 TSLA CAD 的带截距回归 Beta、上涨/下跌条件 Beta、63/126 区间滚动 Beta 和区块 Bootstrap 不确定性。结果保存在 `outputs/effective_beta/`，详情见 [研究方法](docs/EFFECTIVE_BETA.md)。

数值结果与不确定性分析参见 [2026-11-20 Effective Beta 研究记录](research/validation/2026-11-20-effective-beta.md)。

### Compounding & Log Wealth Anatomy

```bash
uv run --locked python -m yield_share_anatomy.compounding
```

用严格的对数恒等式拆解 YTSL NAV DRIP 与 TSLA CAD 的历史复利财富差距，输出逐区间与逐年贡献、二阶近似和独立终点核对。原始数据不变，新结果写入 `outputs/compounding/`。参见 [方法说明](docs/COMPOUNDING_ANATOMY.md) 和 [2026-11-20 研究记录](research/validation/2026-11-20-compounding.md)。

### Zero-cost Daily Leverage Counterfactual

```bash
uv run --locked python -m yield_share_anatomy.leverage
```

以 TSLA CAD 真实日线为基础，模拟每日再平衡 1.0×、1.1×、1.2× 的**零融资成本**反事实杠杆组合，再与独立 NAV DRIP 在相同日期比较。结果在 `outputs/leverage_counterfactual/`；参见 [研究方法](docs/LEVERAGE_COUNTERFACTUAL.md) 与 [2026-11-20 验证记录](research/validation/2026-11-20-leverage-counterfactual.md)。这些模型**不代表 YTSL 的真实期权或融资策略**。
