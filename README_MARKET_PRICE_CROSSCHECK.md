# YTSL Market Price: Purpose vs Yahoo historical cross-check

**Purpose NAV and market-price CSV are the primary inputs and remain unchanged.**
A [one-off GitHub Actions query](https://github.com/Shuatify/yield-share-anatomy/actions/runs/45117810520)
retrieved daily YTSL.NE OHLCV from Yahoo Chart API (HTTP 200) on 2026-11-23.
Source: [Yahoo Chart API](https://query1.finance.yahoo.com/v8/finance/chart/YTSL.NE?period1=1671408000&period2=1673049600&interval=1d&events=history).
The historical snapshot is frozen in \`data/reference/ytsl_yahoo_close_2022_2023.csv\`.

| Date | Purpose NAV | Purpose Price | Yahoo Close | Decision |
|---|---:|---:|---:|---|
| 2022-12-20 | 18.17 | 24.89 | 18.29 | **Exclude:** Yahoo Close < Yahoo Low 18.58 |
| 2022-12-22 | 16.25 | 22.33 | 16.35 | Yahoo substitute, derived market series only |
| 2023-01-03 | 13.28 | 15.66 | 13.31 | Yahoo substitute, derived market series only |
| 2023-01-04 | 14.03 | 15.66 | 13.95 | Yahoo substitute, derived market series only |

Yahoo's 2022-12-30 Close was **15.66**, also the anomalous issuer price
on 2023-01-03 and 2023-01-04. It suggests stale observations but does
not prove the issuer's underlying error. Independent Cboe data for
2022-12-20 would help resolve that remaining case.

### Resolution policy

1. Use original Purpose \`price\` if positive and within ±10% of
   Purpose same-day NAV. This is a **diagnostic threshold**, not proof of
   what an ETF may legitimately trade at.
2. For flagged/missing prices, accept same-day Yahoo **Close (not Adj Close)**
   only if OHLC are internally consistent (±0.01 CAD tolerance), volume >0,
   and Yahoo Close is within ±10% of Purpose NAV.
3. If unresolved and **not** a cash/notional distribution ex-date, exclude
   from the **derived market-price** series. Never forward-fill.
4. If unresolved **on** a distribution ex-date, block derived return
   calculation rather than silently skipping an entitlement day.
5. Keep Purpose raw data and all resolution decisions traceable with
   file SHA-256 fingerprints.

The four flagged dates are not the only potentially missing prices in the
full source file. The script also flags missing/nonpositive Purpose prices
and marks them unresolved unless a matching verified secondary quote exists.

### Offline use

~~~bash
uv run --locked pytest -q
uv run --locked python yield_share_market_price_reconciliation.py
~~~

Local ignored outputs in
\`yield_share_phase1_results/market_price_quality/\`:
\`market_price_source_discrepancies.csv\`,
\`market_price_reconciled_daily.csv\`,
\`market_price_reconciliation_status.json\`.

**This PR does not rewire the old Phase 1 market-price DRIP calculation,**
modify NAV Total Return or add background data fetching. To recheck future
anomalies, store a new dated Yahoo OHLCV snapshot with the same columns
and pass \`--yahoo path/to/snapshot.csv\`; do not silently overwrite this reference.
