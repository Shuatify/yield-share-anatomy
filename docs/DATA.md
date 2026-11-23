# 数据目录与可复现流程

## 数据分层

| 路径 | 内容 | 更新策略 |
|---|---|---|
| `data/raw/purpose/ytsl_2026-11-20.csv` | 浏览器下载的发行方原始文件；行顺序及 `volume` 字段都保留 | **只读**，原文件与 Git SHA 可追溯 |
| `data/snapshots/2026-11-20/` | 已排序/标准化的 `ytsl_purpose_daily.csv`、`tsla_yahoo_daily.csv`、`usdcad_boc_daily.csv`；另含预览和采集状态 | **冻结快照**，不覆盖 |
| `data/events/` | YTSL 现金分配、非现金 notional；分配来源仍有待逐项验证 | 变更须附发行方证据 |
| `data/reference/` | 对异常市价使用的 Yahoo OHLCV 截面，含检索日期与源 | 新增快照，不静默覆盖 |
| `research/baselines/2026-11-20/` | 在目录整理前已生成的 Phase 1、NAV、benchmark、Market QC、regime 输出 | 研究历史基线，**字节原样移动** |
| `research/validation/` | 输入 SHA、方法审计与验证结论 | Git 追踪 |
| `outputs/` | 新执行产生的报告与临时下载 | Git 忽略、可再生 |

`fetch_status.json` 的 `sources.ytsl` 保留了当时的历史文件名 `ytsl.csv`，现已移到 `data/raw/purpose/ytsl_2026-11-20.csv`；源文件字节与标准化 CSV 均未更改。

**重要：** 经过 Phase 0 标准化的 Yahoo TSLA 和 BoC 汇率并非它们的原始 HTTP 响应；不应误标为“逐字节 HTTP 原始包”。它们是带数据源与采集质量元信息的**固定源快照**。

## 数据 QC 规则

- NAV 优先独立在 Purpose 交易日日历上计算，不能受 Yahoo/FX/Market Price 日期过滤影响。
- Market Price 以 Purpose 为首选，异常/缺失时才使用 Yahoo **Close（不是 Adj Close）** 和 OHLCV、NAV 做交叉验证。
- 未确认的非分配除息日可以在派生 market series 里排除，但不能自动断言月度、滚动、波动率、最大回撤或端点完全不受影响。
- 未确认的现金或非现金分配除息日应阻止派生总回报计算，不应静默后移或跳过。
- 每次研究都保留明确的输入版本、完整输出路径、比较期间和局限；不更改原始观察值。
- 历史现金分配列表来自二级来源种子，官方逐条核验尚未完成。

## 离线复现

```bash
uv sync --locked
uv run --locked pytest -q
uv run --locked python -m yield_share_anatomy.returns
uv run --locked python -m yield_share_anatomy.regimes
uv run --locked python -m yield_share_anatomy.nav
uv run --locked python -m yield_share_anatomy.benchmark
uv run --locked python -m yield_share_anatomy.market
```

回归测试会验证历史输入 SHA-256、发行方 NAV 收益、累计 NAV/TSLA CAD 对比、异常价格处理。默认目录集中在 `yield_share_anatomy/paths.py`，实际研究函数仍接受显式的输入输出路径（例如 `--data-dir`, `--out`）。

## 未来新快照

1. 单次下载或浏览器手动获取新的 Purpose 原始 CSV，保存到 `data/raw/purpose/`，文件名含新截止日。
2. 用 `python -m yield_share_anatomy.fetch --purpose-file ... --out outputs/fetch` 获取标准化 TSLA、BoC、Purpose 输入，检查 `fetch_status.json` 为 `ok`、日期、行数和缺失量。
3. 把经过核验的数据与状态**复制**到新建的 `data/snapshots/YYYY-MM-DD/`；严禁覆盖历史 2026-11-20 快照。
4. 对新的 snapshot 跑同样的对账与异常检查，记录新的输入 hashes，调整默认版本须作为单独 PR。
5. 只在明确确认时修改或扩展现金分配、notional 事件；未核验数据保留 provisional 标签。

## 旧文档

`docs/history/` 存放早期 Phase 0/1 的各类 README，其中安装 ZIP、顶层脚本运行命令和忽略原始数据的描述均可能过时。**以根目录 README 和本文件为现行说明。**
