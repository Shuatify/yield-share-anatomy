"""Synthetic fixture and input-validation tests; no real-market conclusions."""
import json
from pathlib import Path
import sys
import pandas as pd
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yield_share_phase0_fetch import (parse_purpose, parse_yahoo, parse_boc,
                                      load_fixtures, build_alignment, quality_metrics, DataProblem, save)

FIX=Path(__file__).parent/'fixtures'


def test_purpose_ascending_and_missing_price():
    df=parse_purpose((FIX/'purpose.csv').read_text(),min_rows=3)
    assert len(df)==6
    assert df.date.is_monotonic_increasing
    assert pd.isna(df.loc[2,'price'])


def test_yahoo_timezone_and_close():
    df=parse_yahoo(json.loads((FIX/'yahoo.json').read_text()),min_rows=3)
    assert df.date.iloc[0] == pd.Timestamp('2026-11-09')
    assert df.close_usd.iloc[-1] == 451


def test_yahoo_schema_failure():
    with pytest.raises(DataProblem):
        parse_yahoo({'chart':{'result':[]}},min_rows=3)


def test_fx_parse():
    df=parse_boc(json.loads((FIX/'boc.json').read_text()),min_rows=3)
    assert df.usd_cad.iloc[0] == 1.37


def test_fx_missing_holiday_carries_prior_rate():
    aligned=build_alignment(load_fixtures(FIX))
    row=aligned.loc[aligned.date==pd.Timestamp('2026-11-11')].iloc[0]
    assert row.fx_age_days==1
    assert row.usd_cad==1.371
    assert row.tsla_cad_reference==pytest.approx(440*1.371)


def test_quality_detects_null_price():
    qc=quality_metrics(load_fixtures(FIX))
    assert qc['ytsl']['null_values']['price']==1
    assert qc['ytsl']['rows']==6


def test_purpose_rejects_missing_nav():
    with pytest.raises(DataProblem):
        parse_purpose('date,price,volume\n2026-11-09,1,100\n',min_rows=1)


def test_synthetic_outputs_marked(tmp_path):
    result=save(load_fixtures(FIX),tmp_path,fixture=True)
    assert result['data_type']=='SYNTHETIC_TEST_FIXTURE'
    assert (tmp_path/'aligned_daily_preview.csv').exists()
    assert json.loads((tmp_path/'fetch_status.json').read_text())['quality']['alignment']['rows']==6

from yield_share_phase0_fetch import fetch_live


class FakeResponse:
    def __init__(self, text='', payload=None, code=200):
        self.text, self.payload, self.status_code = text, payload, code

    def raise_for_status(self):
        if self.status_code >= 400:
            from requests import HTTPError
            err = HTTPError(f'{self.status_code} rate limited')
            err.response = self
            raise err

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, purpose_code=429):
        self.headers = {}
        self.urls = []
        self.purpose_code = purpose_code

    def get(self, url, **kwargs):
        self.urls.append(url)
        if '/api/nav' in url:
            return FakeResponse((FIX/'purpose.csv').read_text(), code=self.purpose_code)
        if '/finance/chart/' in url:
            return FakeResponse(payload=json.loads((FIX/'yahoo.json').read_text()))
        if 'bankofcanada' in url:
            return FakeResponse(payload=json.loads((FIX/'boc.json').read_text()))
        raise ValueError(url)


def test_429_fetches_other_sources_and_reports_partial(tmp_path, monkeypatch):
    from yield_share_phase0_fetch import parse_yahoo as py, parse_boc as pb
    monkeypatch.setattr('yield_share_phase0_fetch.parse_yahoo', lambda payload: py(payload, min_rows=3))
    monkeypatch.setattr('yield_share_phase0_fetch.parse_boc', lambda payload: pb(payload, min_rows=3))
    session = FakeSession()
    data, errors, sources = fetch_live(session)
    assert sorted(data) == ['fx', 'tsla']
    assert '429' in errors['ytsl']
    assert len(session.urls) == 3
    status = save(data, tmp_path, fixture=False, errors=errors, sources=sources)
    assert status['status'] == 'partial'
    assert (tmp_path/'tsla_yahoo_daily.csv').exists()
    assert (tmp_path/'usdcad_boc_daily.csv').exists()
    assert not (tmp_path/'aligned_daily_preview.csv').exists()


def test_manual_purpose_file_skips_http_download(monkeypatch):
    from yield_share_phase0_fetch import parse_yahoo as py, parse_boc as pb
    monkeypatch.setattr('yield_share_phase0_fetch.parse_purpose',
                        lambda txt: parse_purpose(txt, min_rows=3))
    monkeypatch.setattr('yield_share_phase0_fetch.parse_yahoo', lambda payload: py(payload, min_rows=3))
    monkeypatch.setattr('yield_share_phase0_fetch.parse_boc', lambda payload: pb(payload, min_rows=3))
    session = FakeSession()
    data, errors, sources = fetch_live(session, purpose_file=FIX/'purpose.csv')
    assert set(data) == {'fx', 'tsla', 'ytsl'}
    assert not errors
    assert all('/api/nav' not in url for url in session.urls)
    assert sources['ytsl'].startswith('user-provided file:')


def test_cached_purpose_skips_http_download(tmp_path, monkeypatch):
    from yield_share_phase0_fetch import parse_yahoo as py, parse_boc as pb
    monkeypatch.setattr('yield_share_phase0_fetch.parse_purpose',
                        lambda txt: parse_purpose(txt, min_rows=3))
    monkeypatch.setattr('yield_share_phase0_fetch.parse_yahoo', lambda payload: py(payload, min_rows=3))
    monkeypatch.setattr('yield_share_phase0_fetch.parse_boc', lambda payload: pb(payload, min_rows=3))
    cache = tmp_path/'ytsl_purpose_daily.csv'
    cache.write_text((FIX/'purpose.csv').read_text())
    session = FakeSession()
    data, errors, sources = fetch_live(session, cached_purpose_csv=cache)
    assert not errors
    assert set(data) == {'fx', 'tsla', 'ytsl'}
    assert all('/api/nav' not in url for url in session.urls)
    assert 'cached file:' in sources['ytsl']


def test_partial_removes_stale_alignment(tmp_path):
    (tmp_path/'aligned_daily_preview.csv').write_text('STALE DATA')
    save({'tsla': load_fixtures(FIX)['tsla']}, tmp_path, fixture=False,
         errors={'ytsl':'429', 'fx':'unavailable'})
    assert not (tmp_path/'aligned_daily_preview.csv').exists()
