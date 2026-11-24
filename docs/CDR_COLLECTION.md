# TSLA CDR — historical price acquisition and quality-control protocol

**Goal:** collect a candidate daily CAD-quoted Tesla CDR market-price series for
2022-12-21 through 2026-11-20. Do **not** compute or publish three-way
returns until the new input is independently validated. Keep the existing YTSL
NAV DRIP / TSLA CAD / Bank of Canada pinned snapshots unchanged.

## Source order

1. **Issuer:** https://cdr.cibc.com/en/cdr-directory — current quotes,
   CDR Ratio History, FX forward history, and corporate-action notices.
   No downloadable issuer historical *daily OHLCV* dataset was confirmed.
   CDR ratios are not themselves historical traded prices.
2. **Exchange:** TSX/TMX (post-listing) and Cboe Canada (legacy). Official
   venue notices establish listing and de-listing dates. Use dated exchange
   records as independent quote verification; archive evidence and dates.
3. **Yahoo:** daily `TSLA.NE` Cboe series through 2025-02-13, and
   `TSLA.TO` TSX series starting 2025-02-14. The two symbols **must not
   be naively concatenated**, since post-delisting NE quotes may be stale.

References:
- https://www.tsx.com/en/news/new-company-listings?id=1898
- https://cibc.mediaroom.com/2025-02-11-CIBC-voluntarily-de-lists-10-Canadian-Depositary-Receipts-from-Cboe-Canada

## Run (on a network-enabled machine)

```bash
uv sync --locked
uv run --locked python -m yield_share_anatomy.cdr \
  --out outputs/cdr_collection \
  --calendar-csv data/snapshots/2026-11-20/ytsl_purpose_daily.csv
uv run --locked pytest -q tests/test_cdr.py
```

If Yahoo HTTP requests fail (including 429), stop; **never synthesize
prices**. Retry later or supply saved unmodified Yahoo chart JSON with
`--ne-json path/to/ne.json --to-json path/to/to.json`.

For external cross-checks, independently obtain daily close pairs in CSV
with columns `date,close_cad`. Pass them using
`--exchange-csv path.csv` or `--cibc-csv path.csv` (only if the issuer
actually offers price data; **not** CDR Ratio values). These files are
cross-checks and do not silently replace the primary series.

## Outputs

All generated files live in Git-ignored `outputs/cdr_collection/`:

- `yahoo_TSLA_NE_raw.json` and `yahoo_TSLA_TO_raw.json`: saved chart
  response evidence plus SHA-256 reported in the manifest.
- `yahoo_TSLA_NE_candidate.csv` and `yahoo_TSLA_TO_candidate.csv`:
  separate venue prices including OHLC, adjusted close and volume.
- `tsla_cdr_preliminary_daily.csv`: one row per session, recording the
  selected source `ticker`.
- `quality_report.json`: missing dates relative to the existing NAV
  calendar, venue overlap discrepancies, OHLC/volume checks, large price
  moves and any supplied independent cross-check mismatches.

The report is deliberately labeled `needs_review`, even if it contains no
machine-detected anomalies. An anomaly cannot be erased by forward-filling
prices or substituting an unverifiable price. Document and independently
resolve exceptions before committing a dated data snapshot.

## Release criteria for a verified dataset

1. Confirm full 2022-12-21 to 2026-11-20 coverage and endpoint sessions.
2. Validate Feb 5-13, 2025 dual-listing overlap, and Feb 14 transition.
3. Cross-check flagged **and regularly sampled** closes with TSX or
   archived Cboe records. Review stale/zero volume, atypical returns and
   suspect adjusted close/splits.
4. Add CIBC **daily CDR ratio** history if exportable. Use
   `TSLA USD * USD/CAD * CDR ratio` as a dated **diagnostic** only,
   respecting market timing differences; do not use calculated parity as a
   substitute for missing real closes.
5. Validate CDR corporate actions/distributions with CIBC. Tesla itself
   does not pay regular cash dividends in this window, but confirm there
   are no separate CDR cash events before claiming price = total return.
6. Commit a new versioned snapshot + QC report in a **separate** PR only
   after quality review. No modifications to legacy research outputs.
