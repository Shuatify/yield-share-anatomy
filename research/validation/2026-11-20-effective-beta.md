# Effective beta of YTSL NAV DRIP relative to TSLA CAD

Research run on the fixed historical snapshot dated **2026-11-20**.
This is an **observational**, currency-specific NAV return sensitivity
study, not fund-disclosed nominal leverage or causal attribution.

**Source:** committed, immutable YTSL Purpose NAV, Yahoo TSLA adjusted
closing prices, Bank of Canada USD/CAD reference and 47 provisional
cash ex-date entitlements. Paths in \`data/snapshots/2026-11-20/\` and
\`data/events/ytsl_cash_distributions.csv\`. All four exact input
SHA-256s are emitted into \`effective_beta_summary.json\`.

**Command:** \`uv run --locked python -m yield_share_anatomy.exposure\`.

## Reproducible comparison

- Period: **2022-12-21** to **2026-11-20**.
- 963 exact shared NAV / TSLA CAD closing dates, 962 common-close
  *return intervals*. A Canada/US nonshared trading date is **not**
  discarded from native NAV wealth calculation; returns across the
  intervening interval accrue before same-date alignment.
- OLS with an intercept: \`r(YTSL NAV DRIP) = alpha + beta * r(TSLA CAD)\`.
  Betas are unitless, returns are simple interval returns.
- R² for full paired-interval sample: **0.97943**.
- Conditional subsets split on the **contemporaneous TSLA CAD return sign**.

| Sample | Paired intervals | Estimated beta | Mean NAV minus TSLA per interval |
|---|---:|---:|---:|
| All | 962 | **1.08406** | −0.00503 pp |
| TSLA CAD positive | 485 | **1.02761** | +0.22070 pp |
| TSLA CAD negative | 477 | **1.15791** | −0.23456 pp |

Difference **Down beta minus Up beta = +0.13030**.

This is a slope contrast between two *separately fitted* conditional
regressions, each with its own intercept. It is not the amount of
excess return or the fund's option exposure.

## Moving-block bootstrap: uncertainty

Predeclared default: blocks of 10 consecutive common-close return
intervals, 800 overlapping-block resamples with replacement, fixed
seed \`20261120\`. Empirical percentile 95% limits:

| Estimate | Bootstrap 95% percentile interval |
|---|---|
| Full beta | 1.05359–1.11013 |
| Up beta | 0.97627–1.08366 |
| Down beta | 1.11114–1.18902 |
| **Down − Up beta** | **+0.05226 to +0.18709** |

The difference interval does **not** contain zero under this
resampling specification.

As a simple robustness check, rerun with \`--block 5\` and
\`--block 21\` (400 resamples per case, same seed):

| Block size | Resamples | Down minus Up beta, 95% interval |
|---|---:|---|
| 5 | 400 | +0.05684 to +0.19025 |
| 10 | 800 | +0.05226 to +0.18709 |
| 21 | 400 | +0.04560 to +0.18761 |

All three intervals stay positive, **within this particular
historical sample and bootstrap family**. This is not a general
frequentist guarantee under changing market conditions or an
independent discovery of a structural leverage multiplier.

## Year-by-year stability

The partial December 2022 sample has only 5 paired intervals and
is marked \`insufficient_sample\`; do not annualize it.

| Year | Paired intervals | Up beta | Down beta | Down − Up |
|---|---:|---:|---:|---:|
| 2023 | 245 | 1.00195 | 1.13452 | +0.13258 |
| 2024 | 247 | 0.97394 | 1.14064 | +0.16669 |
| 2025 | 245 | 1.11043 | 1.18143 | +0.07100 |
| 2026 through Nov 20 | 220 | 1.04355 | 1.16083 | +0.11728 |

Every full study year has a positive point estimate, but no
year-specific confidence intervals or multiple-testing adjustments
have been computed.

Trailing 63-interval beta on 2026-11-20 = **1.09728**;
historical range **0.96491–1.19780**.
Trailing 126-interval beta on 2026-11-20 = **1.11229**;
historical range **1.01267–1.14928**.

As a **separate, lower-sample** monthly check using the
independently verified 46 full months, pooled monthly beta =
**1.02801**. For 18 months with TSLA CAD >+5%, conditional beta =
**0.88286**; for 13 months with TSLA CAD <−5%, conditional beta =
**1.17069**. Month-selection is retrospective and the small samples
do not establish predictive behaviour.

## Interpretation and open questions

The daily YTSL NAV response is highly correlated to TSLA CAD and
historically steeper within negative TSLA return intervals. That is
consistent with a nonlinear fund payoff **but does not distinguish**
covered-call payoff curvature, financing, leverage, FX hedging,
management decisions or date-close/FX-reference mismatches.

Critically, daily arithmetic relative returns average only
~−0.00503 pp per interval, while the separately validated
*terminal wealth* gap is −44.1333 pp of initial capital.
These quantities are mathematically different; additive returns,
geometric compounding and volatility/convexity can create
substantial divergence. **Next increment:** analyze the exact
log-wealth identity and compounding terms, without labeling an
accounting residual as a unique causal source.

The present 47-cash-event seed is still unverified against each
official Purpose distribution announcement; nor is YTSL Market
Price DRIP validated by this NAV study.

**Validation:** GitHub Actions run
https://github.com/Shuatify/yield-share-anatomy/actions/runs/45322480128
passed **86 offline tests**, including the pinned historical
exposure regression; also successfully ran the default 800-replicate
study and 5/21-block sensitivity checks. This report records the
observed output, but is not a provider-issued beta benchmark.
