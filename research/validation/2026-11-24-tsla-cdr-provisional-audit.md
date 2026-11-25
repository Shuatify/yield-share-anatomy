# TSLA CDR historical acquisition — 2026-11-24 validation

**Status: PROVISIONAL. Not yet suitable for a published research-grade total-return comparison.**

## Issuer and venue facts

- CIBC Tesla product page (https://cdr.cibc.com/en/cdr-directory/TSLA) showed Dividend History N/A, Corporate Actions N/A, and underlying Tesla dividend N/A on 2026-11-24. This is evidence for no CDR cash distributions; daily CDR Ratio hedging adjustments are separate from splits.
- CIBC issuer delisting notice: https://cibc.mediaroom.com/2025-02-11-CIBC-voluntarily-de-lists-10-Canadian-Depositary-Receipts-from-Cboe-Canada — last Cboe listing session 2025-02-13.
- TSX original listing: https://www.tsx.com/en/news/new-company-listings?id=1898 — first TSX session 2025-02-05.
- Yahoo TSLA.NE returned valid metadata but zero candles for 2022-12-21..2026-11-20. Yahoo TSLA.TO returned 983 candidate sessions, of which 539 belong before 2025-02-14. These pre-TSX dates are **unverified vendor backfill**, not historical TSX venue trades.
- Yahoo source-response SHA-256 and request URLs are recorded in the archived quality_report.json. No invalid OHLC, zero-volume, duplicates, adjusted-close differences, or missing YTSL NAV calendar dates were found. Yahoo chart reported no dividend or split events during the study window; issuer verification is still required.

## Dated third-party and exchange crosschecks

| Evidence | Date / period | Candidate vs published | Interpretation |
|---|---|---|---|
| Stockwatch contemporaneous TSX original-listing report (https://www.stockwatch.com/News/Item/Z-C!TSLA-3649863/C/TSLA) | 2025-02-03 (pre-TSX) | Yahoo CAD 34.86 vs Stockwatch CAD 34.87 | Independent dated secondary historical quote, 1-cent difference |
| TMX TSX Alpha Daily Record 2026-01-09 (https://www.tsx.com/files/alpha/daily-record/AlphaDailyRecord01092026.pdf) | 2026-01-09 | Yahoo 39.21 vs Alpha 39.19 | Venue-specific, not consolidated exchange market close |
| TMX TSX Alpha Daily Record 2026-06-02 (https://www.tsx.com/files/alpha/daily-record/AlphaDailyRecord06022026.pdf) | 2026-06-02 | Yahoo 36.98 vs Alpha 36.98 | Venue-specific, not consolidated exchange market close |
| PortfoliosLab TSLA.TO historical monthly returns (https://portfolioslab.com/symbol/TSLA.TO) | All 36 months in 2023-2025 | All published 2-decimal monthly returns match candidate calculations; full years +96.92%, +60.09%, +7.74% | Source not independent: likely same upstream Yahoo/vendor dataset |

PortfoliosLab also displays a +198% one-day CDR move on the Tesla 2022 stock split date, **outside this research window**. Do not assume this secondary source has independently handled historical corporate actions correctly.

## Independent frozen-input tracking diagnostic

GitHub Actions executes yield_share_anatomy.cdr_proxy_validation on the candidate CSV plus the fixed TSLA USD and BoC FX snapshots, and uploads the detailed paired series and input SHA-256 values.

- 963 shared closes / 962 common-close intervals, 2022-12-21..2026-11-20. The other 20 CDR days lack TSLA US sessions; their movement is accumulated between successive shared closes.
- CDR CAD versus underlying TSLA USD shared-interval daily return correlation: **0.999015**.
- Mean absolute common-close return gap: **0.11826 percentage points**. Maximum: **1.03999 pp**.
- Implied traded-price proxy CDR close / (TSLA USD adjusted close * BoC USDCAD): **0.06942208** at first common close and **0.06033665** at last. **This is NOT the official CIBC daily CDR Ratio**; market price and reference-FX timing affect it.
- High correlation is only a continuity sanity check, not independent verification of the 539 backfilled historical CDR prices.

## Strict release gates

1. Obtain independent, dated Cboe Canada Closing Price File data for a broad pre-2025 sample (especially 2023, 2024 and the February 2025 overlap). Cboe data service: https://www.cboe.com/market_data_services/ca/equities. Log mismatches, never replace silently.
2. Export and freeze CIBC TSLA CDR Ratio History from its official interactive directory; inspect any splits/corporate actions and confirm the no-dividends hypothesis.
3. Review calendar mismatches, extraordinary moves, tracking differences and adjusted prices; attach source and input hashes.
4. Only then create a separate verified dated snapshot and separate PR for the three-way TSLA CAD / TSLA CDR / YTSL NAV-DRIP total-return analysis.

**No causal inference about hedging costs, covered calls, leverage or expenses can be made from these acquisition/QC diagnostics.**
