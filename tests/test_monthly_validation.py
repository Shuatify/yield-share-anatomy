"""Independent monthly NAV/TSLA CAD study, synthetic tests plus pinned real-data regression."""
from pathlib import Path

import pandas as pd
import pytest

from yield_share_anatomy.benchmark import build_tsla_fx_reference
from yield_share_anatomy.monthly_validation import (
    MonthlyValidationError, compare_with_legacy, describe_regimes,
    independent_monthly, run,
)
from yield_share_anatomy.nav import compute_nav_index
from yield_share_anatomy.paths import BASELINE_DIR, CASH_EVENTS, SNAPSHOT_DIR


def make_nav(dates, values, ex_dates=(), distributions=()):
    daily = pd.DataFrame({"date": pd.to_datetime(dates), "nav": values})
    cash = pd.DataFrame({
        "ex_date": pd.to_datetime(list(ex_dates)),
        "amount_cad": list(distributions),
        "kind": ["cash"] * len(ex_dates),
    })
    return compute_nav_index(daily, cash)


def make_tsla(dates, prices):
    return build_tsla_fx_reference(
        pd.DataFrame({"date": dates, "adj_close_usd": prices}),
        pd.DataFrame({"date": dates, "usd_cad": [1.0] * len(dates)}))


def fake_baseline(monthly):
    return pd.DataFrame({
        "month": monthly.month,
        "date": monthly.tsla_end_date,
        "regime": monthly.regime,
        "tsla_monthly_pct": monthly.tsla_cad_monthly_pct,
        "ytsl_nav_drip_monthly_pct": monthly.nav_monthly_pct,
        "gap_pp": monthly.gap_pp,
    })


def test_cash_ex_date_accounted_for_before_month_ends():
    # NAV drops by exactly the cash event; total return over February is 0%.
    nav = make_nav(
        ["2025-01-31", "2025-02-14", "2025-02-28", "2025-03-28"],
        [100, 90, 90, 95], ["2025-02-14"], [10])
    tsla = make_tsla(["2025-01-31", "2025-02-28", "2025-03-28"],
                     [100, 100, 105])
    monthly = independent_monthly(nav, tsla)
    assert monthly.month.tolist() == ["2025-02"]
    assert monthly.nav_monthly_pct.iloc[0] == pytest.approx(0)
    assert monthly.cash_events.iloc[0] == 1
    assert monthly.cash_per_unit_total.iloc[0] == pytest.approx(10)
    assert monthly.gap_pp.iloc[0] == pytest.approx(0)


def test_unsynchronized_native_month_ends_are_reported():
    nav = make_nav(["2025-01-31", "2025-02-27", "2025-03-28"],
                   [100, 98, 95])
    tsla = make_tsla(["2025-01-31", "2025-02-28", "2025-03-28"],
                     [100, 102, 104])
    monthly = independent_monthly(nav, tsla)
    assert not bool(monthly.native_end_dates_aligned.iloc[0])
    assert monthly.nav_end_date.iloc[0] == pd.Timestamp("2025-02-27")
    assert monthly.tsla_end_date.iloc[0] == pd.Timestamp("2025-02-28")
    comparison = compare_with_legacy(monthly, fake_baseline(monthly))
    assert not bool(comparison.legacy_month_end_matches_both.iloc[0])


def test_last_partial_month_is_not_included():
    nav = make_nav(["2025-01-31", "2025-02-28", "2025-03-14"],
                   [100, 110, 120])
    tsla = make_tsla(["2025-01-31", "2025-02-28", "2025-03-14"],
                     [100, 100, 100])
    assert independent_monthly(nav, tsla).month.tolist() == ["2025-02"]


def test_regime_5_percent_threshold_is_strict():
    nav = make_nav(["2025-01-31", "2025-02-28", "2025-03-31"],
                   [100, 100, 100])
    tsla = make_tsla(["2025-01-31", "2025-02-28", "2025-03-31"],
                     [100, 105, 105])
    row = independent_monthly(nav, tsla)
    assert row.regime.iloc[0] == "Sideways"
    # 95/100 - 1 also has a tiny negative floating-point representation error.
    down_equal = make_tsla(["2025-01-31", "2025-02-28", "2025-03-31"],
                           [100, 95, 95])
    assert independent_monthly(nav, down_equal).regime.iloc[0] == "Sideways"
    lower = make_tsla(["2025-01-31", "2025-02-28", "2025-03-31"],
                      [100, 94, 94])
    assert independent_monthly(nav, lower).regime.iloc[0] == "Down"


def test_missing_month_in_secondary_source_is_hard_error():
    nav = make_nav(["2025-01-31", "2025-02-28", "2025-03-31"],
                   [100, 100, 100])
    tsla = make_tsla(["2025-01-31", "2025-03-31"], [100, 105])
    with pytest.raises(MonthlyValidationError, match="different covered months"):
        independent_monthly(nav, tsla)


def test_month_gap_in_both_sources_is_hard_error():
    nav = make_nav(["2025-01-31", "2025-03-31", "2025-04-30"],
                   [100, 105, 110])
    tsla = make_tsla(["2025-01-31", "2025-03-31", "2025-04-30"],
                     [100, 105, 110])
    with pytest.raises(MonthlyValidationError, match="Monthly series has gaps"):
        independent_monthly(nav, tsla)


def test_missing_legacy_month_is_hard_error():
    nav = make_nav(["2025-01-31", "2025-02-28", "2025-03-31"],
                   [100, 105, 110])
    tsla = make_tsla(["2025-01-31", "2025-02-28", "2025-03-31"],
                     [100, 105, 110])
    monthly = independent_monthly(nav, tsla)
    with pytest.raises(MonthlyValidationError, match="month sets differ"):
        compare_with_legacy(monthly, fake_baseline(monthly).iloc[:0])


def test_legacy_difference_is_detected_and_never_overwritten():
    nav = make_nav(["2025-01-31", "2025-02-28", "2025-03-31"],
                   [100, 110, 120])
    tsla = make_tsla(["2025-01-31", "2025-02-28", "2025-03-31"],
                     [100, 105, 110])
    monthly = independent_monthly(nav, tsla)
    baseline = fake_baseline(monthly)
    baseline.loc[0, "gap_pp"] += 2
    compared = compare_with_legacy(monthly, baseline)
    assert compared.gap_difference_pp.iloc[0] == pytest.approx(-2)


def test_regime_summary_counts_wins_and_means():
    frame = pd.DataFrame({
        "regime": ["Down", "Down", "Up", "Sideways"],
        "gap_pp": [-1.5, 0.5, 3.0, 0.0],
    })
    report = {row["regime"]: row for row in describe_regimes(frame)}
    assert report["Down"]["months"] == 2
    assert report["Down"]["mean_gap_pp"] == pytest.approx(-0.5)
    assert report["Down"]["ytsl_win_rate_pct"] == pytest.approx(50)
    assert report["Sideways"]["ytsl_win_months"] == 0


def test_offline_real_46_month_reconciliation(tmp_path):
    report = run(
        snapshot_dir=SNAPSHOT_DIR, events_file=CASH_EVENTS,
        baseline_file=BASELINE_DIR / "phase1" / "monthly_regimes.csv",
        out_dir=tmp_path)
    assert report["status"] == "pass"
    assert report["month_count"] == 46
    assert report["first_month"] == "2023-01"
    assert report["last_month"] == "2026-10"
    assert report["regime_mismatch_months"] == []
    assert report["month_end_mismatch_months"] == []
    assert max(report["max_abs_difference_pp"].values()) < 1e-8
    grouped = {row["regime"]: row for row in report["regime_summary"]}
    assert [(name, grouped[name]["months"]) for name in ("Up","Sideways","Down")] == [
        ("Up", 18), ("Sideways", 15), ("Down", 13)]
    assert grouped["Down"]["mean_gap_pp"] == pytest.approx(-1.5697006665108377, abs=1e-8)
    assert grouped["Down"]["ytsl_win_months"] == 4
    rows = pd.read_csv(tmp_path / "monthly_vs_legacy.csv")
    assert len(rows) == 46
    assert rows.native_end_dates_aligned.all()
    assert rows.legacy_month_end_matches_both.all()
