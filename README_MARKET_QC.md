# Phase 1 · Market price anomaly audit

The previously printed YTSL market return **+61.6506%** is **not suitable for interpretation** because the first common day (2022-12-20) is $24.89 market price vs $18.17 NAV, a +36.98% premium in Purpose’s raw CSV. On 2022-12-22, $22.33 vs $16.25 NAV is another +37.42% premium. These may be bad/stale values or real exceptional trading, not yet independently verified.

This patch:
- Flags `abs(price/NAV - 1) > 10%` using **same-day** NAV and price.
- Excludes those observations from **all** paths in the common-calendar preliminary comparison, including the initial observation. This prevents an apples-to-oranges start date.
- Never edits raw Purpose CSV.
- Saves `market_price_anomalies.csv` with dates, NAV, price, % premium, reason.
- Reports flagged days and counts in `analysis_status.json`.
- Treats cleaned market-price performance as **provisional**, not a certified tradeable historical return.

Unzip in the existing project directory, overwriting the returns script. No dependency changes.

```bash
unzip -o ~/Downloads/yield_share_phase1_market_qc_patch.zip -d .
uv run --locked pytest -q
uv run --locked python yield_share_phase1_returns.py \
  --data-dir yield_share_phase0_data \
  --out yield_share_phase1_results
cat yield_share_phase1_results/analysis_status.json
cat yield_share_phase1_results/regime_summary.csv
cat yield_share_phase1_results/market_price_anomalies.csv
```

The calculation still uses preliminary 47 cash-event seed rows. Verify them with Purpose announcements before any publication. Regime summaries are descriptive. NAV results can be used for internal exploratory comparison pending distribution verification and cross-check to issuer total returns.
