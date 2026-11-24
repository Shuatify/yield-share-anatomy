"""Effective-beta regression checks: synthetic and pinned real data."""
import math

import pandas as pd
import pytest

from yield_share_anatomy.exposure import (
    ExposureError, annual_fits, block_bootstrap, conditional_fits,
    fit_beta, paired_daily, rolling_beta, run,
)
from yield_share_anatomy.paths import CASH_EVENTS, SNAPSHOT_DIR


def returns(x, y):
    return pd.DataFrame({"tsla_cad_return": x, "ytsl_nav_return": y})


def test_ols_with_intercept_recovers_known_beta():
    x = [-.05, -.02, .01, .03, .06]
    y = [0.002 + 1.25 * v for v in x]
    result = fit_beta(returns(x, y))
    assert result["beta"] == pytest.approx(1.25)
    assert result["alpha_interval_pp"] == pytest.approx(.2)
    assert result["r_squared"] == pytest.approx(1.0)
    assert result["n"] == 5


def test_constant_input_and_nonfinite_rejected():
    with pytest.raises(ExposureError, match="constant TSLA"):
        fit_beta(returns([.01] * 5, [.02] * 5))
    with pytest.raises(ExposureError, match="Nonfinite"):
        fit_beta(returns([.01, .02, .03], [.01, float("nan"), .03]))


def test_conditional_slopes_can_be_asymmetric():
    x = [-.06, -.04, -.02, .01, .03, .05]
    y = [2 * v if v < 0 else v for v in x]
    result = conditional_fits(returns(x, y))
    assert result["down"]["beta"] == pytest.approx(2.0)
    assert result["up"]["beta"] == pytest.approx(1.0)
    assert result["down_minus_up_beta"] == pytest.approx(1.0)
    assert result["excluded_near_zero"] == 0


def test_contemporaneous_direction_uses_tsla_sign_not_nav_sign():
    x = [-.05, -.03, -.02, .01, .02, .04]
    y = [.01, -.03, -.02, -.01, .02, .04]
    result = conditional_fits(returns(x, y))
    assert result["down"]["n"] == 3
    assert result["up"]["n"] == 3


def test_nonlinear_direction_threshold_filters_small_days():
    x = [-.05, -.03, -.002, .001, .03, .05]
    y = [1.1 * v for v in x]
    result = conditional_fits(returns(x, y), threshold_pct=1, min_n=2)
    assert result["up"]["n"] == 2
    assert result["down"]["n"] == 2
    assert result["excluded_near_zero"] == 2
    with pytest.raises(ExposureError, match="Direction threshold"):
        conditional_fits(returns(x, y), threshold_pct=-1)


def test_paired_calendar_preserves_intervening_nav_cash_entitlement():
    nav = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-03",
                                "2025-01-06", "2025-01-07", "2025-01-08"]),
        "nav_drip_index": [1.0, 1.0, 1.1, 1.2, 1.25],
    })
    tsla = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-03",
                                "2025-01-07", "2025-01-08"]),
        "tsla_cad_reference": [100.0, 100.0, 110.0, 115.0],
    })
    paired = paired_daily(nav, tsla,
                          start=pd.Timestamp("2025-01-02"),
                          end=pd.Timestamp("2025-01-08"))
    assert paired.date.dt.strftime("%Y-%m-%d").tolist() == [
        "2025-01-03", "2025-01-07", "2025-01-08"]
    assert paired.ytsl_nav_return.iloc[1] == pytest.approx(.20)
    assert paired.tsla_cad_return.iloc[1] == pytest.approx(.10)
    assert paired.gap_calendar_days.tolist() == [1, 4, 1]


def test_missing_exact_endpoint_fails_loudly():
    nav = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-03",
                                "2025-01-06", "2025-01-07"]),
        "nav_drip_index": [1, 1.01, 1.02, 1.03],
    })
    tsla = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-03",
                                "2025-01-06", "2025-01-08"]),
        "tsla_cad_reference": [100, 101, 102, 103],
    })
    with pytest.raises(ExposureError, match="Exact requested start/end"):
        paired_daily(nav, tsla, start=pd.Timestamp("2025-01-02"),
                     end=pd.Timestamp("2025-01-07"))


def test_bootstrap_reproducible_with_seed():
    x = ([.02, -.03, .04, -.05, .06, -.07, .08, -.09] * 5)
    frame = returns(x, [v * (1.2 if v < 0 else .9) for v in x])
    first = block_bootstrap(frame, block=4, replicates=30, seed=101)
    second = block_bootstrap(frame, block=4, replicates=30, seed=101)
    assert first == second
    assert first["beta_ci_95"]["down_minus_up"][0] == pytest.approx(.3)
    assert first["beta_ci_95"]["down_minus_up"][1] == pytest.approx(.3)
    assert not first["delta_includes_zero"]


def test_invalid_bootstrap_parameters_rejected():
    frame = returns([(-1)**i * .02 for i in range(20)],
                    [(-1)**i * .03 for i in range(20)])
    with pytest.raises(ExposureError, match="n>=12"):
        block_bootstrap(frame, block=11, replicates=40)
    with pytest.raises(ExposureError, match="n>=12"):
        block_bootstrap(frame, block=5, replicates=4)


def test_rolling_beta_uses_only_trailing_observations():
    x = [.01, -.02, .03, -.04, .05, -.06, .07]
    frame = returns(x, [1.1 * v for v in x])
    frame["date"] = pd.to_datetime([
        "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07",
        "2025-01-08", "2025-01-09", "2025-01-10"])
    frame["previous_date"] = frame["date"].shift(1)
    frame.loc[0, "previous_date"] = pd.Timestamp("2024-12-31")
    rolling = rolling_beta(frame, windows=(3, 5))
    assert (rolling.window_intervals == 3).sum() == 5
    assert (rolling.window_intervals == 5).sum() == 3
    assert all(math.isclose(v, 1.1) for v in rolling.beta)


def test_short_year_is_explicitly_insufficient():
    frame = returns([.01, -.02, .03, .02, -.01],
                    [.012, -.024, .036, .024, -.012])
    frame["date"] = pd.to_datetime([
        "2022-12-21", "2022-12-22", "2022-12-23",
        "2022-12-29", "2022-12-30"])
    annual = annual_fits(frame)
    assert annual == [{"year": 2022, "status": "insufficient_sample", "n": 5}]



def test_annual_directional_beta_is_separate_per_calendar_year():
    x = [0.01, 0.03, 0.05, -0.02, -0.04, -0.06] * 12
    frame = returns(x, [v if v > 0 else 1.25*v for v in x])
    frame["date"] = pd.bdate_range("2024-01-01", periods=len(frame))
    group = annual_fits(frame)
    assert len(group) == 1
    assert group[0]["year"] == 2024
    assert group[0]["directional"]["up"]["n"] == 36
    assert group[0]["directional"]["down"]["n"] == 36
    assert group[0]["directional"]["down_minus_up_beta"] == pytest.approx(.25)

def test_real_2026_11_20_effective_beta_snapshot(tmp_path):
    report = run(SNAPSHOT_DIR, CASH_EVENTS, tmp_path,
                 block=10, replicates=60, seed=20261120)
    assert report["status"] == "ok"
    assert report["common_closing_dates"] == 963
    assert report["paired_intervals"] == 962
    assert report["full_daily"]["beta"] == pytest.approx(1.0840605323710557, abs=1e-10)
    assert report["daily_directional"]["up"]["n"] == 485
    assert report["daily_directional"]["down"]["n"] == 477
    assert report["daily_directional"]["up"]["beta"] == pytest.approx(1.0276102667278972, abs=1e-10)
    assert report["daily_directional"]["down"]["beta"] == pytest.approx(1.1579108748813451, abs=1e-10)
    assert report["monthly_46"]["observations"] == 46
    assert report["monthly_46"]["full"]["beta"] == pytest.approx(1.0280119835727202, abs=1e-10)
    assert report["rolling"]["63"]["latest_beta"] == pytest.approx(1.0972766774844869, abs=1e-10)
    assert report["rolling"]["126"]["latest_beta"] == pytest.approx(1.1122876670444135, abs=1e-10)
    assert report["annual"][0]["status"] == "insufficient_sample"
    years = {v["year"]: v for v in report["annual"] if v["status"] == "estimated"}
    assert sorted(years) == [2023, 2024, 2025, 2026]
    assert all(years[y]["directional"]["down_minus_up_beta"] > 0 for y in years)
    assert years[2024]["directional"]["down_minus_up_beta"] == pytest.approx(
        0.1666939869468964, abs=1e-9)
    assert len(pd.read_csv(tmp_path/"paired_daily_returns.csv")) == 962
    assert len(pd.read_csv(tmp_path/"rolling_beta.csv")) == 900 + 837
    assert (tmp_path/"effective_beta_summary.json").exists()
