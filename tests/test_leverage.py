"""Frictionless daily-reset leverage: synthetic guards + pinned real-data regression."""
import json
import math

import pandas as pd
import pytest

from yield_share_anatomy.leverage import (
    CounterfactualError, leverage_index, run, study,
)
from yield_share_anatomy.paths import CASH_EVENTS, SNAPSHOT_DIR


def fx_ref(dates, prices):
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "tsla_cad_reference": [float(x) for x in prices],
    })


def make_nav(dates, wealth):
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        "nav_drip_index": [float(x) for x in wealth],
    })


def test_daily_reset_1x_is_exact_price_ratio():
    ref = fx_ref(["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07"],
                 [100, 90, 100, 110])
    x = leverage_index(ref, 1.0, start=pd.Timestamp("2025-01-02"),
                       end=pd.Timestamp("2025-01-07"))
    assert x.wealth_multiple.tolist() == pytest.approx([1, .9, 1, 1.1])
    assert x.model_factor.iloc[0] == 1


def test_daily_reset_leverage_has_path_dependence():
    ref = fx_ref(["2025-01-02", "2025-01-03", "2025-01-06"],
                 [100, 90, 100])
    x = leverage_index(ref, 1.2, start="2025-01-02", end="2025-01-06")
    assert x.wealth_multiple.iloc[-1] == pytest.approx(.88 * (1 + 1.2/9))
    assert x.wealth_multiple.iloc[-1] < 1
    assert x.tsla_cad_reference.iloc[-1] == x.tsla_cad_reference.iloc[0]


def test_nonshared_us_session_is_still_daily_rebalanced():
    ref = fx_ref(["2025-01-02", "2025-01-03", "2025-01-06",
                  "2025-01-07", "2025-01-08"],
                 [100, 90, 100, 110, 100])
    x = leverage_index(ref, 1.2, start="2025-01-02", end="2025-01-08")
    # Jan 03 is missing from the Canadian NAV calendar but included in
    # the US daily reset. Jan 02 -> Jan 06 TSLA total return is exactly 0.
    nav_dates = pd.to_datetime(["2025-01-02", "2025-01-06",
                                "2025-01-07", "2025-01-08"])
    matched = x.set_index("date").loc[nav_dates, "wealth_multiple"]
    assert matched.iloc[1] == pytest.approx(.9973333333333334, abs=1e-13)
    assert matched.iloc[1] != pytest.approx(1)


def test_missing_fx_value_blocks_derived_daily_model():
    ref = fx_ref(["2025-01-02", "2025-01-03", "2025-01-06"],
                 [100, 90, 100])
    ref.loc[1, "tsla_cad_reference"] = float("nan")
    with pytest.raises(CounterfactualError, match="Missing, nonpositive"):
        leverage_index(ref, 1.1, start="2025-01-02", end="2025-01-06")


def test_exact_anchor_must_exist():
    ref = fx_ref(["2025-01-02", "2025-01-03", "2025-01-06"],
                 [100, 90, 100])
    with pytest.raises(CounterfactualError, match="Exact model start"):
        leverage_index(ref, 1.1, start="2025-01-01", end="2025-01-06")


def test_leverage_wipeout_rejected():
    ref = fx_ref(["2025-01-02", "2025-01-03", "2025-01-06"],
                 [100, 10, 20])
    with pytest.raises(CounterfactualError, match="wipes out"):
        leverage_index(ref, 1.2, start="2025-01-02", end="2025-01-06")


def test_duplicate_and_bad_leverage_rejected():
    ref = fx_ref(["2025-01-02", "2025-01-03"], [100, 101])
    ref = pd.concat([ref, ref.iloc[[0]]], ignore_index=True)
    with pytest.raises(CounterfactualError, match="duplicate"):
        leverage_index(ref, 1, start="2025-01-02", end="2025-01-03")
    with pytest.raises(CounterfactualError, match="positive and finite"):
        leverage_index(ref, float("inf"), start="2025-01-02", end="2025-01-03")


def test_long_us_calendar_gap_is_not_silently_used():
    ref = fx_ref(["2025-01-02", "2025-01-20"], [100, 110])
    with pytest.raises(CounterfactualError, match="Excessive gap"):
        leverage_index(ref, 1, start="2025-01-02", end="2025-01-20")


def test_study_fails_without_1x_identity_scenario():
    dates = pd.bdate_range("2025-01-02", periods=8)
    nav = make_nav(dates, [1, 1.02, 1, 1.05, .98, 1.03, .96, 1.01])
    tsla = fx_ref(dates, [100, 104, 99, 105, 97, 103, 96, 101])
    with pytest.raises(CounterfactualError, match="Include 1.0x"):
        study(nav, tsla, start=dates[0], end=dates[-1], leverages=(1.1,))


def test_synthetic_study_keeps_real_nav_benchmark_and_model_separate():
    dates = pd.bdate_range("2025-01-02", periods=8)
    nav = make_nav(dates, [1, 1.03, .98, 1.07, .96, 1.06, .93, 1.02])
    tsla = fx_ref(dates, [100, 104, 99, 105, 97, 103, 96, 101])
    native, shared, report = study(nav, tsla,
        start=dates[0], end=dates[-1], leverages=(1.0, 1.2))
    assert report["status"] == "pass"
    assert report["native_tsla_trading_closes"] == 8
    assert report["shared_nav_tsla_closes"] == 8
    assert report["actual_ytsl_nav"]["wealth_multiple"] == pytest.approx(1.02)
    assert report["scenarios"][0]["wealth_multiple"] == pytest.approx(1.01)
    assert len(native) == 16
    assert len(shared) == 8
    assert len(report["scenarios"][1]["by_calendar_year"]) == 1
    assert report["assumptions"]["ETF_replication_claim"] is False
    assert report["assumptions"]["financing_cost"] == 0


def test_real_pinned_leverage_paths_and_beta_are_reproduced(tmp_path):
    report = run(SNAPSHOT_DIR, CASH_EVENTS, tmp_path)
    assert report["status"] == "pass"
    assert report["native_tsla_trading_closes"] == 983
    assert report["shared_nav_tsla_closes"] == 963
    assert report["shared_return_intervals"] == 962
    assert report["actual_ytsl_nav"]["total_return_pct"] == pytest.approx(
        120.41139492221933, abs=1e-8)
    assert report["actual_ytsl_nav"]["max_drawdown_shared_closes_pct"] == pytest.approx(
        -58.31161389385679, abs=1e-8)
    assert report["actual_ytsl_nav"]["down_minus_up_beta"] == pytest.approx(
        0.1303006081534479, abs=1e-9)
    s = {round(x["leverage"], 1): x for x in report["scenarios"]}
    assert sorted(s) == [1.0, 1.1, 1.2]
    assert s[1.0]["total_return_pct"] == pytest.approx(
        164.54468803302754, abs=1e-8)
    assert s[1.1]["total_return_pct"] == pytest.approx(
        171.7657053260988, abs=1e-8)
    assert s[1.2]["total_return_pct"] == pytest.approx(
        175.62690522311652, abs=1e-8)
    assert s[1.2]["nav_minus_model_pp_initial_capital"] == pytest.approx(
        -55.21551030089719, abs=1e-8)
    assert abs(s[1.1]["conditional_beta_vs_tsla_cad"]["down_minus_up_beta"]) < 0.001
    assert abs(s[1.2]["conditional_beta_vs_tsla_cad"]["down_minus_up_beta"]) < 0.001
    assert s[1.2]["max_drawdown_shared_closes_pct"] == pytest.approx(
        -61.82960276353535, abs=1e-7)
    assert all(len(v["by_calendar_year"]) == 5 for v in s.values())
    assert s[1.2]["by_calendar_year"][2]["model_return_pct"] == pytest.approx(
        89.29612525723594, abs=1e-8)
    assert s[1.2]["by_calendar_year"][3]["model_return_pct"] == pytest.approx(
        2.396962709351036, abs=1e-8)
    assert len(pd.read_csv(tmp_path / "daily_model_on_tsla_sessions.csv")) == 983 * 3
    assert len(pd.read_csv(tmp_path / "common_close_wealth.csv")) == 963
    status = json.loads((tmp_path / "leverage_counterfactual_summary.json").read_text())
    assert status["input_sha256"] == {
        "purpose_nav": "a0a6c90c3d804c354bc53ef384630f8b0abff6d5fdb5d318cb75ca65ea6e76f7",
        "tsla_usd": "925076d6d488413b3c8246d206654d719186f3c73bd2bd5007ede1f9acd7c48b",
        "usd_cad": "ffaca3a83de376bf4b47cc32a5b73015b1a1767933903c0f12a0ab8a119f0fbf",
        "cash_events": "7142c89fa4e15efeef67b87d6d11e32a914863caee47b2b72dfa2422d226108e",
    }
