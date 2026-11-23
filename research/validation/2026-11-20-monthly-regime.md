# 2026-11-20 monthly-regime independent reconciliation

**Status:** Independent monthly calculation validated on the pinned historical
dataset; the issuer cash-event seed still awaits line-by-line source verification.

## Provenance

Inputs are committed under `data/snapshots/2026-11-20/` and
`data/events/ytsl_cash_distributions.csv`. Old month-level outputs are
**immutable, archived baselines** at
`research/baselines/2026-11-20/phase1/monthly_regimes.csv`.

Computation: `uv run --locked python -m yield_share_anatomy.monthly_validation`.
The module saves `independent_monthly.csv`, `monthly_vs_legacy.csv`,
and `regime_validation_status.json` (including SHA-256 hashes of all
five files) under ignored `outputs/regime_validation/`.

The independent method calculates YTSL NAV DRIP on the full Purpose NAV
calendar with cash on exact ex-date; TSLA/CAD is Yahoo adjusted TSLA close
times the Bank of Canada USD/CAD reference on US trading days. Independent
native last trading observations are used for each calendar month, then
compared with preceding month-end values. This deliberately avoids using
YTSL **Market Price** or the original Phase 1 common-calendar filter.

## Findings (2023-01 to 2026-10, 46 complete comparison months)

- All **46/46 months** can be reproduced independently.
- All **46/46 NAV and TSLA CAD month-end dates** match, and match the
  old analysis's selected month-end dates.
- **0** regime classification changes at the original ±5% thresholds.
- Maximum difference from the original legacy monthly gap was about
  **8 × 10^-14 percentage points**, a floating-point artifact.
- January 2023 is measured from the **December 2022 closing anchor**.
  The partial initial and final months (2022-12, 2026-11) are
  excluded in line with the original project's policy.

| TSLA/CAD monthly regime | Months | NAV relative gap, mean | NAV win months |
|---|---:|---:|---:|
| Up, TSLA > +5% | 18 | +0.0289 pp | 9/18 |
| Sideways, -5% ≤ TSLA ≤ +5% | 15 | +0.8966 pp | 10/15 |
| Down, TSLA < -5% | 13 | -1.5697 pp | 4/13 |

**Interpretation:** In 9 of 13 months when TSLA/CAD fell more than 5%,
YTSL NAV DRIP fell further (or underperformed on a monthly return basis).
The mean gap was -1.57 pp. This is a historical, conditional observation,
**not a claim that Covered Calls caused the gap**: the ETF's leverage,
financing costs, FX hedging, fees, distribution reinvestment and other
exposures remain entangled.

Monthly average gaps must not be added up or equated with the separately
verified ~-44.13 pp cumulative total-return gap; monthly returns compound
and regroup across market regimes.

## Caveats and follow-up

- This validates monthly NAV calculations and month-end alignment,
  **not** Market Price DRIP, intra-month volatility, drawdown, or other
  risk metrics. The old YTSL market-price anomalies are still a separate
  data-quality issue.
- The 47 cash distributions are an unverified secondary-source research
  seed even though official Purpose NAV-period returns were matched.
- Regime membership is defined by the **same period TSLA/CAD return**
  and is descriptive, not a predictive conditioning variable.
- Small, overlapping market environments can be sensitive to leverage,
  tail events and regime threshold; no investment outperformance claim
  follows from these counts.
- The next research increment should **test exposures/mechanisms**
  (leverage, options overlay, financing, FX hedge) or run sensitivity
  analyses, without attributing the observed monthly differences to
  a single driver.
