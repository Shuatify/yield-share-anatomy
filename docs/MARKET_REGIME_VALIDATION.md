# Independent Market Regime Validation

Reproduce the original Phase 1's **46 complete calendar-month** NAV DRIP vs
TSLA/CAD returns independently, using the full YTSL NAV calendar and actual
TSLA US trading dates plus Bank of Canada FX. The existing Phase 1 and
robustness scripts remain unchanged.

Run completely offline using pinned CSVs:

~~~bash
uv run --locked python -m yield_share_anatomy.monthly_validation
~~~

The script writes to ignored \`outputs/regime_validation/\`:
- \`independent_monthly.csv\` — native month-end dates, NAV/TSLA CAD returns,
  exact ex-date cash event counts, monthly gap and classification;
- \`monthly_vs_legacy.csv\` — comparison with archived \`monthly_regimes.csv\`,
  including date, regime and per-return differences;
- \`regime_validation_status.json\` — pass/fail, group summaries, data SHA-256s.

The **first and last observed months** are excluded to match the original
conservative partial-month policy: 2022-12 and 2026-11. This is an explicit
frozen-snapshot comparison convention, not a universal complete-month test.
Independent month ends can differ across US/Canadian calendars. Those
differences are explicitly reported (and counted as unresolved for this
strict historical reconciliation), not silently joined on adjacent dates.

### Pinned sample (through 2026-10)

| TSLA CAD monthly regime | Months | Mean YTSL NAV relative gap | YTSL win months |
|---|---:|---:|---:|
| Up (>+5%) | 18 | +0.0289 pp | 9 |
| Sideways (between -5% and +5%, inclusive) | 15 | +0.8966 pp | 10 |
| Down (<-5%) | 13 | -1.5697 pp | 4 |

For all 46 months, independent and archived monthly NAV/TSLA CAD returns
agree to floating-point precision and all month ends match exactly.
This validates the **monthly calculation**, not market-price total return,
a causal explanation for poor down-month performance, hedging impact,
the issuer's individual cash distribution events, or future returns.

Avoid treating the 13 down months as 13 independent randomized experiments.
Regime thresholds are descriptive, sample size is limited, and NAV
exposures include leverage, covered calls, fees and currency hedging.
