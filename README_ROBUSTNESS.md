# Phase 1: Market Regime Robustness (offline)

This add-on reads your existing `yield_share_phase1_results/monthly_regimes.csv`. No dependency changes and no network requests. It does not change the Phase 1 return engine.

From the project root:

```bash
unzip -o ~/Downloads/yield_share_phase1_robustness_patch.zip -d .
uv run --locked python -m unittest -q test_regime_robustness.py
uv run --locked python yield_share_regime_robustness.py
cat yield_share_phase1_robustness/robustness_summary.json
```

The script recomputes up / sideways / down partitions at monthly underlying-stock return thresholds ±3%, ±5%, ±8%, and ±10%. It reports NAV-vs-stock and market-vs-stock differences, win rates, largest monthly gaps, and leave-one-month-out sensitivity.

**Caveats**: Cash distribution events have not been line-by-line reconciled with issuer announcements. Changing thresholds is a sensitivity test, not permission to select whichever value produces a preferred headline. Historical YTSL-vs-TSLA differences cannot be attributed solely to call-writing because leverage, financing, hedging and fees also contribute.
