"""Exact compounding identity: synthetic checks and pinned real-data regression."""
import json
import math

import pandas as pd
import pytest

from yield_share_anatomy.compounding import (
    CompoundingError, components, decompose, run, study,
)
from yield_share_anatomy.paths import CASH_EVENTS, SNAPSHOT_DIR


def paired(xs, ys):
    assert len(xs) == len(ys)
    dates = pd.bdate_range("2025-01-02", periods=len(xs) + 1)
    ywealth = 1.0
    xwealth = 100.0
    rows = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        ywealth *= 1 + y
        xwealth *= 1 + x
        rows.append({
            "date": dates[i + 1],
            "previous_date": dates[i],
            "tsla_cad_return": x,
            "ytsl_nav_return": y,
            "nav_drip_index": ywealth,
            "tsla_cad_reference": xwealth,
        })
    return pd.DataFrame(rows)


def test_exact_log_identity_and_second_order_remainder():
    frame, summary = study(paired([.03, -.04, .07], [.05, -.06, .08]))
    ar = summary["components_100x_decimal"]["arithmetic_spread_sum_100x"]
    nonlinear = summary["components_100x_decimal"]["nonlinear_correction_100x"]
    log = summary["components_100x_decimal"]["relative_log_wealth_100x"]
    assert log == pytest.approx(ar + nonlinear, abs=1e-12)
    assert summary["components_100x_decimal"]["quadratic_identity_residual_100x"] == pytest.approx(0, abs=1e-12)
    assert frame["relative_log_spread"].tolist() == pytest.approx([
        math.log1p(y) - math.log1p(x) for x, y in zip(
            [.03, -.04, .07], [.05, -.06, .08])])


def test_identical_paths_have_zero_gap_and_correction():
    _, result = study(paired([.2, -.15, .08, -.03],
                             [.2, -.15, .08, -.03]))
    c = result["components_100x_decimal"]
    assert c["relative_log_wealth_100x"] == pytest.approx(0)
    assert c["arithmetic_spread_sum_100x"] == pytest.approx(0)
    assert c["nonlinear_correction_100x"] == pytest.approx(0)
    assert result["wealth"]["terminal_return_gap_pp_of_initial_capital"] == pytest.approx(0)


def test_arithmetic_spread_zero_can_still_lose_compounded_wealth():
    _, report = study(paired([0, 0], [.1, -.1]))
    c = report["components_100x_decimal"]
    assert c["arithmetic_spread_sum_100x"] == pytest.approx(0)
    assert c["nonlinear_correction_100x"] == pytest.approx(100 * math.log(.99))
    assert c["quadratic_approx_100x"] == pytest.approx(-1.0)
    assert report["wealth"]["ytsl_nav_multiple"] == pytest.approx(.99)
    assert report["wealth"]["tsla_cad_multiple"] == pytest.approx(1)
    assert report["wealth"]["terminal_return_gap_pp_of_initial_capital"] == pytest.approx(-1)


def test_swapping_assets_reverses_every_log_component():
    f1 = decompose(paired([.03, -.02, .11], [.04, -.04, .09]))
    f2 = decompose(paired([.04, -.04, .09], [.03, -.02, .11]))
    for key in ["arithmetic_spread", "relative_log_spread",
                "nonlinear_correction", "quadratic_component",
                "higher_order_remainder"]:
        assert f1[key].tolist() == pytest.approx((-f2[key]).tolist())


def test_invalid_loss_more_than_100_percent_rejected():
    with pytest.raises(CompoundingError, match="> -100%"):
        decompose(paired([0.0, 0.1], [-1, 0.02]))


def test_nan_return_rejected():
    f = paired([.01, .02], [.02, .03])
    f.loc[0, "ytsl_nav_return"] = float("nan")
    with pytest.raises(CompoundingError, match="finite"):
        decompose(f)


def test_invalid_or_discontinuous_date_rejected():
    f = paired([.01, .02, .03], [.02, .03, .04])
    f.loc[1, "previous_date"] = pd.Timestamp("2025-01-01")
    with pytest.raises(CompoundingError, match="contiguous"):
        decompose(f)


def test_duplicate_return_interval_rejected():
    f = paired([.01, .02, .03], [.02, .03, .04])
    f.loc[1, "date"] = f.loc[0, "date"]
    with pytest.raises(CompoundingError, match="sorted, and unique"):
        decompose(f)


def test_corrupted_wealth_levels_rejected_by_independent_bridge():
    f = paired([.01, .02, .03], [.02, .03, .04])
    f.loc[2, "nav_drip_index"] *= 1.2
    with pytest.raises(CompoundingError, match="Terminal wealth"):
        study(f)


def test_year_and_direction_groups_add_to_full_log_wealth():
    f, report = study(paired([.03, -.05, .1, -.02], [.04, -.07, .11, -.03]))
    all_log = report["components_100x_decimal"]["relative_log_wealth_100x"]
    assert sum(g["relative_log_wealth_100x"] for g in report["by_year"]) == pytest.approx(all_log)
    assert sum(g["relative_log_wealth_100x"] for g in report["by_tsla_direction"]) == pytest.approx(all_log)
    assert len(f) == 4


def test_real_snapshot_pinned_962_interval_reconciliation(tmp_path):
    report = run(SNAPSHOT_DIR, CASH_EVENTS, tmp_path)
    w = report["wealth"]
    c = report["components_100x_decimal"]
    assert report["status"] == "pass"
    assert report["paired_intervals"] == 962
    assert report["shared_closes"] == 963
    assert w["ytsl_nav_total_return_pct"] == pytest.approx(120.41139492221933, abs=1e-8)
    assert w["tsla_cad_total_return_pct"] == pytest.approx(164.54468803302754, abs=1e-8)
    assert w["terminal_return_gap_pp_of_initial_capital"] == pytest.approx(-44.13329311080821, abs=1e-8)
    assert w["relative_wealth_ratio_ytsl_over_tsla"] == pytest.approx(.8331726354478972, abs=1e-10)
    assert c["arithmetic_spread_sum_100x"] == pytest.approx(-4.843484614696847, abs=1e-9)
    assert c["nonlinear_correction_100x"] == pytest.approx(-13.407956670504487, abs=1e-9)
    assert c["relative_log_wealth_100x"] == pytest.approx(-18.25144128520136, abs=1e-9)
    assert c["quadratic_approx_100x"] == pytest.approx(-12.92485603584502, abs=1e-9)
    assert c["higher_order_remainder_100x"] == pytest.approx(-.483100634659512, abs=1e-9)
    assert abs(c["identity_residual_100x"]) < 1e-9
    year = {g["year"]: g for g in report["by_year"]}
    assert year[2024]["relative_log_wealth_100x"] == pytest.approx(-19.3754403730998, abs=1e-8)
    assert year[2025]["relative_log_wealth_100x"] == pytest.approx(9.660156554735583, abs=1e-8)
    assert report["extremes"]["worst_log_interval"] == "2025-03-10"
    assert report["extremes"]["best_log_interval"] == "2025-04-09"
    assert len(pd.read_csv(tmp_path / "compounding_daily.csv")) == 962
    assert len(pd.read_csv(tmp_path / "annual_log_components.csv")) == 5
    assert len(pd.read_csv(tmp_path / "extreme_intervals.csv")) == 20
    status = json.loads((tmp_path / "compounding_summary.json").read_text())
    assert status["input_sha256"] == {
        "purpose_nav": "a0a6c90c3d804c354bc53ef384630f8b0abff6d5fdb5d318cb75ca65ea6e76f7",
        "tsla_usd": "925076d6d488413b3c8246d206654d719186f3c73bd2bd5007ede1f9acd7c48b",
        "usd_cad": "ffaca3a83de376bf4b47cc32a5b73015b1a1767933903c0f12a0ab8a119f0fbf",
        "cash_events": "7142c89fa4e15efeef67b87d6d11e32a914863caee47b2b72dfa2422d226108e",
    }
