"""Offline unit tests: synthetic observations, not issuer-backtested data."""
import pandas as pd
import pytest

from yield_share_anatomy.nav import compute_nav_index, load_nav, reconcile


def nav_table(dates, values):
    return pd.DataFrame({'date': pd.to_datetime(dates), 'nav': values})


def cash_table(dates=(), amounts=()):
    return pd.DataFrame({'ex_date': pd.to_datetime(list(dates)),
                         'amount_cad': list(amounts), 'kind': ['cash'] * len(dates)})


def test_ex_date_nav_drop_offset_by_cash():
    nav = nav_table(['2026-10-01', '2026-10-02'], [100, 90])
    index = compute_nav_index(nav, cash_table(['2026-10-02'], [10]))
    assert index.nav_drip_index.iloc[-1] == pytest.approx(1.0)
    assert index.cash_per_unit.tolist() == [0.0, 10.0]


def test_reinvest_cash_across_two_ex_dates():
    nav = nav_table(['2026-10-01', '2026-10-02', '2026-10-05'], [100, 90, 80])
    cash = cash_table(['2026-10-02', '2026-10-05'], [10, 10])
    assert compute_nav_index(nav, cash).nav_drip_index.tolist() == pytest.approx([1., 1., 1.])


def test_notional_not_passed_as_cash():
    event = cash_table(['2025-12-30'], [2.318])
    event.loc[0, 'kind'] = 'notional'
    with pytest.raises(ValueError, match='Only strictly positive cash'):
        compute_nav_index(nav_table(['2025-12-29', '2025-12-30'], [20, 20]), event)


def test_missing_ex_date_rejected_instead_of_shifted():
    with pytest.raises(ValueError, match='without NAV observations'):
        compute_nav_index(nav_table(['2026-10-01', '2026-10-05'], [100, 90]),
                          cash_table(['2026-10-02'], [10]))


def test_independent_of_market_price_fx_and_tsla_calendar():
    index = compute_nav_index(nav_table(['2026-10-01', '2026-10-02'], [100, 101]),
                              cash_table())
    assert index.nav_drip_index.iloc[-1] == pytest.approx(1.01)
    assert 'price' not in index and 'usd_cad' not in index


def test_issuer_period_uses_previous_month_end():
    index = compute_nav_index(nav_table(
        ['2026-09-30', '2026-10-29', '2026-10-30'], [100, 110, 120]),
        cash_table())
    compared = reconcile(index, as_of=pd.Timestamp('2026-10-30'),
                         official={'1M': 20.0})
    assert compared.actual_start.iloc[0] == '2026-09-30'
    assert compared.calculated_pct.iloc[0] == pytest.approx(20.0)
    assert bool(compared.within_tolerance.iloc[0])


def test_issuer_comparison_needs_exact_asof():
    index = compute_nav_index(nav_table(['2026-09-30', '2026-10-29'],
                                        [100, 110]), cash_table())
    with pytest.raises(ValueError, match='Exact as-of'):
        reconcile(index, official={'1M': 10.0})


def test_missing_nav_rejected_even_if_price_present(tmp_path):
    csv = tmp_path / 'nav.csv'
    csv.write_text('date,nav,price\n2026-10-01,100,100\n2026-10-02,,98\n')
    with pytest.raises(ValueError, match='missing/nonpositive'):
        load_nav(csv)


def test_duplicate_cash_event_rejected():
    nav = nav_table(['2026-10-01', '2026-10-02'], [100, 90])
    with pytest.raises(ValueError, match='Duplicate ex-dates'):
        compute_nav_index(nav, cash_table(['2026-10-02', '2026-10-02'], [2, 8]))


def test_issuer_anchor_before_first_observation_rejected():
    index = compute_nav_index(nav_table(['2026-10-29', '2026-10-30'],
                                        [100, 110]), cash_table())
    with pytest.raises(ValueError, match='No NAV observation on or before anchor'):
        reconcile(index, official={'1M': 0.0})
