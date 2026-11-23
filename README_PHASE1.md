# Phase 1: 从真实 YTSL / TSLA / FX 数据计算历史回报

**数据源成功后再运行；不需要额外安装任何依赖。**

## 安装补丁

将这个 ZIP 解压到现有 `yield-share-anatomy` 项目根目录（保留 Phase 0 原文件）：

```bash
unzip -o ~/Downloads/yield_share_phase1_patch.zip -d .
uv run --locked pytest -q
```

## 运行真实数据研究

```bash
uv run --locked python yield_share_phase1_returns.py \
  --data-dir yield_share_phase0_data \
  --events data/ytsl_cash_distributions.csv \
  --notional data/ytsl_notional_events.csv \
  --out yield_share_phase1_results
```

`fetch_status.json` 必须是 `status=ok`。脚本拒绝默认使用模拟样本。

## 输出

- `daily_return_index.csv`：YTSL NAV、市价、现金不再投资、现金分配再投资、TSLA CAD 总回报、两种相对回报差、指示年化分配率。
- `monthly_regimes.csv`：完整日历月的 TSLA/YTSL 回报和市场分类。
- `regime_summary.csv`：上涨、横盘、下跌三类市场样本数量、平均回报差、胜率。
- `cash_events_applied.csv`：每个已纳入分红事件的原始除息日、实际用于同步比较的日期和日期偏移。
- `annual_distribution_audit.csv`：每年常规现金分配和已知非现金分配核对。
- `analysis_status.json`：计算范围、数据完整性、回报数字、风险提示。

## 分配 CSV 的数据状态

`data/ytsl_cash_distributions.csv` 含 **47 条现金分配**，时间为 2022 年 12 月至 2026 年 10 月。它是基于 DividendHistory.org 公共历史列表人工建立的研究种子数据，字段 `status=crosscheck_needed`，**并未完成与 Purpose 所有历史月度公告逐条交叉核实**。已发现 2024、2025 年常规现金总额与 Purpose 年度 Tax Factors 对应值吻合。

`data/ytsl_notional_events.csv` 记录 2023 年 $2.0700 和 2025 年 $2.3180 的最终非现金分配。二者不能作为现金收入，也不应在份额立即合并的情况下重复计入总回报。2023 年 Purpose 年度 Tax Factors 的 “Total Cash Distributions” 字段显示 $6.0669，而每月常规现金相加为 $3.9969，差额恰为 $2.0700 已公告 notional；**分类不一致待查**，`annual_distribution_audit.csv` 会标记该年需复核。

2026 年 11 月 26 日尚未除息，**即使公告已公布，也不能加入截至 2026-11-20 的历史回报**。后续需要更新现金事件 CSV 才能延展历史。

## 计算假设与局限

1. 比较起点选为 YTSL NAV、YTSL 市价、TSLA 调整收盘价和 FX 全部有效的首个共同日期。
2. TSLA 以 Yahoo `adj_close_usd × Bank of Canada USD/CAD` 转换成 CAD 参考回报，非对冲基准。BoC 是参考汇率，不是实际可执行收盘汇率。
3. YTSL 分别以 NAV 和交易所市场收盘价计算价格回报、领取现金不再投资的经济回报、以及将现金在除息日收盘重新投入的假设总回报。
4. 现金在除息日计入 **应收权益**，不是声称当天就到账；实际券商到账取决于 Payment Date。
5. 为了与 TSLA 同步比较，YTSL 的某些交易日可能被排除；如分红除息日在被排除日，会将事件映射到下一个共同交易日并明确标注，**是近似再投资执行方式**。
6. 每月市场环境按 TSLA CAD 单月总回报分为 >+5%、±5% 和 <-5% 三类；排除第一个和最后一个可能不完整的月份。样本有限，统计只作描述性研究。
7. 警惕异常早期价格、可能的历史拆股/合股、特殊分配和 Yahoo 修订；在任何公开展示前要先核对异常和官方 NAV Total Return。

**当前是离线研究脚本，未构建网站，也不宣称可以直接公开引用其未经核对的结果。**
