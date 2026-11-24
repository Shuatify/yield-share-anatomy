"""Reproduce all 3 total-return paths from the frozen source inputs."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from yield_share_anatomy.three_way import (
    CDR_FILE, START, END, WEALTH, align_three_way, compute, load_cdr,
    period_table, compound_table_matches_terminal,
)
from yield_share_anatomy.paths import SNAPSHOT_DIR, CASH_EVENTS


def test_shared_close_alignment_never_reconstructs_nav_drip():
    # The middle NAV-only date is intentionally absent from TSLA / CDR.
    # Cash on that day must be included by computing the NAV DRIP upstream.
    nav_index = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
        "nav_drip_index": [1.0, 1.2, 1.5],
    })
    tsla = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-06"]),
        "tsla_cad_reference": [100., 110.],
    })
    cdr = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-06"]),
        "close": [10., 11.],
    })
    aligned = align_three_way(nav_index, tsla, cdr, pd.Timestamp("2025-01-02"),
                              pd.Timestamp("2025-01-06"))
    assert len(aligned) == 2
    assert math.isclose(aligned["ytsl_nav_drip_wealth"].iloc[-1], 150.)
    assert math.isclose(aligned["tsla_cad_wealth"].iloc[-1], 110.)
    assert math.isclose(aligned["tsla_cdr_wealth"].iloc[-1], 110.)


def test_missing_required_endpoint_fails():
    frame = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-02", "2025-01-06"]),
        "nav_drip_index": [1., 1.2],
        "tsla_cad_reference": [100., 110.],
        "close": [10., 11.],
    })
    with pytest.raises(ValueError, match="Missing exact common"):
        align_three_way(frame, frame, frame, pd.Timestamp("2025-01-01"),
                        pd.Timestamp("2025-01-06"))


def test_annual_monthly_periods_exactly_compound():
    frame = pd.DataFrame({
        "date": pd.to_datetime([
            "2022-12-21", "2022-12-30", "2023-01-31", "2023-02-28", "2023-12-29"
        ]),
    })
    for col in WEALTH.values():
        frame[col] = [100., 90., 105., 102., 120.]
    annual, monthly = period_table(frame, "year"), period_table(frame, "month")
    compound_table_matches_terminal(annual, frame)
    compound_table_matches_terminal(monthly, frame)
    # 2023 return should use last 2022 close, not Jan 2023's first close.
    expected = 100 * (120 / 90 - 1)
    assert math.isclose(float(annual.loc[annual.period == "2023",
                                         "tsla_cdr_wealth_return_pct"].iloc[0]), expected)
    assert annual["period"].tolist() == ["2022", "2023"]


def test_frozen_snapshot_exact_endpoints_and_historic_baselines():
    if not CDR_FILE.exists():
        pytest.fail("CDR pinned input missing: new branch must include data snapshot")
    cdr = load_cdr(CDR_FILE)
    assert len(cdr) == 983
    assert cdr.date.iloc[0] == START
    assert cdr.date.iloc[-1] == END

    daily, annual, monthly, report = compute(
        CDR_FILE, SNAPSHOT_DIR / "ytsl_purpose_daily.csv", CASH_EVENTS,
        SNAPSHOT_DIR / "tsla_yahoo_daily.csv",
        SNAPSHOT_DIR / "usdcad_boc_daily.csv",
    )
    assert len(daily) == 963
    assert report["shared_intervals"] == 962
    assert daily.date.iloc[0] == START
    assert daily.date.iloc[-1] == END
    totals = report["total_return_pct"]
    assert math.isclose(totals["YTSL NAV DRIP"], 120.41139492221933,
                        abs_tol=1e-7)
    assert math.isclose(totals["TSLA CAD (unhedged)"], 164.54468803302754,
                        abs_tol=1e-7)
    assert math.isclose(totals["TSLA CDR (CAD hedged)"],
                        100 * (29.889999389648438 / 13.0 - 1),
                        abs_tol=1e-5)
    assert len(annual) == 5
    assert len(monthly) == 48
    compound_table_matches_terminal(annual, daily)
    compound_table_matches_terminal(monthly, daily)
    assert not any("USD" in name for name in WEALTH.values())
