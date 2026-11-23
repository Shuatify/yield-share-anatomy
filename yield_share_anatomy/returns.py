#!/usr/bin/env python3
"""Phase 1: reproducible exploratory TSLA vs YTSL return series.

Consumes actual Phase 0 CSV downloads (or explicitly labeled synthetic fixtures).
Outputs separate NAV/market-price, cash-entitlement and reinvestment return series.

IMPORTANT:
- Distribution seed is secondary-source transcription, not yet fully official-verified.
- Notional events are excluded from cash income and share-reinvestment arithmetic.
- For common-calendar comparison, events on a non-common session are applied at
  the next common close; the shift is reported, never hidden.
- USD/CAD uses BoC daily indicative FX, not executable end-of-day exchange rates.
- This is descriptive research, not a simulation of an investable hedged benchmark.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .paths import SNAPSHOT_DIR, CASH_EVENTS, NOTIONAL_EVENTS, OUTPUT_DIR

import pandas as pd

DATA_FILES = {
    'ytsl': 'ytsl_purpose_daily.csv',
    'tsla': 'tsla_yahoo_daily.csv',
    'fx': 'usdcad_boc_daily.csv',
}

INITIAL_CAPITAL_CAD = 10000.0
REGIME_THRESHOLD = 0.05
MAX_MARKET_PREMIUM_PCT = 10.0


class ResearchDataError(ValueError):
    pass


def read_observations(directory: Path) -> pd.DataFrame:
    required = {
        'ytsl': ['date', 'nav', 'price'],
        'tsla': ['date', 'close_usd', 'adj_close_usd'],
        'fx': ['date', 'usd_cad'],
    }
    frames = {}
    for name, filename in DATA_FILES.items():
        path = directory / filename
        if not path.exists():
            raise ResearchDataError(f'Missing {path}. Run Phase 0 first.')
        frame = pd.read_csv(path, parse_dates=['date'])
        missing = sorted(set(required[name]) - set(frame.columns))
        if missing:
            raise ResearchDataError(f'{filename} missing {missing}')
        frame = frame[required[name]].copy().sort_values('date')
        if frame['date'].duplicated().any():
            raise ResearchDataError(f'{filename}: duplicate dates')
        for col in required[name][1:]:
            frame[col] = pd.to_numeric(frame[col], errors='coerce')
        frames[name] = frame

    ytsl = frames['ytsl']
    tsla = frames['tsla']
    fx = frames['fx'].rename(columns={'date':'fx_date'})
    aligned = ytsl.merge(tsla, how='left', on='date', validate='one_to_one')
    aligned = pd.merge_asof(aligned.sort_values('date'), fx.sort_values('fx_date'),
                            left_on='date', right_on='fx_date', direction='backward',
                            tolerance=pd.Timedelta(days=5))
    aligned['fx_age_days'] = (aligned['date'] - aligned['fx_date']).dt.days
    aligned['tsla_cad'] = aligned['adj_close_usd'] * aligned['usd_cad']
    return aligned


def read_cash_events(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ResearchDataError(f'Missing distribution file: {path}')
    events = pd.read_csv(path)
    needed = {'ex_date', 'pay_date', 'amount_cad', 'kind', 'status', 'source_url'}
    if not needed.issubset(events):
        raise ResearchDataError(f'Distribution CSV missing {needed - set(events)}')
    events['ex_date'] = pd.to_datetime(events['ex_date'], errors='coerce')
    events['pay_date'] = pd.to_datetime(events['pay_date'], errors='coerce')
    events['amount_cad'] = pd.to_numeric(events['amount_cad'], errors='coerce')
    if events[['ex_date','pay_date','amount_cad']].isna().any().any():
        raise ResearchDataError('Invalid distribution event date/amount')
    if ((events['amount_cad'] <= 0) | (events['kind'] != 'cash')).any():
        raise ResearchDataError('Cash events must be positive and type cash; notional must be separate')
    if events['ex_date'].duplicated().any():
        raise ResearchDataError('Duplicate distribution ex-dates')
    if (events['pay_date'] < events['ex_date']).any():
        raise ResearchDataError('Payment date before ex-date')
    return events.sort_values('ex_date').reset_index(drop=True)


def audit_market_prices(aligned: pd.DataFrame, max_premium_pct: float = MAX_MARKET_PREMIUM_PCT) -> pd.DataFrame:
    """Flag unusual YTSL market closes vs same-day NAV; preserve raw observations.

    A flag is NOT proof of a bad trade or incorrect issuer data. It excludes
    suspect rows from exploratory market-price comparison until independently
    verified. Always retain the original file for later source reconciliation.
    """
    if not 0 < max_premium_pct <= 100:
        raise ResearchDataError('Market premium threshold must be between 0 and 100 percent')
    raw = aligned[['date','nav','price']].copy()
    raw['market_premium_pct'] = 100.0 * (raw['price'] / raw['nav'] - 1.0)
    bad = raw['nav'].gt(0) & raw['price'].gt(0) & raw['market_premium_pct'].abs().gt(max_premium_pct)
    raw = raw.loc[bad].copy()
    raw['reason'] = f'abs(market price / NAV - 1) > {max_premium_pct:g}%'
    return raw.sort_values('date').reset_index(drop=True)


def build_common_calendar(aligned: pd.DataFrame, max_premium_pct: float = MAX_MARKET_PREMIUM_PCT) -> tuple[pd.DataFrame, dict]:
    columns = ['nav', 'price', 'adj_close_usd', 'usd_cad', 'tsla_cad']
    if aligned.empty:
        raise ResearchDataError('No observations')
    anomalies = audit_market_prices(aligned, max_premium_pct)
    valid = aligned[columns].notna().all(axis=1)
    valid &= aligned[columns].gt(0).all(axis=1)
    valid &= aligned['fx_age_days'].le(5)
    # Do not use suspect YTSL market prices as the first-day denominator, nor
    # include them as daily extremes. Raw rows remain unchanged on disk.
    valid &= ~(100*(aligned['price']/aligned['nav']-1)).abs().gt(max_premium_pct)
    selected = aligned.loc[valid].copy().reset_index(drop=True)
    if len(selected) < 3:
        raise ResearchDataError('Insufficient common valid trading days')
    diagnostics = {
        'ytsl_dates':len(aligned),
        'common_valid_dates':len(selected),
        'excluded_rows':len(aligned)-len(selected),
        'market_nav_premium_threshold_pct':max_premium_pct,
        'market_price_anomaly_count':len(anomalies),
        'market_price_anomaly_dates':[str(t.date()) for t in anomalies['date']],
        'missing_tsla_on_ytsl_dates':int(aligned['adj_close_usd'].isna().sum()),
        'missing_ytsl_market_price':int(aligned['price'].isna().sum()),
        'fx_carryforward_days':int((selected['fx_age_days']>0).sum()),
        'max_abs_nav_daily_pct':round(float(selected['nav'].pct_change().abs().max()*100),3),
        'max_abs_market_daily_pct':round(float(selected['price'].pct_change().abs().max()*100),3),
    }
    return selected, diagnostics


def map_events_to_common_dates(events: pd.DataFrame, dates: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Apply an entitlement no earlier than its ex-date, at next common close.

    Where ex-date is after initial investment date and up to latest date, map it.
    A missing common close for >5 calendar days is a hard failure.
    """
    start, end = dates.iloc[0], dates.iloc[-1]
    valid_events = events.loc[(events['ex_date'] > start) & (events['ex_date'] <= end)].copy()
    skipped_at_start = int((events['ex_date'] <= start).sum())
    shifted = []
    applied = []
    for _, e in valid_events.iterrows():
        idx = dates.searchsorted(e['ex_date'], side='left')
        if idx >= len(dates):
            raise ResearchDataError(f"Cannot apply event {e['ex_date'].date()}: no later market date")
        at = dates.iloc[idx]
        delay = int((at - e['ex_date']).days)
        if delay > 5:
            raise ResearchDataError(f"Event {e['ex_date'].date()} delayed {delay} days; data gap")
        row = e.to_dict()
        row['applied_date'] = at
        row['shift_calendar_days'] = delay
        applied.append(row)
        if delay: shifted.append({'ex_date':str(e['ex_date'].date()),
                                  'applied_date':str(at.date()), 'delay_days':delay})
    if applied:
        mapping = pd.DataFrame(applied)
    else:
        mapping = pd.DataFrame(columns=[*events.columns, 'applied_date', 'shift_calendar_days'])
    return mapping, {'applied_cash_events':len(mapping),
                     'excluded_events_at_or_before_start':skipped_at_start,
                     'shifted_event_count':len(shifted), 'shifted_events':shifted}


def compute_return_paths(calendar: pd.DataFrame, mapped: pd.DataFrame,
                         initial: float = INITIAL_CAPITAL_CAD) -> pd.DataFrame:
    if initial <= 0:
        raise ResearchDataError('Initial capital must be positive')
    out = calendar[['date','nav','price','close_usd','adj_close_usd','usd_cad','fx_age_days','tsla_cad']].copy()
    # Entitlement value accrued on ex-date / mapped common comparison date;
    # NOT a claim that cash is credited to brokerage on that day.
    day_amount = mapped.groupby('applied_date')['amount_cad'].sum() if len(mapped) else pd.Series(dtype=float)
    out['cash_entitlement_per_unit'] = out['date'].map(day_amount).fillna(0.0)
    out['latest_monthly_cash_per_unit'] = out['cash_entitlement_per_unit'].where(
        out['cash_entitlement_per_unit'] > 0).ffill()
    out['indicated_nav_yield_pct'] = 100*12*out['latest_monthly_cash_per_unit']/out['nav']
    out['indicated_market_yield_pct'] = 100*12*out['latest_monthly_cash_per_unit']/out['price']
    out['tsla_cad_total_return_pct'] = (out['tsla_cad']/out['tsla_cad'].iloc[0]-1)*100
    for label, price_col in (('nav','nav'), ('market','price')):
        prices=out[price_col].astype(float).tolist()
        cash_event=out['cash_entitlement_per_unit'].astype(float).tolist()
        base_units=initial/prices[0]
        reinvest_units=base_units
        total_cash_per_original_unit=0.0
        cash_received_entitlement=0.0
        no_reinvest_values=[]
        drip_values=[]
        cash_cumulative=[]
        for p, amount in zip(prices, cash_event):
            # Cash entitlement based on original units for no-reinvestment path.
            cash_received_entitlement += base_units * amount
            total_cash_per_original_unit += amount
            # Reinvest the distribution at post-ex-date closing price.
            reinvest_units *= (1.0 + amount/p)
            no_reinvest_values.append(base_units*p+cash_received_entitlement)
            drip_values.append(reinvest_units*p)
            cash_cumulative.append(cash_received_entitlement)
        out[f'ytsl_{label}_price_return_pct'] = (out[price_col]/out[price_col].iloc[0]-1)*100
        out[f'ytsl_{label}_cash_total_return_pct'] = (pd.Series(no_reinvest_values,index=out.index)/initial-1)*100
        out[f'ytsl_{label}_drip_total_return_pct'] = (pd.Series(drip_values,index=out.index)/initial-1)*100
        out[f'ytsl_{label}_cash_entitled_cad'] = cash_cumulative
        out[f'ytsl_{label}_drip_units'] = (pd.Series(drip_values,index=out.index)/out[price_col]).values
    out['nav_relative_gap_pp'] = out['ytsl_nav_drip_total_return_pct'] - out['tsla_cad_total_return_pct']
    out['market_relative_gap_pp'] = out['ytsl_market_drip_total_return_pct'] - out['tsla_cad_total_return_pct']
    return out


def regimes_from_daily(daily: pd.DataFrame, threshold: float = REGIME_THRESHOLD) -> tuple[pd.DataFrame,pd.DataFrame]:
    if threshold <= 0:
        raise ResearchDataError('Regime threshold must be positive')
    monthly = daily.groupby(daily['date'].dt.to_period('M'), sort=True).tail(1).copy()
    monthly['month'] = monthly['date'].dt.strftime('%Y-%m')
    # Historical calendar-month comparisons need previous month's close.
    monthly['tsla_monthly_pct'] = 100 * (monthly['tsla_cad'] / monthly['tsla_cad'].shift(1) - 1)
    monthly['ytsl_nav_drip_monthly_pct'] = 100 * (
        (1+monthly['ytsl_nav_drip_total_return_pct']/100)/
        (1+monthly['ytsl_nav_drip_total_return_pct'].shift(1)/100) - 1)
    monthly['ytsl_market_drip_monthly_pct'] = 100 * (
        (1+monthly['ytsl_market_drip_total_return_pct']/100)/
        (1+monthly['ytsl_market_drip_total_return_pct'].shift(1)/100) - 1)
    monthly = monthly.iloc[1:-1].copy() # exclude partial first and last months conservatively
    if monthly.empty:
        return monthly, pd.DataFrame(columns=['regime','months','avg_tsla_pct','avg_ytsl_nav_pct',
                                             'avg_gap_pp','median_gap_pp','ytsl_win_rate_pct'])
    monthly['gap_pp'] = monthly['ytsl_nav_drip_monthly_pct'] - monthly['tsla_monthly_pct']
    monthly['regime'] = 'Sideways'
    monthly.loc[monthly['tsla_monthly_pct']>100*threshold,'regime'] = 'Up'
    monthly.loc[monthly['tsla_monthly_pct']< -100*threshold,'regime'] = 'Down'
    stats=[]
    for name in ['Up','Sideways','Down']:
        group = monthly.loc[monthly['regime']==name]
        stats.append({'regime':name,'months':len(group),
                      'avg_tsla_pct':float(group['tsla_monthly_pct'].mean()) if len(group) else None,
                      'avg_ytsl_nav_pct':float(group['ytsl_nav_drip_monthly_pct'].mean()) if len(group) else None,
                      'avg_gap_pp':float(group['gap_pp'].mean()) if len(group) else None,
                      'median_gap_pp':float(group['gap_pp'].median()) if len(group) else None,
                      'ytsl_win_rate_pct':float((group['gap_pp']>0).mean()*100) if len(group) else None})
    return monthly[['month','date','regime','tsla_monthly_pct','ytsl_nav_drip_monthly_pct',
                    'ytsl_market_drip_monthly_pct','gap_pp']], pd.DataFrame(stats)


def annual_distribution_audit(cash: pd.DataFrame, notional_file: Path) -> pd.DataFrame:
    if not notional_file.exists():
        raise ResearchDataError(f'Missing notional event file: {notional_file}')
    n = pd.read_csv(notional_file, parse_dates=['ex_date'])
    if not {'ex_date','amount_cad','kind','status'}.issubset(n):
        raise ResearchDataError('Notional CSV missing columns')
    if (n['kind'] != 'notional').any() or (n['status'] != 'final').any():
        raise ResearchDataError('Notional event data must be final and notional')
    cash_years = cash.groupby(cash.ex_date.dt.year)['amount_cad'].sum()
    non_years = n.groupby(n.ex_date.dt.year)['amount_cad'].sum()
    official_summary = {2022:(.3067,0), 2023:(6.0669,0), 2024:(3.8,0), 2025:(6.85,2.318)}
    rows=[]
    for yr in sorted(set(cash_years.index).union(non_years.index)):
        cash_amt=round(float(cash_years.get(yr,0)),4)
        non_amt=round(float(non_years.get(yr,0)),4)
        posted=official_summary.get(yr)
        rows.append({'year':int(yr),'monthly_cash_sum':cash_amt,'final_notional_events_sum':non_amt,
                     'economic_event_sum':round(cash_amt+non_amt,4),
                     'official_tax_factors_cash_label':posted[0] if posted else None,
                     'official_tax_factors_notional_label':posted[1] if posted else None,
                     'needs_review':bool(yr==2023)})
    return pd.DataFrame(rows)


def run(data_dir:Path, cash_events:Path, notional_events:Path, out:Path, *,
        allow_synthetic:bool=False, market_premium_threshold_pct:float=MAX_MARKET_PREMIUM_PCT) -> dict:
    statusfile=data_dir/'fetch_status.json'
    if not statusfile.exists():
        raise ResearchDataError('Missing Phase 0 fetch_status.json; run Phase 0 before Phase 1')
    fetch_status=json.loads(statusfile.read_text())
    if fetch_status.get('status')!='ok':
        raise ResearchDataError('Phase 0 fetch status is not ok')
    synthetic=(fetch_status.get('data_type')=='SYNTHETIC_TEST_FIXTURE')
    if synthetic and not allow_synthetic:
        raise ResearchDataError('Refusing synthetic data without --allow-synthetic (test only)')
    aligned=read_observations(data_dir)
    anomalies=audit_market_prices(aligned, market_premium_threshold_pct)
    valid,qc=build_common_calendar(aligned, market_premium_threshold_pct)
    cash=read_cash_events(cash_events)
    mapped,ev_status=map_events_to_common_dates(cash, valid['date'])
    daily=compute_return_paths(valid,mapped)
    monthly,regimes=regimes_from_daily(daily)
    audit=annual_distribution_audit(cash,notional_events)
    out.mkdir(parents=True,exist_ok=True)
    anomalies.to_csv(out/'market_price_anomalies.csv', index=False)
    daily.to_csv(out/'daily_return_index.csv',index=False)
    monthly.to_csv(out/'monthly_regimes.csv',index=False)
    regimes.to_csv(out/'regime_summary.csv',index=False)
    mapped.to_csv(out/'cash_events_applied.csv',index=False)
    audit.to_csv(out/'annual_distribution_audit.csv',index=False)
    final=daily.iloc[-1]
    report={'status':'ok','data_type':fetch_status.get('data_type'),
            'start':str(daily.date.iloc[0].date()),'end':str(daily.date.iloc[-1].date()),
            'common_days':len(daily), 'qc':qc,'event_mapping':ev_status,
            'total_return_at_end_pct':{
               'tsla_cad':round(float(final.tsla_cad_total_return_pct),4),
               'ytsl_nav_drip':round(float(final.ytsl_nav_drip_total_return_pct),4),
               'ytsl_market_drip':round(float(final.ytsl_market_drip_total_return_pct),4),
               'ytsl_nav_no_reinvest':round(float(final.ytsl_nav_cash_total_return_pct),4),
               'ytsl_market_no_reinvest':round(float(final.ytsl_market_cash_total_return_pct),4)},
            'methodology':{'cash_event_time':'entitlement on ex-date, mapped to next common closing session if necessary',
                'notional':'Excluded from cash and unit reinvestment; separately audited',
                'market_calendar':'YTSL/TSLA common valid dates only',
                'fx':'Bank of Canada reference USD/CAD, carry-forward <=5 calendar days',
                'reinvestment':'At event-day closing NAV/market price',
                'monthly_regimes':'TSLA CAD monthly return >+5%, within +/-5%, <-5%; first and last incomplete month excluded',
                'data_validation':'Distribution events are secondary-source seed pending official line-by-line verification; do not publish as final verified research.',
                'market_price_quality':'Market prices with |premium to NAV| over specified threshold excluded from ALL series on common calendar, raw data preserved; flagged rows not independently confirmed errors. Results provisional.'}}
    (out/'analysis_status.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=SNAPSHOT_DIR)
    parser.add_argument('--events',type=Path,default=CASH_EVENTS)
    parser.add_argument('--notional',type=Path,default=NOTIONAL_EVENTS)
    parser.add_argument('--out',type=Path,default=OUTPUT_DIR / 'phase1')
    parser.add_argument('--allow-synthetic',action='store_true',help='Only for smoke testing')
    parser.add_argument('--market-premium-threshold-pct',type=float,default=MAX_MARKET_PREMIUM_PCT, help='Flag/exclude YTSL market prices diverging from same-day NAV by over this percentage (default: 10)')
    args=parser.parse_args()
    try:
        report=run(args.data_dir,args.events,args.notional,args.out,allow_synthetic=args.allow_synthetic, market_premium_threshold_pct=args.market_premium_threshold_pct)
    except (ResearchDataError, ValueError, OSError) as exc:
        parser.exit(1,f'Phase 1 failed: {exc}\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
