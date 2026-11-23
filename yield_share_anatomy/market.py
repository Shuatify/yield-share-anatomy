#!/usr/bin/env python3
"""Audit Purpose YTSL market prices against frozen Yahoo Close evidence.

Never edit raw Purpose observations. A suspicious issuer price can be
replaced for a *derived market-price* series only if the Yahoo OHLCV
internally validates. Unresolved non-ex-date rows may be excluded;
unresolved cash/notional ex-dates block downstream calculation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .paths import SNAPSHOT_DIR, CASH_EVENTS, NOTIONAL_EVENTS, OUTPUT_DIR

import pandas as pd

PREMIUM_THRESHOLD_PCT = 10.0


def _load(path: Path, columns: set[str], name: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if not columns.issubset(frame.columns):
        raise ValueError(f'{name} missing {sorted(columns - set(frame.columns))}')
    frame['date'] = pd.to_datetime(frame['date'], errors='coerce')
    if frame['date'].isna().any() or frame['date'].duplicated().any():
        raise ValueError(f'{name} has invalid or duplicate dates')
    return frame.sort_values('date').reset_index(drop=True)


def _positive(series: pd.Series) -> pd.Series:
    v = pd.to_numeric(series, errors='coerce')
    return v.notna() & v.gt(0) & v.lt(float('inf'))


def reconcile_market_prices(issuer: pd.DataFrame, yahoo: pd.DataFrame,
                            distribution_ex_dates: set[pd.Timestamp],
                            premium_threshold_pct: float = PREMIUM_THRESHOLD_PCT
                            ) -> pd.DataFrame:
    if not 0 < premium_threshold_pct <= 100:
        raise ValueError('Invalid premium threshold')
    for name, f, fields in [
        ('Purpose', issuer, {'date', 'nav', 'price'}),
        ('Yahoo', yahoo, {'date', 'open', 'high', 'low', 'close', 'volume'}),
    ]:
        if not fields.issubset(f.columns):
            raise ValueError(f'{name} missing {sorted(fields - set(f.columns))}')
        if f['date'].isna().any() or f['date'].duplicated().any():
            raise ValueError(f'{name} duplicate or invalid dates')

    raw = issuer[['date', 'nav', 'price']].copy()
    raw['nav'] = pd.to_numeric(raw['nav'], errors='coerce')
    raw['price'] = pd.to_numeric(raw['price'], errors='coerce')
    if not _positive(raw['nav']).all():
        raise ValueError('NAV is missing or nonpositive; do not repair NAV with market quotes')
    provenance_fields = [col for col in ('source', 'retrieved_at_utc', 'reference_file')
                         if col in yahoo.columns]
    secondary = yahoo[['date', 'open', 'high', 'low', 'close', 'volume',
                       *provenance_fields]].copy()
    for col in ('open', 'high', 'low', 'close', 'volume'):
        secondary[col] = pd.to_numeric(secondary[col], errors='coerce')
    out = raw.merge(secondary, on='date', how='left', validate='one_to_one')
    out = out.rename(columns={'price': 'purpose_price', 'open': 'yahoo_open',
                              'high': 'yahoo_high', 'low': 'yahoo_low',
                              'close': 'yahoo_close', 'volume': 'yahoo_volume'})
    out['purpose_premium_pct'] = 100 * (out['purpose_price'] / out['nav'] - 1)
    out['yahoo_premium_pct'] = 100 * (out['yahoo_close'] / out['nav'] - 1)
    out['flagged'] = (~_positive(out['purpose_price']) |
                      out['purpose_premium_pct'].abs().gt(premium_threshold_pct))
    valid_ohlcv = (
        _positive(out['yahoo_open']) & _positive(out['yahoo_high']) &
        _positive(out['yahoo_low']) & _positive(out['yahoo_close']) &
        out['yahoo_volume'].gt(0) &
        out['yahoo_high'].ge(out['yahoo_low']) &
        out['yahoo_open'].between(out['yahoo_low'] - 0.01, out['yahoo_high'] + 0.01) &
        out['yahoo_close'].between(out['yahoo_low'] - 0.01, out['yahoo_high'] + 0.01)
    )
    out['yahoo_ohlcv_valid'] = valid_ohlcv
    out['yahoo_nav_plausible'] = (out['yahoo_premium_pct'].abs()
                                  .le(premium_threshold_pct))
    out['is_distribution_ex_date'] = out['date'].isin(distribution_ex_dates)
    substitute = out['flagged'] & valid_ohlcv & out['yahoo_nav_plausible']
    unresolved = out['flagged'] & ~substitute
    blocked = unresolved & out['is_distribution_ex_date']
    out['resolution'] = 'issuer'
    out.loc[substitute, 'resolution'] = 'yahoo_substitute'
    out.loc[unresolved & ~blocked, 'resolution'] = 'exclude_unverified'
    out.loc[blocked, 'resolution'] = 'blocked_ex_date'
    out['research_price'] = out['purpose_price'].where(~out['flagged'])
    out.loc[substitute, 'research_price'] = out.loc[substitute, 'yahoo_close']
    out['research_price_source'] = 'Purpose'
    out.loc[substitute, 'research_price_source'] = 'Yahoo Finance Close'
    out.loc[unresolved, 'research_price_source'] = 'unresolved'
    return out.sort_values('date').reset_index(drop=True)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _distribution_ex_dates(cash_file: Path, notional_file: Path) -> set[pd.Timestamp]:
    from yield_share_anatomy.returns import read_cash_events
    cash = read_cash_events(cash_file)
    notional = pd.read_csv(notional_file, parse_dates=['ex_date'])
    if not {'ex_date', 'kind'}.issubset(notional):
        raise ValueError('Notional events missing ex_date or kind')
    if (notional['kind'] != 'notional').any() or notional['ex_date'].isna().any():
        raise ValueError('Invalid notional events')
    return set(cash['ex_date']).union(set(notional['ex_date']))


def run(purpose_file: Path, yahoo_files: list[Path] | Path, cash_file: Path,
        notional_file: Path, outdir: Path) -> dict:
    primary = _load(purpose_file, {'date', 'nav', 'price'}, 'Purpose')
    references = [yahoo_files] if isinstance(yahoo_files, Path) else list(yahoo_files)
    if not references:
        raise ValueError('At least one Yahoo reference CSV is required')
    chunks = []
    for path in references:
        chunk = _load(path, {'date', 'open', 'high', 'low', 'close', 'volume'}, 'Yahoo')
        chunk['reference_file'] = path.as_posix()
        chunks.append(chunk)
    secondary = pd.concat(chunks, ignore_index=True).sort_values('date').reset_index(drop=True)
    if secondary['date'].duplicated().any():
        raise ValueError('Duplicate Yahoo dates across reference CSVs')
    ledger = reconcile_market_prices(primary, secondary,
                                     _distribution_ex_dates(cash_file, notional_file))
    outdir.mkdir(parents=True, exist_ok=True)
    ledger.loc[ledger.flagged].to_csv(
        outdir / 'market_price_source_discrepancies.csv', index=False)
    ledger.to_csv(outdir / 'market_price_reconciled_daily.csv', index=False)
    counts = ledger['resolution'].value_counts().to_dict()
    labels = sorted(secondary['source'].dropna().unique().tolist()) if 'source' in secondary else []
    dates = (sorted(secondary['retrieved_at_utc'].dropna().astype(str).unique().tolist())
             if 'retrieved_at_utc' in secondary else [])
    status = {
        'status': 'blocked' if counts.get('blocked_ex_date', 0) else 'diagnostic_only',
        'resolution_counts': counts, 'premium_threshold_pct': PREMIUM_THRESHOLD_PCT,
        'yahoo_validation': 'Close/Open inside OHLC +/-0.01; volume >0; abs(Close/NAV - 1) <=10%',
        'secondary_source_labels': labels, 'secondary_retrieval_dates': dates,
        'input_sha256': {p.as_posix(): _hash(p) for p in
                         (purpose_file, *references, cash_file, notional_file)},
        'warning': 'Derived market-price diagnostic only; does not modify raw CSV or NAV returns.',
    }
    (outdir / 'market_price_reconciliation_status.json').write_text(
        json.dumps(status, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return status


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--purpose', type=Path,
                    default=SNAPSHOT_DIR / 'ytsl_purpose_daily.csv')
    ap.add_argument('--yahoo', type=Path, action='append',
                    help='Yahoo OHLCV snapshot, repeatable; default uses two dated reference files')
    ap.add_argument('--events', type=Path,
                    default=CASH_EVENTS)
    ap.add_argument('--notional', type=Path,
                    default=NOTIONAL_EVENTS)
    ap.add_argument('--out', type=Path,
                    default=OUTPUT_DIR / 'market_price_quality')
    args = ap.parse_args()
    try:
        references = args.yahoo if args.yahoo is not None else [
            Path('data/reference/ytsl_yahoo_close_2022_2023.csv'),
            Path('data/reference/ytsl_yahoo_close_2026.csv'),
        ]
        status = run(args.purpose, references, args.events, args.notional, args.out)
    except (ValueError, OSError) as exc:
        ap.exit(1, f'Market-price QC failed: {exc}\n')
    print(json.dumps(status, indent=2, ensure_ascii=False))
    if status['status'] == 'blocked':
        ap.exit(2, 'Unresolved distribution ex-date: do not exclude or forward-fill.\n')


if __name__ == '__main__':
    main()
