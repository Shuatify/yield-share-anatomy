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


def test_missing_2026_purpose_prices_filled_by_valid_yahoo():
    primary = pd.DataFrame({
        'date': pd.to_datetime(['2026-06-23', '2026-11-02']),
        'nav': [18.55, 17.32], 'price': [float('nan'), float('nan')],
    })
    secondary = pd.DataFrame({
        'date': pd.to_datetime(['2026-06-23', '2026-11-02']),
        'open': [19.25, 17.30], 'high': [19.25, 17.77],
        'low': [18.43, 17.05], 'close': [18.57, 17.33],
        'volume': [755183, 414900],
    })
    result = reconcile_market_prices(primary, secondary, set())
    assert result.resolution.tolist() == ['yahoo_substitute', 'yahoo_substitute']
    assert result.research_price.tolist() == pytest.approx([18.57, 17.33])
    assert result.yahoo_ohlcv_valid.all()


def test_missing_2026_price_on_distribution_ex_date_can_be_substituted():
    primary = pd.DataFrame({
        'date': pd.to_datetime(['2026-11-02']),
        'nav': [17.32], 'price': [float('nan')],
    })
    secondary = pd.DataFrame({
        'date': pd.to_datetime(['2026-11-02']),
        'open': [17.3], 'high': [17.77], 'low': [17.05],
        'close': [17.33], 'volume': [414900],
    })
    result = reconcile_market_prices(primary, secondary,
                                     {pd.Timestamp('2026-11-02')})
    assert result.resolution.iloc[0] == 'yahoo_substitute'


def test_multiple_reference_files_are_joined_with_input_hashes(tmp_path):
    from yield_share_market_price_reconciliation import run
    purpose = tmp_path / 'purpose.csv'
    purpose.write_text(
        'date,nav,price\n2022-12-22,16.25,22.33\n'
        '2026-06-23,18.55,\n2026-11-02,17.32,\n')
    old = tmp_path / 'old.csv'
    old.write_text(
        'date,open,high,low,close,volume,source,retrieved_at_utc\n'
        '2022-12-22,17.56,17.67,16.17,16.35,11235,Yahoo,2026-11-23\n')
    new = tmp_path / 'new.csv'
    new.write_text(
        'date,open,high,low,close,volume,source,retrieved_at_utc\n'
        '2026-06-23,19.25,19.25,18.43,18.57,755183,Yahoo,2026-11-23\n'
        '2026-11-02,17.3,17.77,17.05,17.33,414900,Yahoo,2026-11-23\n')
    cash = tmp_path / 'cash.csv'
    cash.write_text(
        'ex_date,pay_date,amount_cad,kind,status,source_url\n'
        '2026-01-15,2026-01-22,0.5,cash,fixture,fixture\n')
    notional = tmp_path / 'notional.csv'
    notional.write_text(
        'ex_date,amount_cad,kind,status\n'
        '2025-12-30,2.318,notional,final\n')
    report = run(purpose, [old, new], cash, notional, tmp_path / 'out')
    assert report['resolution_counts']['yahoo_substitute'] == 3
    assert old.as_posix() in report['input_sha256']
    assert new.as_posix() in report['input_sha256']
    ledger = pd.read_csv(tmp_path / 'out/market_price_reconciled_daily.csv')
    assert ledger['research_price'].tolist() == pytest.approx([16.35, 18.57, 17.33])
    assert set(ledger['reference_file']) == {old.as_posix(), new.as_posix()}


def test_duplicate_dates_across_reference_files_rejected(tmp_path):
    from yield_share_market_price_reconciliation import run
    purpose = tmp_path / 'purpose.csv'
    purpose.write_text('date,nav,price\n2026-06-23,18.55,\n')
    yahoo_data = ('date,open,high,low,close,volume\n'
                  '2026-06-23,19.25,19.25,18.43,18.57,755183\n')
    first = tmp_path / 'first.csv'
    second = tmp_path / 'second.csv'
    first.write_text(yahoo_data)
    second.write_text(yahoo_data)
    # Fail before attempting to read distribution events.
    with pytest.raises(ValueError, match='Duplicate Yahoo dates'):
        run(purpose, [first, second], tmp_path/'unused.csv',
            tmp_path/'unused_notional.csv', tmp_path/'out')
