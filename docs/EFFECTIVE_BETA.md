# Effective Beta: observed NAV/TSLA CAD sensitivity

**Research snapshot:** 2022-12-21 to 2026-11-20 (963 common closes,
962 consecutive *common-close intervals*). Offline, from pinned Purpose
NAV, Yahoo TSLA adjusted-close, BoC USD/CAD and cash-event series.

## Method

The existing independently validated full NAV DRIP index is calculated
on Purpose NAV dates **before** selecting common TSLA dates. TSLA/CAD is
calculated from actual TSLA USD close and an as-of backward BoC FX rate.
An interval begins at one common NAV/TSLA close and ends at the next
common close: a skipped Canada/US holiday is **aggregated**, not silently
treated as a zero-return day. Days with missing or suspect Purpose
*Market Price* never enter this NAV study.

For each group, estimate a linear regression **with an intercept**:

\[
r_{\mathrm{YTSL,NAV}} = \alpha + \beta r_{\mathrm{TSLA,CAD}} + \varepsilon
\]

- Full sample; TSLA CAD positive and negative intervals separately.
- Condition on |TSLA return| > 1% as a simple predeclared robustness cut.
- Trailing 63- and 126-common-interval rolling beta; yearly full-sample
  beta; partial 2022 marked insufficient rather than extrapolated.
- Contextual *monthly* betas using the independently validated 46-month
  sample (and months where TSLA/CAD > +5% or < -5%).
- Seeded 10-joint-interval **moving-block bootstrap**, 800 replicates,
  for a descriptive 95% interval on both conditional betas and their
  **Down minus Up** difference.

### Run

~~~bash
uv run --locked python -m yield_share_anatomy.exposure
~~~

Outputs under ignored \`outputs/effective_beta/\`:

- \`paired_daily_returns.csv\`: interval end, previous close, both returns,
  calendar gap length and relative return;
- \`rolling_beta.csv\`: trailing 63/126 betas and R²;
- \`annual_beta.csv\`: historical annual beta with explicit small-sample flag;
- \`effective_beta_summary.json\`: all beta estimates, directional mean
  returns, bootstrap uncertainty, monthly cross-check, and input SHA-256.

### Interpretation boundaries

This Beta is **not** the ETF's published or daily rebalanced leverage.
It is a historical, conditional, currency-specific NAV/underlying *return
sensitivity* estimated by a simple linear model. A steeper downside
regression can reflect leverage, call-option convexity, financing,
hedging, fund management, or sample composition; it does **not**
identify any one causal driver.

Bootstrapping reduces the naive assumption of independent daily returns
but is still a heuristic: sensitivity to block length, volatility
clustering, serial dependence and unstable regime membership may alter
confidence intervals. The source distribution events remain
\`crosscheck_needed\`; no investor tax treatment is modeled. Avoid
interpreting interval mean gaps as the already validated cumulative
return gap or using this as a trading signal.
