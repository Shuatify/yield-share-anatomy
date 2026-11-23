# YTSL NAV Total Return — official reconciliation

This is a **NAV-only audit**, not a rewrite of the existing TSLA/YTSL
comparison pipeline. It uses **all valid Purpose NAV trading days** and does
not filter based on market-price anomalies, TSLA, or FX.

Run the offline test suite, followed by issuer reconciliation using the
historical Phase 0 NAV CSV on the local Mac:

~~~bash
uv sync --locked
uv run --locked pytest -q
uv run --locked python yield_share_nav_reconciliation.py \
  --nav yield_share_phase0_data/ytsl_purpose_daily.csv \
  --events data/ytsl_cash_distributions.csv
~~~

Files in the ignored \`yield_share_phase1_results/nav_reconciliation/\`
directory:
- \`nav_only_daily_index.csv\` — raw NAV + cash + normalized DRIP index
- \`nav_reconciliation.csv\` — issuer return vs calculated return by period
- \`nav_reconciliation_status.json\` — status, parameters, SHA-256 hashes

Benchmark: Purpose Investments [YTSL performance](https://www.purposeinvest.com/funds/tesla-yield-shares-purpose-etf/performance),
**as at 2026-10-30**: 1M 14.99%, 3M 35.38%, 6M 7.63%,
YTD -9.26%, 1Y -9.55%, 3Y annualized 25.32%, since inception
annualized 24.55%. The exact period-anchor method and issuer day count
are still assumptions. The diagnostic threshold is **0.20 percentage
points**; never adjust inputs or thresholds just to make it pass.

Cash ex-dates must exist in the NAV series. Cash is accrued/reinvested at
ex-date closing NAV. Notional distributions are excluded from the cash
ledger and require separate validation for unit consolidation.
The existing 47 cash events are an **unverified secondary-source seed**,
and 2023 tax-factor versus notional classification is unresolved.
**Passing a numerical comparison does not make the research publishable
or fully issuer-verified.**

The CLI returns status 2 for discrepancies outside the stated tolerance.
No changes to raw CSVs, existing return calculations, dependencies,
or site code are included in this PR.
