# 2026-11-20 YTSL NAV vs TSLA CAD compounding identity

**Study:** 963 common-date closes, 962 paired return intervals, same
native-calculated wealth endpoints as prior issuer NAV reconciliation
and TSLA/CAD benchmark; date range 2022-12-21 — 2026-11-20.
Cash distribution seed retains its \`crosscheck_needed\` status.

**Primary formula:** \`log relative wealth = Σ(simple return spread)
+ Σ(exact nonlinear correction)\`; scaled by 100 for display.

## Exact observed end wealth

| Measure | Observed |
|---|---:|
| YTSL NAV DRIP, from unit starting capital | 2.2041139492 |
| TSLA CAD unhedged reference, from unit starting capital | 2.6454468803 |
| YTSL total return | +120.4113949% |
| TSLA CAD total return | +164.5446880% |
| **Terminal total-return gap** (initial-capital pp) | **−44.1332931 pp** |
| Relative YTSL/TSLA final wealth ratio | 0.8331726354 |
| Relative shortfall vs TSLA *ending* wealth | −16.6827365% |
| **Log relative final wealth ×100** | **−18.2514413** |

The 44.13 pp difference, −16.68% terminal relative-wealth shortfall
and −18.25 ×100 log ratio are **not interchangeable units**.

## Exact accounting components

| 100× summed decimal-return component | Amount |
|---|---:|
| Simple return spread, Σ(y − x) | **−4.8434846** |
| Exact log correction, Σ[log1p(y)−y − (log1p(x)−x)] | **−13.4079567** |
| Sum = relative log wealth ×100 | **−18.2514413** |
| Of the nonlinear term, quadratic −1/2 Σ(y²−x²) | −12.9248560 |
| Higher-order remainder (exact) | −0.4831006 |

As shares of **this particular negative log identity**, the first
term is ~26.54% and nonlinear correction ~73.46%. **This is not a
causal 26.5% / 73.5% decomposition of an investable strategy,
leveraging costs, premiums or "volatility drag."**

## Distribution of relative log results by ending year

| Year | Paired intervals | Relative log wealth ×100 |
|---|---:|---:|
| Partial 2022 | 5 | −1.45269 |
| 2023 | 245 | −3.72344 |
| 2024 | 247 | **−19.37544** |
| 2025 | 245 | **+9.66016** |
| Through 2026-11-20 | 220 | −3.36002 |
| **Total** | **962** | **−18.25144** |

This reveals that the substantial 2024 deterioration was partly
offset by a 2025 recovery. Annual log contributions add exactly but
must not be called year-to-date or annual percentage point returns.

The worst interval for YTSL relative log performance ended
**2025-03-10** (TSLA CAD about −15.07%, YTSL NAV DRIP about −19.50%).
The best ended **2025-04-09** (TSLA CAD about +22.29%, YTSL about
+26.71%). Their very large moves show why inspecting tail
contributions matters.

## Guardrails

1. The exact log identity does **not** isolate covered-call value,
   stock holding leverage, interest, the ETF FX hedge, issuer fees, or
   capital gains tax. Data from specific option holdings and financing
   would be required to build causal/mechanistic benchmarks.
2. The second-order term is a useful approximation to the correction
   but *not* direct evidence that variance alone generated the return gap.
3. Keep all 47 cash entitlements in the issuer-benchmarked NAV series,
   and never apply suspect Purpose Market Price exclusions to NAV.
4. This is a fixed historical sample with input SHA fingerprints stored
   in \`outputs/compounding/compounding_summary.json\`. All baseline
   snapshots and original return research are unchanged.

**Execution:** \`uv run --locked python -m yield_share_anatomy.compounding\`,
CI validates the exact identity against native terminal levels and
the known historic -44.1333 pp result. See PR #9 for validation logs.
