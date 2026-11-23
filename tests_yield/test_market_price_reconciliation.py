"""Offline tests for source-aware market-price fallback, no live requests."""
import pandas as pd
import pytest
from yield_share_market_price_reconciliation import reconcile_market_prices


def issuer():
    return pd.DataFrame({
        'date': pd.to_datetime(['2022-12-20', '2022-12-22', '2023-01-03', '2023-01-04']),
        'nav': [18.17, 16.25, 13.28, 14.03],
        'price': [24.89, 22.33, 15.66, 15.66],
    })


def yahoo():
    return pd.DataFrame({
        'date': pd.to_datetime(['2022-12-20', '2022-12-22', '2023-01-03', '2023-01-04']),
        'open': [19.53, 17.56, 14.94, 13.53],
        'high': [19.53, 17.67, 14.94, 14.01],
        'low': [18.58, 16.17, 12.84, 13.31],
        'close': [18.29, 16.35, 13.31, 13.95],
        'volume': [1378, 11235, 8280, 8248],
    })


def test_three_usable_close_quotes_and_one_unresolved():
    r = reconcile_market_prices(issuer(), yahoo(), set())
    assert r.resolution.tolist() == [
        'exclude_unverified', 'yahoo_substitute',
        'yahoo_substitute', 'yahoo_substitute']
    assert pd.isna(r.research_price.iloc[0])
    assert r.research_price.iloc[1:].tolist() == pytest.approx([16.35, 13.31, 13.95])
    assert not bool(r.yahoo_ohlcv_valid.iloc[0])  # 18.29 close < 18.58 low


def test_unresolved_distribution_ex_date_blocked():
    r = reconcile_market_prices(issuer(), yahoo(), {pd.Timestamp('2022-12-20')})
    assert r.resolution.iloc[0] == 'blocked_ex_date'


def test_valid_issuer_price_not_replaced():
    i = issuer().iloc[[1]].copy()
    i['price'] = 16.28
    r = reconcile_market_prices(i, yahoo().iloc[[1]], set())
    assert r.resolution.iloc[0] == 'issuer'
    assert r.research_price.iloc[0] == pytest.approx(16.28)


def test_zero_volume_yahoo_not_accepted():
    y = yahoo()
    y.loc[1, 'volume'] = 0
    r = reconcile_market_prices(issuer(), y, set())
    assert r.resolution.iloc[1] == 'exclude_unverified'


def test_yahoo_price_outside_nav_range_not_accepted():
    y = yahoo()
    y.loc[1, ['close', 'high']] = [22.33, 23.0]
    r = reconcile_market_prices(issuer(), y, set())
    assert r.resolution.iloc[1] == 'exclude_unverified'


def test_missing_yahoo_excludes_non_ex_date():
    r = reconcile_market_prices(issuer(), yahoo().iloc[:0], set())
    assert set(r.resolution) == {'exclude_unverified'}


def test_duplicate_secondary_date_rejected():
    y = pd.concat([yahoo(), yahoo().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match='duplicate'):
        reconcile_market_prices(issuer(), y, set())


def test_missing_nav_cannot_be_repaired_from_market_close():
    i = issuer()
    i.loc[0, 'nav'] = 0
    with pytest.raises(ValueError, match='NAV is missing'):
        reconcile_market_prices(i, yahoo(), set())


def test_ex_date_with_valid_yahoo_is_not_blocked():
    r = reconcile_market_prices(issuer(), yahoo(), {pd.Timestamp('2023-01-03')})
    assert r.resolution.iloc[2] == 'yahoo_substitute'


def test_issuer_data_is_immutable():
    i = issuer()
    before = i.copy(deep=True)
    reconcile_market_prices(i, yahoo(), set())
    pd.testing.assert_frame_equal(i, before)
