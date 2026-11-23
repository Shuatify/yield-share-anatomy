#!/usr/bin/env python3
"""Issuer YTSL NAV total-return reconciliation, separate from TSLA comparison.

Compute on the ETF's own complete NAV calendar. Market-price anomalies,
missing TSLA sessions and FX should not remove days from this series.
This calculation remains provisional until cash event history is verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

OFFICIAL_AS_OF = pd.Timestamp('2026-10-30')
OFFICIAL_SOURCE = 'https://www.purposeinvest.com/funds/tesla-yield-shares-purpose-etf/performance'
# Purpose ETF series performance snapshot, as at 2026-10-30, percentages.
OFFICIAL_RETURNS = {
    '1M': 14.99, '3M': 35.38, '6M': 7.63, 'YTD': -9.26,
    '1Y': -9.55, '3Y_annualized': 25.32,
    'since_inception_annualized': 24.55,
}


def load_nav(path: Path) -> pd.DataFrame:
    """Load NAV columns only, leaving source bytes unchanged."""
    daily = pd.read_csv(path)
    if not {'date', 'nav'}.issubset(daily.columns):
        raise ValueError('NAV CSV requires date and nav columns')
    daily = daily[['date', 'nav']].copy()
    daily['date'] = pd.to_datetime(daily['date'], errors='coerce')
    daily['nav'] = pd.to_numeric(daily['nav'], errors='coerce')
    if daily['date'].isna().any() or daily['date'].duplicated().any():
        raise ValueError('NAV has invalid or duplicate dates')
    if daily['nav'].isna().any() or daily['nav'].le(0).any() or not daily['nav'].map(math.isfinite).all():
        raise ValueError('NAV contains missing/nonpositive values; investigate before running')
    return daily.sort_values('date').reset_index(drop=True)


def compute_nav_index(nav: pd.DataFrame, cash_events: pd.DataFrame) -> pd.DataFrame:
    """Reinvest cash distributions at exact ex-date closing NAV.

    Daily factor is (NAV_t + cash_t)/NAV_(t-1). Noncash notional events
    must not be passed here; if NAV is missing for an ex-date, fail rather
    than silently moving the cash event to another comparison day.
    """
    if nav.empty or nav['date'].duplicated().any() or not nav['date'].is_monotonic_increasing:
        raise ValueError('NAV must be nonempty, sorted and unique')
    if nav['nav'].isna().any() or nav['nav'].le(0).any() or not nav['nav'].map(math.isfinite).all():
        raise ValueError('NAV values must be positive and finite')
    events = cash_events.copy()
    if not {'ex_date', 'amount_cad', 'kind'}.issubset(events.columns):
        raise ValueError('Missing required cash event columns')
    events['ex_date'] = pd.to_datetime(events['ex_date'], errors='coerce')
    events['amount_cad'] = pd.to_numeric(events['amount_cad'], errors='coerce')
    if events['ex_date'].isna().any() or events['amount_cad'].isna().any():
        raise ValueError('Invalid cash event date or amount')
    if (events['kind'] != 'cash').any() or events['amount_cad'].le(0).any():
        raise ValueError('Only strictly positive cash events are allowed in NAV DRIP')
    if events['ex_date'].duplicated().any():
        raise ValueError('Duplicate ex-dates: reconcile events before calculating')

    first, last = nav['date'].iloc[0], nav['date'].iloc[-1]
    relevant = events.loc[(events['ex_date'] > first) & (events['ex_date'] <= last)]
    missing = relevant.loc[~relevant['ex_date'].isin(nav['date']), 'ex_date']
    if not missing.empty:
        raise ValueError(f'Cash ex-dates without NAV observations: {missing.dt.strftime("%Y-%m-%d").tolist()}')
    out = nav[['date', 'nav']].copy()
    entitlements = relevant.set_index('ex_date')['amount_cad']
    out['cash_per_unit'] = out['date'].map(entitlements).fillna(0.0)
    factors = (out['nav'] + out['cash_per_unit']) / out['nav'].shift(1)
    factors.iloc[0] = 1.0  # investor enters at first observation's closing NAV
    out['nav_drip_index'] = factors.cumprod()
    return out


def _anchor_on_or_before(index: pd.DataFrame, target: pd.Timestamp,
                         max_gap_days: int = 7) -> pd.Timestamp:
    eligible = index.loc[index['date'] <= target, 'date']
    if eligible.empty:
        raise ValueError(f'No NAV observation on or before anchor {target.date()}')
    anchor = eligible.iloc[-1]
    if (target - anchor).days > max_gap_days:
        raise ValueError(f'Stale NAV anchor for {target.date()}: {anchor.date()}')
    return anchor


def reconcile(index: pd.DataFrame, *, as_of: pd.Timestamp = OFFICIAL_AS_OF,
              official: dict[str, float] | None = None,
              tolerance_pp: float = 0.20) -> pd.DataFrame:
    """Compare official period returns using explicit month-end anchor dates.

    This anchor/day-count convention is a hypothesis to be checked against
    issuer methodology, NOT an assertion about Purpose's internal calculation.
    """
    if official is None:
        official = OFFICIAL_RETURNS
    if tolerance_pp <= 0:
        raise ValueError('Tolerance must be positive')
    as_of = pd.Timestamp(as_of)
    end = index.loc[index['date'] == as_of]
    if len(end) != 1:
        raise ValueError(f'Exact as-of NAV not found: {as_of.date()}')
    if index['date'].duplicated().any() or not index['date'].is_monotonic_increasing:
        raise ValueError('Index must be sorted and unique')
    if index['nav_drip_index'].isna().any() or index['nav_drip_index'].le(0).any():
        raise ValueError('Invalid NAV total return index')
    end_index = float(end['nav_drip_index'].iloc[0])
    months = {'1M': 1, '3M': 3, '6M': 6, '1Y': 12, '3Y_annualized': 36}
    anchors = {name: as_of + pd.offsets.MonthEnd(0) - pd.offsets.MonthEnd(n)
               for name, n in months.items()}
    anchors['YTD'] = pd.Timestamp(as_of.year - 1, 12, 31)
    anchors['since_inception_annualized'] = index['date'].iloc[0]
    rows = []
    for period, published_pct in official.items():
        target = anchors[period]
        start = _anchor_on_or_before(index, target)
        starting = float(index.loc[index['date'] == start, 'nav_drip_index'].iloc[0])
        total = end_index / starting
        if period.endswith('_annualized'):
            days = (as_of - start).days
            if days <= 0:
                raise ValueError('Cannot annualize zero-length period')
            calculated_pct = (total ** (365.25 / days) - 1) * 100
        else:
            calculated_pct = (total - 1) * 100
        delta_pp = calculated_pct - published_pct
        rows.append({
            'period': period, 'target_start': target.strftime('%Y-%m-%d'),
            'actual_start': start.strftime('%Y-%m-%d'),
            'end': as_of.strftime('%Y-%m-%d'),
            'official_pct': published_pct, 'calculated_pct': calculated_pct,
            'difference_pp': delta_pp,
            'within_tolerance': abs(delta_pp) <= tolerance_pp,
        })
    return pd.DataFrame(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(nav_file: Path, cash_file: Path, out: Path,
        tolerance_pp: float = 0.20) -> dict:
    # Reuse Phase 1's cash event validation. No duplicate event parser.
    from yield_share_phase1_returns import read_cash_events

    nav = load_nav(nav_file)
    events = read_cash_events(cash_file)
    index = compute_nav_index(nav, events)
    comparison = reconcile(index, tolerance_pp=tolerance_pp)
    out.mkdir(parents=True, exist_ok=True)
    index.to_csv(out / 'nav_only_daily_index.csv', index=False)
    comparison.to_csv(out / 'nav_reconciliation.csv', index=False,
                      float_format='%.8f')
    summary = {
        'status': 'pass' if comparison['within_tolerance'].all() else 'needs_investigation',
        'research_status': 'provisional_distribution_seed',
        'issuer_source': OFFICIAL_SOURCE,
        'issuer_as_of': OFFICIAL_AS_OF.strftime('%Y-%m-%d'),
        'nav_observations': len(nav),
        'cash_events_in_nav_range': int(((events['ex_date'] > nav['date'].iloc[0]) &
                                        (events['ex_date'] <= nav['date'].iloc[-1])).sum()),
        'nav_sha256': sha256(nav_file),
        'cash_events_sha256': sha256(cash_file),
        'tolerance_pp': tolerance_pp,
        'reconciliation_rule': 'exact as-of; prior calendar month-ends mapped backward by <=7 days',
        'reinvestment_rule': 'cash entitlement on exact ex-date; reinvest at closing NAV; notional excluded',
        'annualization_day_count': 365.25,
        'unverified_items': [
            'cash distribution seed not fully issuer crosschecked',
            'issuer exact anchor date and annualization convention',
            'notional NAV/unit consolidation handling',
        ],
    }
    (out / 'nav_reconciliation_status.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nav', type=Path,
                        default=Path('yield_share_phase0_data/ytsl_purpose_daily.csv'))
    parser.add_argument('--events', type=Path,
                        default=Path('data/ytsl_cash_distributions.csv'))
    parser.add_argument('--out', type=Path,
                        default=Path('yield_share_phase1_results/nav_reconciliation'))
    parser.add_argument('--tolerance-pp', type=float, default=0.20)
    args = parser.parse_args()
    try:
        summary = run(args.nav, args.events, args.out, args.tolerance_pp)
    except (ValueError, OSError) as exc:
        parser.exit(1, f'NAV reconciliation failed: {exc}\n')
    print(json.dumps(summary, indent=2))
    if summary['status'] != 'pass':
        parser.exit(2, 'Issuer NAV reconciliation needs investigation; see CSV.\n')


if __name__ == '__main__':
    main()
