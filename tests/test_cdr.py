"""Synthetic data checks for TSLA CDR ingestion. Not live-data validation."""
import pandas as pd
import pytest
from yield_share_anatomy.cdr import stitch, parse_chart, audit_external, CDRDataError


def quote(date, close, ticker, volume=100):
    return {
        "date": date, "open": close, "high": close * 1.01,
        "low": close * 0.99, "close": close,
        "adj_close": close, "volume": volume, "ticker": ticker
    }


def test_venue_transition_never_uses_ghost_cboe_prices():
    ne = pd.DataFrame([
        quote("2025-02-05", 20, "TSLA.NE"),
        quote("2025-02-13", 21, "TSLA.NE"),
        quote("2025-02-14", 999, "TSLA.NE", 0),
    ])
    to = pd.DataFrame([
        quote("2025-02-05", 20, "TSLA.TO"),
        quote("2025-02-13", 21, "TSLA.TO"),
        quote("2025-02-14", 22, "TSLA.TO"),
    ])
    result, issues = stitch(ne, to)
    assert result.set_index("date").loc["2025-02-14", "close"] == 22
    assert result.set_index("date").loc["2025-02-13", "ticker"] == "TSLA.NE"
    assert not any(x["code"] == "venue_overlap_disagreement" for x in issues)


def test_overlap_price_disagreement_is_flagged():
    ne = pd.DataFrame([quote("2025-02-05", 20, "TSLA.NE")])
    to = pd.DataFrame([quote("2025-02-05", 25, "TSLA.TO")])
    _, issues = stitch(ne, to)
    assert any(x["code"] == "venue_overlap_disagreement" for x in issues)


def test_external_disagreement_does_not_silently_rewrite_price():
    series = pd.DataFrame([quote("2025-02-14", 22, "TSLA.TO")])
    comparison = audit_external(series, pd.DataFrame({
        "date": ["2025-02-14"], "close_cad": [30]
    }), "tsx")
    assert len(comparison["outliers"]) == 1
    assert series.loc[0, "close"] == 22


def test_yahoo_currency_must_be_cad():
    raw = {"chart": {"result": [{
        "meta": {"currency": "USD"}, "timestamp": [1740000000],
        "indicators": {"quote": [{}]}
    }]}}
    with pytest.raises(CDRDataError, match="currency"):
        parse_chart(raw, "TSLA.NE")


def test_full_to_history_kept_as_unverified_legacy_backfill():
    ne = pd.DataFrame(columns=["date", "open", "high", "low", "close", "adj_close", "volume", "ticker"])
    to = pd.DataFrame([
        quote("2022-12-21", 12, "TSLA.TO"),
        quote("2025-02-13", 21, "TSLA.TO"),
        quote("2025-02-14", 22, "TSLA.TO"),
    ])
    result, issues = stitch(ne, to)
    assert len(result) == 3
    assert result.iloc[0]["date"] == "2022-12-21"
    assert any(x["code"] == "historical_vendor_backfill_requires_exchange_validation" for x in issues)
