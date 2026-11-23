# Yield Share Anatomy — Phase 0 (uv 版本)

这个项目获取并检查 YTSL 官方 NAV/市场价格、TSLA 历史价格和 USD/CAD。
**尚未计算总回报**；`tests_yield/fixtures` 是**合成测试数据**。

## 只需要在 Mac 安装一次

```bash
brew install uv
uv --version
```

## 项目首次初始化

在解压的项目目录里运行：

```bash
./setup.sh
```

脚本依次执行：
1. `uv python install 3.13`：准备项目使用的 Python 3.13
2. `uv sync`：根据 `pyproject.toml` 生成 `uv.lock`，建立 `.venv` 并安装依赖
3. `uv run pytest -q`：运行测试
4. 使用合成 fixture 数据跑一次离线端到端流程

**注意：本压缩包没有预生成 `uv.lock`。** 当前制作环境的 uv 包索引缓存不完整、网络不可用，无法可靠生成锁文件，因此首次运行 `uv sync` 时会在你的 Mac 上联网生成它。生成后应提交到 Git，这样以后可使用 `uv sync --locked` 获得可重复的依赖环境。

如果之前在同一项目目录用传统 venv 建过 `.venv`，建议先退出已激活的环境 (`deactivate`)，然后由 `uv sync` 管理。如果发现 Python 版本与本项目固定的 3.13 不符，可删除**项目目录内**的 `.venv` 并重新运行 `uv sync`。

## 真实数据下载

```bash
uv run --locked python yield_share_phase0_fetch.py --out yield_share_phase0_data
```

需要网络。输出包括三个原始序列的 CSV、`aligned_daily_preview.csv` 和 `fetch_status.json`。注意后者尚不包含现金及非现金分红的完整处理，**不能将预览 CSV 当作已校验的总回报数据**。

## 日常命令

```bash
uv run --locked pytest -q             # 运行测试
uv run --locked python --version      # 查看项目 Python
uv add matplotlib                     # 加运行时依赖并更新锁文件
uv add --dev ruff                      # 加开发依赖
uv sync --locked                       # 按已提交锁文件同步
uv lock --check                        # 检查锁文件是否与项目声明一致
```

`uv run` 自动使用项目 `.venv`，无需手动 `source .venv/bin/activate`；日常也不必使用 `pip install`。

需要提交到 Git：`pyproject.toml`, `.python-version`, `uv.lock`, 代码与测试。
不要提交：`.venv/`、`.pytest_cache/`、下载的投资数据（默认为 `.gitignore` 排除）。

文档：
- https://docs.astral.sh/uv/getting-started/installation/
- https://docs.astral.sh/uv/guides/projects/
- https://docs.astral.sh/uv/concepts/projects/sync/

## Purpose 返回 HTTP 429 时（当前推荐流程）

这是 Purpose 对自动 HTTP 请求返回的限流/防护响应，不是 `uv` 的问题。**不要循环快速重试或尝试伪造身份绕过限制。**

1. 用浏览器打开 [Purpose 的 YTSL Performance 页面](https://www.purposeinvest.com/funds/tesla-yield-shares-purpose-etf/performance)，点击 **Download NAVs**；也可以直接打开官方 [CSV 下载地址](https://www.purposeinvest.com/api/nav?fundId=YTSL&seriesId=ETF)。
2. 保存 CSV 到项目目录，命名为 `ytsl.csv`。
3. 用本地文件运行；脚本不会再向 Purpose 发请求，但仍会尝试下载 TSLA 和 USD/CAD：

```bash
uv run --locked python yield_share_phase0_fetch.py \
  --purpose-file ./ytsl.csv \
  --out yield_share_phase0_data
```

今后只要 `yield_share_phase0_data/ytsl_purpose_daily.csv` 已存在，默认会读取本地缓存，避免重复访问 Purpose。想明确刷新时用 `--refresh-purpose`（只发一次正常请求；仍可能收到 429）。手动文件的优先级最高。

```bash
# 有缓存时，直接运行，不访问 Purpose
uv run --locked python yield_share_phase0_fetch.py --out yield_share_phase0_data
```

**部分成功可以保存**：某个来源失败时，其他来源仍继续获取；成功的 CSV 会保存到输出目录，`fetch_status.json` 会记录 `status: partial` 及失败原因。`partial` 会返回退出码 2，以便脚本/CI 能识别不完整数据。只有三项数据都成功，才写入 `aligned_daily_preview.csv`；若重跑不完整，会清除旧的对齐文件，防止误用过期结果。

可以执行下列命令验证本次更新：

```bash
uv run --locked pytest -q   # 目前 12 个自动化测试，包括 HTTP 429 的模拟
```

本次代码修改没有改变项目依赖，已有 `uv.lock` 不需要重建。
