"""Math and input tests for Phase 1. Only synthetic prices; real cash seed is public source facts."""
from pathlib import Path
import pandas as pd
import pytest
from yield_share_anatomy.returns import (
 read_cash_events, annual_distribution_audit, build_common_calendar,
 map_events_to_common_dates, compute_return_paths, regimes_from_daily,
 ResearchDataError,
)
ROOT=Path(__file__).resolve().parents[1]


def sample_calendar():
    dates=pd.to_datetime(['2026-01-05','2026-01-06','2026-01-08','2026-01-09'])
    return pd.DataFrame({'date':dates,'nav':[10,9,9.5,10],
       'price':[10,9,9.5,10], 'close_usd':[100,95,97,100],
       'adj_close_usd':[100,95,97,100], 'usd_cad':[1,1,1,1],
       'fx_age_days':[0,0,0,0], 'tsla_cad':[100,95,97,100]})


def sample_events():
    return pd.DataFrame({'ex_date':pd.to_datetime(['2026-01-06']),
       'pay_date':pd.to_datetime(['2026-01-08']),'amount_cad':[1.0],
       'kind':['cash'],'status':['confirmed'],'source_url':['test-only']})


def test_cash_vs_reinvest_return_exact_math():
    df=sample_calendar()
    mapped,meta=map_events_to_common_dates(sample_events(),df['date'])
    out=compute_return_paths(df,mapped,initial=100.0)
    # 10 initial shares, $1/share distribution; Jan 6 ex close=9
    assert out.loc[1,'ytsl_nav_price_return_pct']==pytest.approx(-10)
    assert out.loc[1,'ytsl_nav_cash_total_return_pct']==pytest.approx(0)
    assert out.loc[1,'ytsl_nav_drip_total_return_pct']==pytest.approx(0)
    assert out.loc[3,'ytsl_nav_cash_entitled_cad']==pytest.approx(10)
    assert out.loc[3,'ytsl_nav_cash_total_return_pct']==pytest.approx(10)
    assert out.loc[3,'ytsl_nav_drip_total_return_pct']==pytest.approx(100*(10/9-1), rel=1e-12)
    assert out.loc[3,'tsla_cad_total_return_pct']==pytest.approx(0)


def test_event_noncommon_market_day_shift_is_explicit():
    df=sample_calendar()
    event=sample_events()
    event.loc[0,'ex_date']=pd.Timestamp('2026-01-07')
    mapped,meta=map_events_to_common_dates(event,df['date'])
    assert meta['shifted_event_count']==1
    assert str(mapped.loc[0,'applied_date'].date())=='2026-01-08'
    assert meta['shifted_events'][0]['delay_days']==1


def test_bad_event_gt5days_refused():
    dates=pd.to_datetime(['2026-01-01','2026-01-10','2026-01-20']).to_series().reset_index(drop=True)
    event=sample_events()
    event.loc[0,'ex_date']=pd.Timestamp('2026-01-02')
    with pytest.raises(ResearchDataError):
        map_events_to_common_dates(event,dates)


def test_notional_2023_not_counted_as_cash():
    e=read_cash_events(ROOT/'data/events/ytsl_cash_distributions.csv')
    audit=annual_distribution_audit(e,ROOT/'data/events/ytsl_notional_events.csv').set_index('year')
    assert len(e)==47
    assert audit.loc[2023,'monthly_cash_sum']==pytest.approx(3.9969)
    assert audit.loc[2023,'final_notional_events_sum']==pytest.approx(2.07)
    assert audit.loc[2023,'economic_event_sum']==pytest.approx(6.0669)
    assert bool(audit.loc[2023,'needs_review'])
    assert audit.loc[2024,'monthly_cash_sum']==pytest.approx(3.8)
    assert audit.loc[2025,'monthly_cash_sum']==pytest.approx(6.85)
    assert audit.loc[2025,'final_notional_events_sum']==pytest.approx(2.318)


def test_bad_cash_type_rejected(tmp_path):
    p=tmp_path/'bad.csv'
    p.write_text('ex_date,pay_date,amount_cad,kind,status,source_url\n'
                 '2025-12-30,2026-01-05,2.318,notional,final,local\n')
    with pytest.raises(ResearchDataError):read_cash_events(p)


def test_common_calendar_drops_null_without_fill():
    a=sample_calendar()
    additional = a.iloc[[-1]].copy()
    additional['date'] = pd.Timestamp('2026-01-12')
    a = pd.concat([a, additional], ignore_index=True)
    a.loc[1,'adj_close_usd']=float('nan')
    a.loc[2,'price']=float('nan')
    selected,qc=build_common_calendar(a)
    assert len(selected)==3
    assert qc['excluded_rows']==2


def test_regime_empty_for_short_history():
    out=compute_return_paths(sample_calendar(),map_events_to_common_dates(
          sample_events(),sample_calendar()['date'])[0])
    monthly,summary=regimes_from_daily(out)
    assert monthly.empty
    assert summary.empty
