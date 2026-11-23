#!/usr/bin/env python3
"""Audit independent TSLA USD/CAD benchmarks against the legacy shared calendar.

No new investment strategy, leverage or currency hedge is modeled.
This tool compares *identical start/end dates* to isolate calendar-method
effects on the existing Phase 1 results. Historical results remain provisional.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from .paths import SNAPSHOT_DIR, CASH_EVENTS, OUTPUT_DIR

import pandas as pd

from yield_share_anatomy.nav import compute_nav_index, load_nav


class CalendarAuditError(ValueError):
    pass


def _clean_dates_and_numbers(frame: pd.DataFrame, value_col: str,
                             source: str) -> pd.DataFrame:
    if not {'date', value_col}.issubset(frame.columns):
        raise CalendarAuditError(f'{source} missing date or {value_col}')
    out = frame[['date', value_col]].copy()
    out['date'] = pd.to_datetime(out['date'], errors='coerce')
    out[value_col] = pd.to_numeric(out[value_col], errors='coerce')
    if out['date'].isna().any() or out['date'].duplicated().any():
        raise CalendarAuditError(f'{source}: invalid or duplicate dates')
    if out[value_col].isna().any() or out[value_col].le(0).any():
        raise CalendarAuditError(f'{source}: missing or nonpositive {value_col}')
    if not out[value_col].map(math.isfinite).all():
        raise CalendarAuditError(f'{source}: nonfinite {value_col}')
    return out.sort_values('date').reset_index(drop=True)


def build_tsla_fx_reference(tsla: pd.DataFrame, fx: pd.DataFrame, *,
                            max_fx_age_days: int = 5) -> pd.DataFrame:
    """Only actual US TSLA trading sessions; BoC FX carried backward <=5 days.

    No TSLA close is carried forward to a US-market holiday. The currency rate
    is a BoC reference series, not a hedged or executable closing-rate proxy.
    """
    if max_fx_age_days < 0:
        raise CalendarAuditError('max_fx_age_days must be nonnegative')
    us = _clean_dates_and_numbers(tsla, 'adj_close_usd', 'TSLA')
    cad = _clean_dates_and_numbers(fx, 'usd_cad', 'BoC')
    cad = cad.rename(columns={'date': 'fx_date'})
    out = pd.merge_asof(us, cad, left_on='date', right_on='fx_date',
                        direction='backward',
                        tolerance=pd.Timedelta(days=max_fx_age_days))
    out['fx_age_days'] = (out['date'] - out['fx_date']).dt.days
    out['tsla_cad_reference'] = out['adj_close_usd'] * out['usd_cad']
    return out


def align_independent_returns(nav_index: pd.DataFrame, tsla_fx: pd.DataFrame,
                              start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Full NAV DRIP is computed first; only then select exact shared dates."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start >= end:
        raise CalendarAuditError('Start must precede end')
    required = {'date', 'nav_drip_index'}
    if not required.issubset(nav_index.columns):
        raise CalendarAuditError('Missing NAV DRIP index columns')
    if nav_index['date'].duplicated().any():
        raise CalendarAuditError('Duplicate NAV dates')
    reference = tsla_fx.dropna(subset=['usd_cad', 'tsla_cad_reference'])
    both = nav_index[['date', 'nav_drip_index']].merge(
        reference[['date', 'adj_close_usd', 'usd_cad', 'fx_date',
                   'fx_age_days', 'tsla_cad_reference']],
        on='date', how='inner', validate='one_to_one')
    both = both.loc[both['date'].between(start, end)].sort_values('date').reset_index(drop=True)
    if both.empty or both['date'].iloc[0] != start or both['date'].iloc[-1] != end:
        raise CalendarAuditError('Exact legacy start/end must both be in independent benchmark dates')
    for field in ['nav_drip_index', 'adj_close_usd', 'tsla_cad_reference']:
        base = float(both[field].iloc[0])
        if not math.isfinite(base) or base <= 0:
            raise CalendarAuditError(f'Invalid starting value: {field}')
        both[f'{field}_return_pct'] = 100 * (both[field] / base - 1)
    both['nav_minus_tsla_cad_pp'] = (both['nav_drip_index_return_pct'] -
                                    both['tsla_cad_reference_return_pct'])
    return both


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(data_dir: Path, cash_file: Path, out_dir: Path, *,
        allow_synthetic: bool = False) -> dict:
    from yield_share_anatomy.returns import (
        build_common_calendar, compute_return_paths, map_events_to_common_dates,
        read_cash_events, read_observations,
    )

    status_path = data_dir / 'fetch_status.json'
    status = json.loads(status_path.read_text(encoding='utf-8'))
    if status.get('status') != 'ok':
        raise CalendarAuditError('Phase 0 data status must be ok')
    is_synthetic = status.get('data_type') == 'SYNTHETIC_TEST_FIXTURE'
    if is_synthetic and not allow_synthetic:
        raise CalendarAuditError('Synthetic data requires --allow-synthetic')

    ytsl_file = data_dir / 'ytsl_purpose_daily.csv'
    tsla_file = data_dir / 'tsla_yahoo_daily.csv'
    fx_file = data_dir / 'usdcad_boc_daily.csv'
    cash = read_cash_events(cash_file)

    # Legacy, for reference only. Do not write to its regular output directory.
    observations = read_observations(data_dir)
    legacy_dates, legacy_qc = build_common_calendar(observations)
    legacy_mapped, legacy_events = map_events_to_common_dates(cash, legacy_dates['date'])
    legacy = compute_return_paths(legacy_dates, legacy_mapped)
    start, end = legacy['date'].iloc[0], legacy['date'].iloc[-1]

    # Independent components (not prefiltered by market-price anomalies).
    nav_index = compute_nav_index(load_nav(ytsl_file), cash)
    tsla_fx = build_tsla_fx_reference(pd.read_csv(tsla_file), pd.read_csv(fx_file))
    common = align_independent_returns(nav_index, tsla_fx, start, end)

    old_nav = float(legacy['ytsl_nav_drip_total_return_pct'].iloc[-1])
    old_tsla = float(legacy['tsla_cad_total_return_pct'].iloc[-1])
    new_nav = float(common['nav_drip_index_return_pct'].iloc[-1])
    new_tsla = float(common['tsla_cad_reference_return_pct'].iloc[-1])
    new_usd = float(common['adj_close_usd_return_pct'].iloc[-1])

    legacy_set = set(legacy['date'])
    cash_in_window = cash.loc[cash['ex_date'].gt(start) & cash['ex_date'].le(end)]
    cash_not_on_legacy_days = cash_in_window.loc[~cash_in_window['ex_date'].isin(legacy['date'])]

    bridge = {
        'status': 'diagnostic_only',
        'data_type': status.get('data_type'),
        'legacy_start': str(start.date()), 'legacy_end': str(end.date()),
        'legacy_common_days': len(legacy),
        'nav_trading_days_in_window': int(nav_index['date'].between(start, end).sum()),
        'independent_exact_shared_days': len(common),
        'independent_shared_days_removed_by_legacy_filters': [
            str(d.date()) for d in common['date'] if d not in legacy_set],
        'cash_ex_dates_missing_from_legacy_common_calendar': [
            str(d.date()) for d in cash_not_on_legacy_days['ex_date']],
        'legacy_event_mapping': legacy_events,
        'legacy_calendar_qc': legacy_qc,
        'legacy_nav_drip_pct': old_nav,
        'full_calendar_nav_drip_pct': new_nav,
        'nav_calendar_effect_pp': new_nav - old_nav,
        'legacy_tsla_cad_pct': old_tsla,
        'independent_tsla_cad_pct': new_tsla,
        'tsla_calendar_effect_pp': new_tsla - old_tsla,
        'independent_tsla_usd_pct': new_usd,
        'legacy_nav_minus_tsla_cad_pp': old_nav - old_tsla,
        'independent_nav_minus_tsla_cad_pp': new_nav - new_tsla,
        'total_gap_method_effect_pp': (new_nav - new_tsla) - (old_nav - old_tsla),
        'input_sha256': {p.name: _sha256(p)
                         for p in [ytsl_file, tsla_file, fx_file, cash_file]},
        'methodology': {
            'nav': 'Full YTSL NAV daily index before shared-date alignment; cash at exact ex-date',
            'tsla_usd': 'Yahoo adjusted close ratio on actual US sessions',
            'tsla_cad': 'Yahoo adjusted close multiplied by BoC USD/CAD reference; FX as-of backward <=5 days',
            'comparison': 'Both methods rebased to identical legacy first and last common dates',
            'limits': 'Not a hedged benchmark, no leverage adjustment, and seed cash events remain provisional',
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    common.to_csv(out_dir / 'independent_benchmark_daily.csv', index=False)
    (out_dir / 'calendar_method_bridge.json').write_text(
        json.dumps(bridge, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return bridge


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=SNAPSHOT_DIR)
    parser.add_argument('--events', type=Path, default=CASH_EVENTS)
    parser.add_argument('--out', type=Path, default=OUTPUT_DIR / 'benchmark_calendar')
    parser.add_argument('--allow-synthetic', action='store_true', help='For offline synthetic smoke tests only')
    args = parser.parse_args()
    try:
        report = run(args.data_dir, args.events, args.out, allow_synthetic=args.allow_synthetic)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Calendar audit failed: {exc}\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
