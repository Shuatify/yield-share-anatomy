# Three-way CAD total return: TSLA unhedged, TSLA CDR, YTSL NAV DRIP

## Purpose

Compare the historical **growth of CAD 100 at the exact same initial close** across (1) unhedged TSLA CAD, (2) hedged TSLA CDR, and (3) YTSL NAV with each eligible cash distribution reinvested. Fixed window **2022-12-21 through 2026-11-20**. All source inputs are pinned in Git; this is a historical measurement, not trading guidance.

## Inputs and independent wealth calculation

1. **TSLA CAD (unhedged):** Yahoo adjusted USD TSLA close multiplied by the Bank of Canada daily USD/CAD reference rate, carried backward at most 5 calendar days; no hedge assumed. The resulting CAD-wealth path is indexed to CAD 100 at the initial shared close. This is an indicative, not necessarily executable, FX conversion.
2. **TSLA CDR (hedged):** pinned CAD TSLA CDR historical market **Close** from the reviewed Yahoo TSLA.TO candidate in `data/snapshots/2026-11-20-cdr-yahoo/`. The CIBC product page showed dividend history and corporate actions as N/A as of 2026-11-24; Close and Adj Close match all study dates. **We therefore assume no additional cash distribution and treat the CDR price index as its total return.** Marked 'reviewed vendor data', not full historical official Cboe verification.
3. **YTSL NAV DRIP:** issuer NAV wealth index compounded on YTSL's *complete native NAV calendar*, incorporating the 47 cash entitlements at their exact ex-date NAV; then—and only then—select 963 shared close dates. Notional events are excluded. This is the existing issuer-return-reconciled research method; cash-event list remains annotated as provisional.

All three paths are independently constructed before date intersection. The **963 shared closes** span 2022-12-21 to 2026-11-20, for **962 close-to-close intervals**. Some intervals exceed one trading day because US and Canada have distinct market holidays. Do not interpret each row as one uniform 24-hour day.

## Why the three ways are comparable, but not perfect causal controls

- TSLA CDR and YTSL both seek CAD currency hedging, but their implementations and actual hedge costs differ.
- YTSL's issuer NAV differs in basis from TSLA CDR's traded market close. Comparing their wealth outcomes is meaningful; attributing the entire gap to covered calls/leverage/fees is not.
- Raw TSLA CAD represents an unhedged Canadian's underlying TSLA value, *not* a hedged benchmark.
- The 539 pre-2025-02-14 Yahoo TSLA.TO observations are market vendor backfill for a period when the CDR traded on Cboe. They were checked via multiple consistency diagnostics and a dated third-party spot quote but are not all independently sourced from Cboe. The user considers this adequate for the present exploratory comparison.

## Reproduce

```bash
uv sync --locked
uv run --locked pytest -q tests/test_three_way.py
uv run --locked python -m yield_share_anatomy.three_way
```

Outputs in ignored `outputs/three_way/`: `three_way_daily.csv` (rebased wealth), `three_way_annual.csv`, `three_way_monthly.csv`, and `three_way_summary.json`, with input SHA-256 hashes. **Do not manually recalculate yearly returns or axis ranges in a website UI; consume these exact computed series.**

## Computation and display invariants

- Exact first / last common dates are mandatory and fail hard when absent.
- Annual returns use the prior calendar year's last *shared* close as the anchor; the first and final partial years are labeled. Monthly returns use the same principle.
- The product of each annual or monthly period's gross-return factors **must exactly reconcile** to terminal wealth (floating tolerance). This guards against year-2025 sign disagreements between visualizations.
- Unit tests assert the two previously validated endpoint baselines for YTSL and TSLA CAD, and the CDR candidate's 13.00 to 29.89 endpoint change. No new benchmark replaces those baselines.
- The website should display yearly data from `three_way_annual.csv` and selectable date ranges from `three_way_daily.csv`; axes and values must be recomputed from the selected date range, not fixed to 2026.

## Sources

- CIBC issuer directory: https://cdr.cibc.com/en/cdr-directory/TSLA
- TSLA CDR provisional validation: `research/validation/2026-11-24-tsla-cdr-provisional-audit.md`
- Existing NAV and TSLA benchmark protocol: `docs/DATA.md`, `docs/COMPOUNDING_ANATOMY.md`
