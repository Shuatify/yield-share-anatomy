# 2026-11-20 zero-cost daily-reset TSLA CAD leverage experiment

**Study:** 2022-12-21 to 2026-11-20; 983 TSLA US daily close
observations and 963 dates shared with YTSL NAV (962 common-close
return intervals). Frozen data from \`data/snapshots/2026-11-20/\`
and the provisional \`data/events/ytsl_cash_distributions.csv\`.

## Exactly specified counterfactual

For each native US trading date after the first, assume
\`daily wealth factor = 1 + L * TSLA_CAD_daily_simple_return\`,
for constant \(L\in\{1.0, 1.1, 1.2\}\).
**No funding interest, option overlay, hedging, execution slippage,
fees or taxes**. Rebalance every TSLA US closing session, including
sessions absent from the YTSL NAV calendar. Wealth starts at 1 on
2022-12-21; compare only identical endpoints on 2026-11-20.

### End wealth and returns

| Path | Final wealth | Total return | YTSL NAV minus model (initial-capital pp) |
|---|---:|---:|---:|
| Observed YTSL NAV DRIP | 2.20411395 | +120.4114% | — |
| TSLA CAD 1.0× | 2.64544688 | +164.5447% | −44.1333 pp |
| Daily-reset 1.1× | 2.71765705 | +171.7657% | −51.3543 pp |
| Daily-reset 1.2× | 2.75626905 | +175.6269% | −55.2155 pp |

**The frictionless constant leverage models do not reproduce the
historical YTSL NAV underperformance.** Higher constant leverages
actually increase their terminal return in this particular sample.
But borrowing costs and option/hedging policies are absent, and the
sample is path-specific. No causal attribution is possible.

### Matched common-close conditional beta

| Series | Up TSLA/CAD beta | Down TSLA/CAD beta | Down−Up |
|---|---:|---:|---:|
| Actual YTSL NAV DRIP | 1.02761 | 1.15791 | **+0.13030** |
| Model 1.0× | ~1.0000 | ~1.0000 | ~0 |
| Model 1.1× | 1.10028 | 1.10006 | **−0.00022** |
| Model 1.2× | 1.20061 | 1.20014 | **−0.00047** |

The very small non-zero differences in 1.1× and 1.2× model
conditional betas arise because US-only intermediate sessions are
rebalanced before modeling the later shared-close interval.
This distinction is deliberate; the model's **native US daily beta**
would be equal to the input leverage by construction.

Drawdown on *shared closes* only: model 1.0× ~−54.20%, model 1.1×
~−58.14%, model 1.2× ~−61.83%. These are not margin/liquidation
risk measures and are not individual US-session drawdowns.

## Validation and limitations

\`uv run --locked python -m yield_share_anatomy.leverage\`

The CLI stores model input hashes and each scenario in
\`outputs/leverage_counterfactual/\`. Synthetic unit tests require
native US daily resetting even on a date without Canadian issuer NAV,
and check 1.0× reference identity, impossible leverage losses,
missing values, and shared endpoint selection.

**Do not call the remaining YTSL-vs-model gap a covered-call
premium cost.** It blends many unmodeled real-world mechanisms, and
YTSL's actual target leverage, hedged currency and option notional
are not controlled here. The next research step should seek
issuer portfolio holdings, option positions, and financing rules
before attempting a quantitative causal attribution.
