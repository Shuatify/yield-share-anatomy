# TSLA/CAD benchmark and YTSL NAV calendar — real-data audit

**Input provenance:** Owner-supplied output from a local Mac execution of
`yield_share_benchmark_alignment.py`, using `LIVE_SOURCE_DATA` through
2026-11-20. This report is a **transcription of a user-provided local run**;
the raw historical CSVs were not available to the GitHub Actions runner or
independently executed here. See PR #2 for original reported JSON.

## Reproducible window

- Start: 2022-12-21; end: 2026-11-20 (same as Phase 1 prototype)
- Original common days: 958; YTSL NAV days in window: 983
- Independent shared days: 963; five shared days were excluded by old filters:
  2022-12-22, 2023-01-03, 2023-01-04, 2026-06-23, 2026-11-02
- Applied cash events: 47; **zero** ex-dates missing from the old common
  calendar; **zero** event-date shifts

## End-to-end comparison, percentages of initial capital

| Metric | Original Phase 1 | Full-calendar method | Difference (pp) |
|---|---:|---:|---:|
| YTSL NAV DRIP | +120.41139492221969% | +120.41139492221933% | approximately 0 |
| TSLA CAD, unhedged reference | +164.54468803302754% | +164.54468803302754% | 0 |
| YTSL NAV - TSLA CAD | -44.133293110807855 pp | -44.13329311080821 pp | approximately 0 |

Independent TSLA USD adjusted close: **+151.37747249602586%**.
The USD versus unhedged CAD TSLA terminal total-return difference is about
**13.17 percentage points**. This is not an estimate of YTSL's hedge cost
or the covered-call contribution.

The essentially zero method effect is consistent with no cash ex-date shifts
and identical endpoints. Removing intermediate NAV observations without cash
events need not alter compounded terminal wealth, but can still affect
intermediate statistics or month-end selections. Hence this validates the
**cumulative return gap only**, not all monthly/regime analyses.

## Input SHA-256 (original local Phase 0 snapshots)

| File | SHA-256 |
|---|---|
| `ytsl_purpose_daily.csv` | `a0a6c90c3d804c354bc53ef384630f8b0abff6d5fdb5d318cb75ca65ea6e76f7` |
| `tsla_yahoo_daily.csv` | `925076d6d488413b3c8246d206654d719186f3c73bd2bd5007ede1f9acd7c48b` |
| `usdcad_boc_daily.csv` | `ffaca3a83de376bf4b47cc32a5b73015b1a1767933903c0f12a0ab8a119f0fbf` |
| `ytsl_cash_distributions.csv` | `7142c89fa4e15efeef67b87d6d11e32a914863caee47b2b72dfa2422d226108e` |

## Limits and next checks

- NAV cash distributions remain an issuer-unverified secondary-source seed,
  although separate NAV return period benchmarks are closely matched.
- YTSL's hedging, fund financing, leverage and covered calls **cannot** be
  causally decomposed from the observed -44.13 pp difference.
- USD/CAD is a Bank of Canada reference series, not a tradable spot close.
- Market-price anomalies and calendar month regime statistics require their
  own validation; this audit is not their endorsement.

CI in PR #2: 40 offline/synthetic tests passed after centralizing pytest
module resolution in `pyproject.toml`.
