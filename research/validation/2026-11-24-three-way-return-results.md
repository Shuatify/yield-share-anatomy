# Three-way total return results — 2026-11-20 pinned close

**Source status:** verified legacy TSLA CAD / YTSL NAV baseline plus reviewed Yahoo TSLA CDR candidate. Suitable for exploratory comparison under the project's practical verification threshold. Historical pre-TSX CDR backfill remains an acknowledged data limitation.

## Shared comparison basis

- All wealth starts at CAD 100 at the exact **2022-12-21** close and ends **2026-11-20**.
- **963 common closes / 962 close-to-close intervals** (intersection of US TSLA USD, YTSL issuer NAV, and Canadian CDR sessions). YTSL DRIP is calculated first on all native NAV dates; skipped dates are not lost.
- TSLA CAD = Yahoo USD TSLA adjusted close * BoC daily USD/CAD reference; **unhedged**.
- TSLA CDR = CIBC CAD-hedged CDR market close; price and Yahoo adjusted close agree; issuer product page shows dividends/corporate actions N/A. No CDR cash reinvestment is therefore modeled.
- YTSL = issuer NAV DRIP of all *cash* distributions at their NAV ex-date; excludes notional amounts.

## Reproduced cumulative results

| Instrument | Terminal CAD wealth per CAD 100 | Total return |
|---|---:|---:|
| TSLA CAD (unhedged) | 264.544688 | +164.544688% |
| TSLA CDR (CAD hedged) | 229.923072 | +129.923072% |
| YTSL NAV DRIP | 220.411395 | +120.411395% |

- YTSL minus unhedged TSLA CAD: **-44.133293 percentage points**.
- YTSL minus hedged TSLA CDR: **-9.511677 percentage points**.
- TSLA CDR minus unhedged TSLA CAD: **-34.621616 percentage points**.

These are historical *observed outcome* differences, not a causal decomposition of currency, option premiums, leverage, hedging expense, or NAV-vs-market valuation.

## Calendar-year (partial endpoints explicitly marked)

| Period (anchor → last common close) | TSLA CAD | TSLA CDR | YTSL NAV DRIP |
|---|---:|---:|---:|
| 2022 partial (2022-12-21 → 2022-12-30) | -10.907439% | -10.153844% | -12.192325% |
| 2023 (2022-12-30 → 2023-12-29) | +96.984840% | +96.917803% | +89.785097% |
| 2024 (2023-12-29 → 2024-12-31) | +76.815361% | +60.086955% | +45.671142% |
| 2025 (2024-12-31 → 2025-12-31) | +6.074987% | +7.740354% | +16.833266% |
| 2026 partial (2025-12-31 → 2026-11-20) | -19.630398% | -24.653389% | -22.285972% |

**Important cross-chart check:** All three 2025 returns are **positive**. The website must not reuse a previously incorrect 2025 sign or display an end-axis of 2026 when selecting 2025. The yearly figure and interactive figure must read the same generated daily/annual input data.

## Reproducibility and provenance

Executed in GitHub Actions [Python tests / three-way job](https://github.com/Shuatify/yield-share-anatomy/actions/runs/45505214236); all original regression tests and new cross-method/period-compounding tests passed. Artifacts include `three_way_daily.csv`, `three_way_monthly.csv`, `three_way_annual.csv`, `three_way_summary.json`.

**Pinned input SHA-256**:

```text
CDR Yahoo candidate   03b06d6239297c87cbf0f08d09f75fff02c751ebfcb0c17cfd7873b1ddccfb3e
YTSL NAV              a0a6c90c3d804c354bc53ef384630f8b0abff6d5fdb5d318cb75ca65ea6e76f7
YTSL cash events      7142c89fa4e15efeef67b87d6d11e32a914863caee47b2b72dfa2422d226108e
TSLA USD              925076d6d488413b3c8246d206654d719186f3c73bd2bd5007ede1f9acd7c48b
BoC USD/CAD           ffaca3a83de376bf4b47cc32a5b73015b1a1767933903c0f12a0ab8a119f0fbf
```

Recreate outputs: `uv run --locked python -m yield_share_anatomy.three_way`.
