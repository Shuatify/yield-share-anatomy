# Benchmark calendar audit — TSLA USD, TSLA CAD, YTSL NAV

**Scope:** Audit Phase 1's original cumulative return gap on its original
first/last comparison dates. This PR does not change the original Phase 1
analysis, Market Regime labels, or already-validated issuer NAV index.

What changes compared with Phase 1:
1. Calculate YTSL NAV DRIP from the **full NAV history** before aligning it
   to TSLA (reuse the issuer-benchmarked NAV calculation).
2. Calculate TSLA USD adjusted-close total return on actual US sessions.
3. Multiply TSLA adjusted close by Bank of Canada historical USD/CAD
   reference FX (last available reading no older than five calendar days).
4. Keep the **same start and end dates** as the legacy Phase 1 output.
5. Show the delta between original gap and independently calculated gap,
   plus dates removed by old filters and cash ex-dates not on old calendar.

Run:

~~~bash
uv sync --locked
uv run --locked pytest -q
uv run --locked python yield_share_benchmark_alignment.py
~~~

Uses local, ignored Phase 0 files in \`yield_share_phase0_data/\`. Outputs
in \`yield_share_phase1_results/benchmark_calendar/\`:

- \`independent_benchmark_daily.csv\`: same-day observations with NAV DRIP
  wealth, TSLA USD wealth, and TSLA CAD wealth, rebased to legacy start.
- \`calendar_method_bridge.json\`: legacy-vs-independent end returns, effect
  on relative gap, omitted trading/ex-dates, input hashes, and assumptions.

The independent comparison does **not** forward-fill TSLA across non-US
trading days and does not use market-price premium flags to delete NAV rows.
NAV-only calculations still include those days even if the chart's daily
comparison includes only exact common sessions. The analysis is descriptive;
BoC FX is not an investable close or a hedge, and YTSL cash event seed is
not yet individually issuer-verified.

**Interpretation:** If TSLA CAD has the same end-to-end return under both
methods but YTSL NAV differs, the difference comes from the NAV
calendar/reinvestment treatment, not from missing middle-day TSLA quotes.
This does not establish the covered-call contribution; leverage,
hedging, and financing costs are intentionally out of scope.
