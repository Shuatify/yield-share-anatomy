"""Offline regression tests against the immutable 2026-11-20 live-data snapshot.

These tests make no external HTTP requests. They verify that structural
refactors cannot silently change benchmarked research results.
"""
import hashlib

import pandas as pd
import pytest

from yield_share_anatomy import benchmark, market, nav, returns
from yield_share_anatomy.paths import (
    CASH_EVENTS, NOTIONAL_EVENTS, SNAPSHOT_DIR,
    REFERENCE_DIR, RAW_PURPOSE_FILE,
)

INPUT_HASHES = {
    'ytsl_purpose_daily.csv': 'a0a6c90c3d804c354bc53ef384630f8b0abff6d5fdb5d318cb75ca65ea6e76f7',
    'tsla_yahoo_daily.csv': '925076d6d488413b3c8246d206654d719186f3c73bd2bd5007ede1f9acd7c48b',
    'usdcad_boc_daily.csv': 'ffaca3a83de376bf4b47cc32a5b73015b1a1767933903c0f12a0ab8a119f0fbf',
}


def test_committed_input_fingerprints():
    for name, digest in INPUT_HASHES.items():
        assert hashlib.sha256((SNAPSHOT_DIR / name).read_bytes()).hexdigest() == digest
    assert RAW_PURPOSE_FILE.exists()
    assert len(pd.read_csv(RAW_PURPOSE_FILE)) == 985
    assert hashlib.sha256(CASH_EVENTS.read_bytes()).hexdigest() == (
        '7142c89fa4e15efeef67b87d6d11e32a914863caee47b2b72dfa2422d226108e')


def test_legacy_phase1_outputs_reproduced(tmp_path):
    report = returns.run(SNAPSHOT_DIR, CASH_EVENTS, NOTIONAL_EVENTS, tmp_path / 'phase1')
    assert report['status'] == 'ok'
    assert report['common_days'] == 958
    assert report['event_mapping']['shifted_event_count'] == 0
    x = report['total_return_at_end_pct']
    assert x['ytsl_nav_drip'] == pytest.approx(120.4114, abs=1e-4)
    assert x['tsla_cad'] == pytest.approx(164.5447, abs=1e-4)
    assert len(pd.read_csv(tmp_path / 'phase1/monthly_regimes.csv')) == 46


def test_purpose_issuer_nav_reconciliation_reproduced(tmp_path):
    out = tmp_path / 'nav'
    result = nav.run(SNAPSHOT_DIR / 'ytsl_purpose_daily.csv', CASH_EVENTS, out)
    assert result['status'] == 'pass'
    assert result['nav_observations'] == 985
    assert result['cash_events_in_nav_range'] == 47
    rows = pd.read_csv(out / 'nav_reconciliation.csv')
    assert len(rows) == 7
    assert rows['within_tolerance'].all()
    assert rows['difference_pp'].abs().max() < 0.031


def test_independent_calendar_bridge_reproduced(tmp_path):
    result = benchmark.run(SNAPSHOT_DIR, CASH_EVENTS, tmp_path / 'bridge')
    assert result['legacy_common_days'] == 958
    assert result['nav_trading_days_in_window'] == 983
    assert result['independent_exact_shared_days'] == 963
    assert result['cash_ex_dates_missing_from_legacy_common_calendar'] == []
    assert result['legacy_nav_drip_pct'] == pytest.approx(120.41139492221969, abs=1e-7)
    assert result['independent_tsla_cad_pct'] == pytest.approx(164.54468803302754, abs=1e-7)
    assert result['independent_nav_minus_tsla_cad_pp'] == pytest.approx(-44.13329311080821, abs=1e-7)
    assert abs(result['total_gap_method_effect_pp']) < 1e-8


def test_market_price_quality_reproduced(tmp_path):
    out = tmp_path / 'market'
    result = market.run(
        SNAPSHOT_DIR / 'ytsl_purpose_daily.csv',
        [REFERENCE_DIR / 'ytsl_yahoo_close_2022_2023.csv',
         REFERENCE_DIR / 'ytsl_yahoo_close_2026.csv'],
        CASH_EVENTS, NOTIONAL_EVENTS, out)
    assert result['resolution_counts'] == {
        'issuer': 978, 'yahoo_substitute': 5, 'exclude_unverified': 2}
    rows = pd.read_csv(out / 'market_price_source_discrepancies.csv')
    assert len(rows) == 7
    assert set(rows.loc[rows['resolution'] == 'exclude_unverified', 'date']) == {
        '2022-12-19', '2022-12-20'}
