"""Market price source anomaly regression tests (synthetic mini-series)."""
from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yield_share_phase1_returns import audit_market_prices, build_common_calendar, ResearchDataError


def fixture():
    return pd.DataFrame({
      'date':pd.to_datetime(['2022-12-20','2022-12-21','2022-12-22','2022-12-23','2023-01-03','2023-01-04','2023-01-05']),
      'nav':[18.17,18.15,16.25,15.61,13.28,14.03,13.65],
      'price':[24.89,18.30,22.33,15.62,15.66,15.66,13.81],
      'adj_close_usd':[100.,100.,100.,100.,100.,100.,100.],
      'usd_cad':[1.3]*7, 'tsla_cad':[130.]*7,
      'fx_age_days':[0]*7,
    })


def test_flags_actual_official_early_pattern():
    anomaly=audit_market_prices(fixture())
    assert [d.strftime('%Y-%m-%d') for d in anomaly.date]==['2022-12-20','2022-12-22','2023-01-03','2023-01-04']
    assert anomaly.iloc[0].market_premium_pct == pytest.approx((24.89/18.17-1)*100)
    assert anomaly.iloc[1].market_premium_pct == pytest.approx((22.33/16.25-1)*100)


def test_excludes_suspect_first_row_without_modifying_raw():
    raw=fixture()
    selected,qc=build_common_calendar(raw)
    assert selected.date.iloc[0]==pd.Timestamp('2022-12-21')
    assert len(selected)==3
    assert qc['market_price_anomaly_count']==4
    assert qc['excluded_rows']==4
    assert raw.loc[0,'price']==24.89


def test_threshold_can_be_varied_for_sensitivity():
    df=fixture()
    assert len(audit_market_prices(df, 20))==2
    assert len(audit_market_prices(df, 5))==4
    with pytest.raises(ResearchDataError):audit_market_prices(df, 0)
