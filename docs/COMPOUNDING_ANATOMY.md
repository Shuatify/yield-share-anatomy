# Compounding and log wealth: exact NAV-vs-TSLA accounting

The question is why the YTSL NAV DRIP cumulative wealth gap can be large
even though the average difference of simple daily returns appears small.

## Data and comparison convention

- 2022-12-21 through 2026-11-20; **963 common closes / 962 intervals**
  between consecutive **shared** close dates.
- YTSL: issuer NAV wealth index with distributions reinvested at exact
  ex-date NAV on the full native NAV calendar.
- TSLA CAD: Yahoo TSLA adjusted-close index multiplied by Bank of Canada
  as-of reference USD/CAD, not a hedged or executable quote.
- Nonshared dates are accumulated in native wealth before selecting shared
  endpoints. This is not a uniform calendar-day or trading-day duration
  series, so the term **interval** is intentional.
- Market-price anomalies, tax factors, investor cash taxes, fees paid
  outside the fund and new-money contributions are not separately modeled.

## The exact identity (no regression)

For each paired interval, let \(y_t\) and \(x_t\) be simple YTSL NAV DRIP
and TSLA CAD returns. Neither can be <= -100%.

\[
\log\frac{W_{Y,T}}{W_{X,T}}
=\sum_t[\log(1+y_t)-\log(1+x_t)]
=\sum_t(y_t-x_t)
 +\sum_t\{[\log(1+y_t)-y_t]-[\log(1+x_t)-x_t]\}.
\]

The final bracket is the **nonlinear compounding correction**. We also
compare it with the Taylor quadratic
\(-\frac12\sum_t(y_t^2-x_t^2)\); the higher-order remainder is retained
**exactly**, not discarded.

All displayed components are **100× sums of decimal return terms**
(log-point scaling), not percentage points of initial capital or three
independent economic sources of loss. The arithmetic term and the
nonlinear term are different algebraic views of one *same* historical
return path; no investable counterfactual was estimated.

## Execute offline

~~~bash
uv sync --locked
uv run --locked python -m yield_share_anatomy.compounding
~~~

Outputs under ignored \`outputs/compounding/\`:

- \`compounding_daily.csv\`: per-interval simple-return spread, log
  spread, exact correction, quadratic approximation, higher-order term,
  cumulative wealth and ratios.
- \`annual_log_components.csv\`: by ending calendar year, including
  partial 2022 and 2026.
- \`extreme_intervals.csv\`: ten worst and ten best **interval log
  differences**, not necessarily individual one-trading-day moves.
- \`compounding_summary.json\`: wealth-endpoint check, exact identity
  residual, year and TSLA-sign splits, all input SHA-256s.

The program independently checks wealth computed by accumulating log
returns against native NAV/TSLA level ratios. Any mismatch fails, and
the source snapshots are immutable.

## How to interpret

The **terminal total-return gap** is YTSL's terminal wealth minus
TSLA's terminal wealth, expressed in percent of common *initial*
capital; the **relative wealth shortfall** instead divides YTSL wealth
by *terminal TSLA* wealth. The **log relative wealth gap** is yet another
measure, additive over intervals. These are different quantities and
must never be compared or subtracted as if denominators were identical.

The headline result is an **identity**, not a statement that 73.5% of
the economic loss was caused by leverage, covered calls or realized
volatility. The arbitrary choice of algebraic baseline affects the
fraction ascribed to the nonlinear term. An alternate (also exact)
decomposition could distribute the same terminal gap differently.

The -1/2 squared-return difference resembles the textbook link between
log growth and volatility, but is not a distinct structural estimate
of ETF leverage, fees, gamma, currency hedging or trading decisions.

See the dated [numerical verification](../research/validation/2026-11-20-compounding.md).
