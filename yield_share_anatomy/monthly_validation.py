#!/usr/bin/env python3
"""Independent calendar-month YTSL NAV DRIP vs TSLA CAD validation.

Purpose NAV total return and TSLA/USD/CAD are calculated on their own native
daily calendars. Each calendar-month return uses the final valid native
trading observation in that month, then compares with the previous month.
No market-price data are used. Legacy Phase 1 is read only for comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path

import pandas as pd

from .benchmark import build_tsla_fx_reference
from .nav import compute_nav_index, load_nav
from .paths import BASELINE_DIR, CASH_EVENTS, OUTPUT_DIR, SNAPSHOT_DIR
from .regimes import get_regime
from .returns import read_cash_events

THRESHOLD_PCT = 5.0
TOLERANCE_PP = 1e-7
LEGACY_FILE = BASELINE_DIR / "phase1" / "monthly_regimes.csv"


class MonthlyValidationError(ValueError):
    pass


def _monthly_last(df: pd.DataFrame, value_col: str,
                  date_col: str, output_col: str) -> pd.DataFrame:
    if not {"date", value_col}.issubset(df.columns):
        raise MonthlyValidationError(f"Missing date or {value_col}")
    if df.empty or df["date"].isna().any() or df["date"].duplicated().any():
        raise MonthlyValidationError(f"Invalid date series for {value_col}")
    valid = df.dropna(subset=[value_col]).sort_values("date").copy()
    if valid.empty or valid[value_col].le(0).any():
        raise MonthlyValidationError(f"Invalid {value_col} series")
    valid["month"] = valid["date"].dt.to_period("M").astype(str)
    last = valid.groupby("month", sort=True).tail(1)
    return last[["month", "date", value_col]].rename(
        columns={"date": date_col, value_col: output_col}).reset_index(drop=True)


def independent_monthly(nav_index: pd.DataFrame, tsla_fx: pd.DataFrame,
                        *, threshold_pct: float = THRESHOLD_PCT) -> pd.DataFrame:
    """Return the intervening *complete* calendar months.

    Conservatively drops the first and last observed months as partial
    observation windows, matching the pinned Phase 1 comparison policy.
    A later rolling project should have a dedicated full-month detector.
    """
    if threshold_pct <= 0:
        raise MonthlyValidationError("threshold_pct must be positive")
    if not {"date", "nav_drip_index", "cash_per_unit"}.issubset(nav_index):
        raise MonthlyValidationError("NAV index lacks required columns")
    nav_month = _monthly_last(nav_index, "nav_drip_index",
                              "nav_end_date", "nav_end_index")
    tsla_month = _monthly_last(tsla_fx, "tsla_cad_reference",
                               "tsla_end_date", "tsla_end_cad")
    if nav_month["month"].tolist() != tsla_month["month"].tolist():
        raise MonthlyValidationError(
            "NAV and TSLA have different covered months; cannot silently merge")
    periods = pd.PeriodIndex(nav_month["month"], freq="M")
    if len(periods) < 3:
        raise MonthlyValidationError("Need initial, final and >=1 intervening month")
    if any((periods[i].ordinal - periods[i-1].ordinal) != 1
           for i in range(1, len(periods))):
        raise MonthlyValidationError("Monthly series has gaps; investigate missing data")
    merged = nav_month.merge(tsla_month, on="month",
                             validate="one_to_one")
    merged["nav_previous_end_date"] = merged["nav_end_date"].shift(1)
    merged["tsla_previous_end_date"] = merged["tsla_end_date"].shift(1)
    merged["nav_monthly_pct"] = 100 * (
        merged["nav_end_index"] / merged["nav_end_index"].shift(1) - 1)
    merged["tsla_cad_monthly_pct"] = 100 * (
        merged["tsla_end_cad"] / merged["tsla_end_cad"].shift(1) - 1)
    merged["gap_pp"] = merged["nav_monthly_pct"] - merged["tsla_cad_monthly_pct"]
    merged["regime"] = merged["tsla_cad_monthly_pct"].map(
        lambda r: get_regime(float(r), threshold_pct) if pd.notna(r) else None)
    month_cash = nav_index.loc[nav_index["cash_per_unit"] > 0].copy()
    month_cash["month"] = month_cash["date"].dt.to_period("M").astype(str)
    amounts = month_cash.groupby("month")["cash_per_unit"].sum()
    counts = month_cash.groupby("month")["cash_per_unit"].size()
    merged["cash_events"] = merged["month"].map(counts).fillna(0).astype(int)
    merged["cash_per_unit_total"] = merged["month"].map(amounts).fillna(0.0)
    merged["native_end_dates_aligned"] = (
        merged["nav_end_date"] == merged["tsla_end_date"])
    merged["month_last_calendar_date"] = (
        pd.PeriodIndex(merged["month"], freq="M").to_timestamp(how="end").normalize())
    merged["nav_end_age_days"] = (
        merged["month_last_calendar_date"] - merged["nav_end_date"]).dt.days
    merged["tsla_end_age_days"] = (
        merged["month_last_calendar_date"] - merged["tsla_end_date"]).dt.days
    result = merged.iloc[1:-1].copy().reset_index(drop=True)
    if (result[["nav_end_age_days", "tsla_end_age_days"]] > 7).any().any():
        raise MonthlyValidationError("Stale month-end observation (>7 days)")
    return result[[
        "month", "nav_previous_end_date", "nav_end_date",
        "tsla_previous_end_date", "tsla_end_date", "month_last_calendar_date",
        "native_end_dates_aligned", "nav_end_age_days", "tsla_end_age_days",
        "cash_events", "cash_per_unit_total", "nav_monthly_pct",
        "tsla_cad_monthly_pct", "gap_pp", "regime",
    ]]


def compare_with_legacy(independent: pd.DataFrame,
                        legacy: pd.DataFrame) -> pd.DataFrame:
    required = {"month", "date", "regime", "tsla_monthly_pct",
                "ytsl_nav_drip_monthly_pct", "gap_pp"}
    if not required.issubset(legacy):
        raise MonthlyValidationError(f"Legacy file missing {sorted(required - set(legacy))}")
    if legacy["month"].duplicated().any() or independent["month"].duplicated().any():
        raise MonthlyValidationError("Duplicate monthly observations")
    if set(legacy["month"]) != set(independent["month"]):
        raise MonthlyValidationError("Independent/legacy month sets differ")
    old = legacy[list(required)].rename(columns={
        "date": "legacy_end_date",
        "regime": "legacy_regime",
        "tsla_monthly_pct": "legacy_tsla_cad_monthly_pct",
        "ytsl_nav_drip_monthly_pct": "legacy_nav_monthly_pct",
        "gap_pp": "legacy_gap_pp",
    })
    out = independent.merge(old, on="month", validate="one_to_one")
    for a, b, name in [
        ("nav_monthly_pct", "legacy_nav_monthly_pct", "nav_difference_pp"),
        ("tsla_cad_monthly_pct", "legacy_tsla_cad_monthly_pct", "tsla_difference_pp"),
        ("gap_pp", "legacy_gap_pp", "gap_difference_pp"),
    ]:
        out[name] = out[a] - pd.to_numeric(out[b], errors="raise")
    old_date = pd.to_datetime(out["legacy_end_date"], errors="raise")
    out["legacy_month_end_matches_both"] = (
        (old_date == out["nav_end_date"]) & (old_date == out["tsla_end_date"]))
    out["regime_matched"] = out["regime"] == out["legacy_regime"]
    return out.sort_values("month").reset_index(drop=True)


def describe_regimes(monthly: pd.DataFrame) -> list[dict]:
    rows = []
    for label in ("Up", "Sideways", "Down"):
        group = monthly.loc[monthly["regime"] == label, "gap_pp"].astype(float)
        rows.append({
            "regime": label, "months": int(len(group)),
            "mean_gap_pp": float(group.mean()) if len(group) else None,
            "median_gap_pp": float(group.median()) if len(group) else None,
            "ytsl_win_months": int((group > 0).sum()),
            "ytsl_win_rate_pct": 100 * float((group > 0).mean()) if len(group) else None,
        })
    return rows


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(snapshot_dir: Path = SNAPSHOT_DIR, events_file: Path = CASH_EVENTS,
        baseline_file: Path = LEGACY_FILE, out_dir: Path = OUTPUT_DIR / "regime_validation",
        *, threshold_pct: float = THRESHOLD_PCT,
        tolerance_pp: float = TOLERANCE_PP) -> dict:
    if tolerance_pp <= 0:
        raise MonthlyValidationError("tolerance_pp must be positive")
    source_files = {
        "ytsl_nav": snapshot_dir / "ytsl_purpose_daily.csv",
        "tsla_usd": snapshot_dir / "tsla_yahoo_daily.csv",
        "usd_cad_fx": snapshot_dir / "usdcad_boc_daily.csv",
        "cash_events": events_file,
        "legacy_months": baseline_file,
    }
    cash = read_cash_events(events_file)
    nav_index = compute_nav_index(load_nav(source_files["ytsl_nav"]), cash)
    tsla_fx = build_tsla_fx_reference(
        pd.read_csv(source_files["tsla_usd"]),
        pd.read_csv(source_files["usd_cad_fx"]))
    independent = independent_monthly(nav_index, tsla_fx,
                                       threshold_pct=threshold_pct)
    old = pd.read_csv(baseline_file)
    comparison = compare_with_legacy(independent, old)
    max_diffs = {col: float(comparison[col].abs().max()) for col in
                 ("nav_difference_pp", "tsla_difference_pp", "gap_difference_pp")}
    unresolved = comparison.loc[
        ~comparison["legacy_month_end_matches_both"] |
        ~comparison["regime_matched"] |
        ~comparison["native_end_dates_aligned"] |
        (comparison[list(max_diffs)].abs() > tolerance_pp).any(axis=1),
        "month"].tolist()
    summary = {
        "status": "pass" if not unresolved else "needs_investigation",
        "research_status": "issuer_benchmarked_nav_but_cash_seed_provisional",
        "month_count": len(comparison),
        "first_month": str(comparison["month"].iloc[0]),
        "last_month": str(comparison["month"].iloc[-1]),
        "threshold_pct": threshold_pct,
        "tolerance_pp": tolerance_pp,
        "max_abs_difference_pp": max_diffs,
        "regime_mismatch_months": comparison.loc[
            ~comparison["regime_matched"], "month"].tolist(),
        "month_end_mismatch_months": comparison.loc[
            ~comparison["native_end_dates_aligned"] |
            ~comparison["legacy_month_end_matches_both"], "month"].tolist(),
        "review_months": unresolved,
        "regime_summary": describe_regimes(independent),
        "input_sha256": {key: _hash(file) for key, file in source_files.items()},
        "methodology": {
            "nav": "Full YTSL Purpose NAV DRIP, exact cash ex-dates, no market-price filtering",
            "tsla_cad": "Actual TSLA US trading dates, Yahoo adjusted close times BoC USD/CAD (<=5-day backward FX)",
            "monthly": "Last native trading observation each calendar month; compare to prior month's last native observation",
            "scope": "Drop first and last observed months conservatively (current data: 2022-12 and partial 2026-11)",
            "mismatch_handling": "Report native month-end date mismatch, legacy date mismatch, return difference and regime change",
            "limitation": "Descriptive not causal; fund leverage, options, FX hedge, fees not decomposed",
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    independent.to_csv(out_dir / "independent_monthly.csv", index=False)
    comparison.to_csv(out_dir / "monthly_vs_legacy.csv", index=False)
    (out_dir / "regime_validation_status.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot-dir", type=Path, default=SNAPSHOT_DIR)
    p.add_argument("--events", type=Path, default=CASH_EVENTS)
    p.add_argument("--legacy", type=Path, default=LEGACY_FILE)
    p.add_argument("--out", type=Path, default=OUTPUT_DIR / "regime_validation")
    p.add_argument("--threshold-pct", type=float, default=THRESHOLD_PCT)
    p.add_argument("--tolerance-pp", type=float, default=TOLERANCE_PP)
    args = p.parse_args()
    try:
        report = run(args.snapshot_dir, args.events, args.legacy, args.out,
                     threshold_pct=args.threshold_pct,
                     tolerance_pp=args.tolerance_pp)
    except (ValueError, OSError, KeyError) as err:
        p.exit(1, f"Regime validation failed: {err}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "pass":
        p.exit(2, "Monthly reconciliation needs investigation; inspect monthly_vs_legacy.csv.\n")


if __name__ == "__main__":
    main()
