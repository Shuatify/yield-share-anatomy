"""Synthetic-only checks for the independent TSLA/USD/CAD calendar bridge."""
import pandas as pd
import pytest

from yield_share_anatomy.benchmark import (
    CalendarAuditError, align_independent_returns, build_tsla_fx_reference,
)
from yield_share_anatomy.nav import compute_nav_index
from yield_share_anatomy.returns import compute_return_paths, map_events_to_common_dates


def series(dates, key, values):
    return pd.DataFrame({'date': dates, key: values})


def ref(dates, usd, fx_dates, rates):
    return build_tsla_fx_reference(series(dates, 'adj_close_usd', usd),
                                   series(fx_dates, 'usd_cad', rates))


def test_cad_vs_usd_return_depends_on_fx():
    q = ref(['2026-10-01', '2026-10-02'], [100, 100],
            ['2026-10-01', '2026-10-02'], [1.3, 1.4])
    assert q.tsla_cad_reference.tolist() == pytest.approx([130, 140])
    nav = pd.DataFrame({'date': pd.to_datetime(['2026-10-01', '2026-10-02']),
                        'nav_drip_index': [1., 1.]})
    joined = align_independent_returns(nav, q, pd.Timestamp('2026-10-01'),
                                        pd.Timestamp('2026-10-02'))
    assert joined.adj_close_usd_return_pct.iloc[-1] == pytest.approx(0)
    assert joined.tsla_cad_reference_return_pct.iloc[-1] == pytest.approx(100 * (140/130 - 1))


def test_canadian_holiday_fx_carries_without_filling_tsla():
    q = ref(['2026-06-30', '2026-07-01'], [100, 101],
            ['2026-06-30'], [1.35])
    assert q.fx_age_days.tolist() == [0, 1]
    assert q.tsla_cad_reference.iloc[-1] == pytest.approx(101 * 1.35)


def test_old_fx_is_missing_not_unbounded_forward_fill():
    q = ref(['2026-07-10'], [100], ['2026-07-01'], [1.35])
    assert pd.isna(q.usd_cad.iloc[0])
    assert pd.isna(q.tsla_cad_reference.iloc[0])


def test_duplicate_tsla_dates_rejected():
    with pytest.raises(CalendarAuditError, match='duplicate'):
        ref(['2026-07-01', '2026-07-01'], [100, 100],
            ['2026-07-01'], [1.35])


def test_invalid_fx_rejected():
    with pytest.raises(CalendarAuditError, match='nonpositive'):
        ref(['2026-07-01'], [100], ['2026-07-01'], [0])


def test_missing_exact_endpoint_rejected():
    nav = pd.DataFrame({'date': pd.to_datetime(['2026-10-01', '2026-10-03']),
                        'nav_drip_index': [1, 1.1]})
    q = ref(['2026-10-01', '2026-10-02'], [100, 110],
            ['2026-10-01'], [1.3])
    with pytest.raises(CalendarAuditError, match='Exact legacy start/end'):
        align_independent_returns(nav, q, '2026-10-01', '2026-10-03')


def test_missing_intermediate_tsla_day_does_not_change_endpoint_return():
    nav = pd.DataFrame({'date': pd.to_datetime(['2026-10-01', '2026-10-02', '2026-10-05']),
                        'nav_drip_index': [1, 1.05, 1.1]})
    full = ref(['2026-10-01', '2026-10-02', '2026-10-05'], [100, 108, 120],
               ['2026-10-01', '2026-10-02', '2026-10-05'], [1.3, 1.32, 1.25])
    sparse = full[full.date != pd.Timestamp('2026-10-02')].copy()
    a = align_independent_returns(nav, full, '2026-10-01', '2026-10-05')
    b = align_independent_returns(nav, sparse, '2026-10-01', '2026-10-05')
    assert a.tsla_cad_reference_return_pct.iloc[-1] == pytest.approx(
        b.tsla_cad_reference_return_pct.iloc[-1])
    assert a.nav_drip_index_return_pct.iloc[-1] == pytest.approx(
        b.nav_drip_index_return_pct.iloc[-1])


def test_cash_ex_date_removed_from_legacy_calendar_changes_nav_drip():
    dates = pd.to_datetime(['2026-10-01', '2026-10-02',
                            '2026-10-05', '2026-10-06'])
    nav = pd.DataFrame({'date': dates, 'nav': [100, 90, 100, 100]})
    cash = pd.DataFrame({'ex_date': pd.to_datetime(['2026-10-02']),
                         'amount_cad': [10.], 'kind': ['cash']})
    full = compute_nav_index(nav, cash)
    expected = full.nav_drip_index.iloc[-1]
    assert expected == pytest.approx(100 / 90)

    # Old comparison omitted the ex-date and shifted cash to 2026-10-05.
    kept = nav[nav.date != pd.Timestamp('2026-10-02')].copy().reset_index(drop=True)
    kept['price'] = kept['nav']
    kept['close_usd'] = 100
    kept['adj_close_usd'] = 100
    kept['usd_cad'] = 1.3
    kept['fx_age_days'] = 0
    kept['tsla_cad'] = 130
    mapped, meta = map_events_to_common_dates(cash, kept['date'])
    old = compute_return_paths(kept, mapped)
    assert meta['shifted_event_count'] == 1
    assert old.ytsl_nav_drip_total_return_pct.iloc[-1] == pytest.approx(10)
    assert 100 * (expected - 1) > old.ytsl_nav_drip_total_return_pct.iloc[-1]
