# Frictionless TSLA CAD daily-leverage counterfactual

This research tests a **narrow falsifiable model**: is simply increasing
and resetting exposure to the *unhedged TSLA/CAD reference* enough to
reproduce the observed YTSL NAV DRIP return and its asymmetric betas?

This is **not a clone of YTSL**. It does not simulate the issuer's option
book, dynamic underlying position, actual FX hedge, financing agreements,
fees, distributions, trading prices or execution.

## Pinned data and model

2022-12-21 through 2026-11-20, using the committed historical snapshot.
Daily model reset on **983 valid native US TSLA closing sessions**.
Only afterward is each model wealth path aligned with the **963 shared
TSLA/YTSL closing dates** for comparison.

Let \(P_t\) be Yahoo's adjusted TSLA USD closing reference multiplied by
the Bank of Canada's most recent valid USD/CAD reference (maximum
five calendar days old). At each actual TSLA US daily close, the
hypothetical portfolio resets its **notional exposure** to L times
equity wealth, where \(L = 1.0, 1.1, 1.2\).

\[
R_{P,t}=P_t/P_{t-1}-1,\qquad
W_{L,t}=W_{L,t-1}(1+L R_{P,t}),\qquad W_{L,0}=1.
\]

This is a **daily rebalanced, frictionless** simple-return proxy.
It has **zero funding/financing cost, zero fee, zero trading slippage,
zero tax**, no cash drag and no funding/margin constraints apart from
halting if the wealth factor is nonpositive. Nothing is currency-hedged.

Data on dates without an issuer NAV are still processed in the TSLA
path. Applying L to a *multi-day* common-close return would be a
different reset convention and is deliberately not used.

Original YTSL NAV DRIP is separately calculated on **all** Purpose NAV
dates with cash reinvestment on exact ex-dates, then selected at the
same endpoints. The underlying TSLA CAD 1.0× series must match the
independent validated TSLA/CAD reference total return to numerical
precision.

For comparability, drawdowns below are measured on shared closes
only. Native US-session drawdowns may be slightly different.

## Run

~~~bash
uv sync --locked
uv run --locked python -m yield_share_anatomy.leverage
~~~

Outputs are ignored under \`outputs/leverage_counterfactual/\`:

- \`daily_model_on_tsla_sessions.csv\`: all 983 native US TSLA trading
  dates for each of three daily-reset model paths, including wealth
  factor and funding-free reset return;
- \`common_close_wealth.csv\`: same-date YTSL NAV wealth and simulated
  wealth on 963 comparison closes;
- \`leverage_counterfactual_summary.json\`: terminal returns, difference
  from YTSL, shared-close max drawdown, full and Up/Down conditional
  beta on the **same 962 paired common-close intervals**, calendar
  year returns, data SHA-256 fingerprints and assumptions.

The model explicitly checks that 1.0× exactly reconstructs the
previously verified TSLA CAD total return, that daily factors are
valid, no input FX/price is missing, and initial/final dates match.

## Interpreting the gap

The fact that a zero-cost 1.2× TSLA/CAD model outperforms YTSL NAV
does **not** establish that option overwrite accounts for the residual,
nor that an actual investor could obtain that same financing and
exposure. Realistic funding costs would reduce the model returns.
Currency hedging, volatility, covered-call caps, ETF distribution
timing, portfolio financing, trading and fees could all affect YTSL,
but without the issuer's actual daily exposures and transactions
their separate contributions cannot be identified.

An observed conditional Down-vs-Up beta difference for YTSL, and near
zero for constant daily-reset model paths, establishes that a **fixed**
L on this CAD underlying reference fails to reproduce the historical
return asymmetry. It does not prove the covered-call overlay caused it.

See [dated validation results](../research/validation/2026-11-20-leverage-counterfactual.md).
